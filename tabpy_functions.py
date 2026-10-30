"""TabPy endpoints for the Tableau cohort workbook.

The workbook can compute plain ratios natively, but it cannot fit a retention
curve, build a confidence interval, extrapolate cumulative LTV beyond a cohort's
observed window, or test two cohort rates for significance. These functions run
inside a TabPy server via ``SCRIPT_REAL`` and cover exactly those gaps.

Contract: every public function accepts scalars or lists (Tableau passes a list
of the rows in the partition, or a single scalar) and returns a plain ``list``
whose length equals the longest input list, or 1 for a scalar result applied to
every row. ``NaN`` and ``inf`` are not valid JSON, so an undefined value is
returned as ``None`` (rendered as null by Tableau) instead of a number.

Typical usage in a calculated field::

    SCRIPT_REAL("return tabpy.query('wilson_lower', _arg1, _arg2)['response']",
                SUM([is_active]), COUNT([user_id]))

Tableau injects the ``tabpy`` client into the script scope; the endpoint must be
deployed first (``tabpy/deploy.py``).
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

__all__ = [
    "ENDPOINTS",
    "ltv_at_horizon",
    "retention_forecast",
    "retention_rate",
    "wilson_lower",
    "wilson_upper",
    "ztest_two_proportions",
]

_NORMAL = NormalDist()


def _as_list(x: object) -> list | None:
    """Normalise a TabPy argument to a list; ``None`` stays ``None``."""
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return list(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    return [x]


def _clean(x: object) -> float | None:
    """Coerce to a finite float; ``None`` for nulls, non-numbers, NaN and inf."""
    if x is None:
        return None
    try:
        value = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _scalar(x: object) -> float | None:
    """Like ``_clean``, but unwraps a one-element list.

    TabPy wraps a constant argument in a list when the query is sent over REST
    (``{"_arg3": [12]}``), while ``SCRIPT_REAL`` sends the bare scalar. Both
    must reach the same value.
    """
    seq = _as_list(x)
    if seq is None or len(seq) != 1:
        return None
    return _clean(seq[0])


def _broadcast(*args: object) -> list[tuple]:
    """Zip all arguments to one length, stretching length-1 inputs to the max.

    Lengths greater than 1 must agree, otherwise ``ValueError`` is raised: a
    silent truncation would misalign a rate with the wrong cohort size.
    """
    sequences: list[list] = []
    for arg in args:
        seq = _as_list(arg)
        sequences.append([None] if seq is None else seq)

    lengths = {len(seq) for seq in sequences}
    if 0 in lengths and max(lengths) > 0:
        raise ValueError("Cannot broadcast an empty list against non-empty arguments")
    non_unit = {n for n in lengths if n > 1}
    if len(non_unit) > 1:
        raise ValueError(
            f"Cannot broadcast arguments with different lengths: {sorted(non_unit)}"
        )

    target = max(lengths) if lengths else 0
    rows: list[tuple] = []
    for i in range(target):
        row: list = []
        for seq in sequences:
            if len(seq) == target:
                row.append(seq[i])
            elif len(seq) == 1:
                row.append(seq[0])
            else:
                row.append(None)
        rows.append(tuple(row))
    return rows


def retention_rate(active: object, cohort_size: object) -> list[float | None]:
    """``active / cohort_size`` clipped to ``[0, 1]``.

    A missing or non-positive cohort size yields ``None`` rather than ``0.0``,
    so a broken denominator is visible instead of looking like zero retention.
    """
    result: list[float | None] = []
    for active_raw, size_raw in _broadcast(active, cohort_size):
        a = _clean(active_raw)
        n = _clean(size_raw)
        if a is None or n is None or n <= 0:
            result.append(None)
            continue
        result.append(min(1.0, max(0.0, a / n)))
    return result


def _wilson(
    successes: object, trials: object, level: object
) -> list[tuple[float | None, float | None]]:
    """Wilson score interval per broadcast row, as ``(low, high)`` pairs."""
    bounds: list[tuple[float | None, float | None]] = []
    for s_raw, n_raw, level_raw in _broadcast(successes, trials, level):
        s = _clean(s_raw)
        n = _clean(n_raw)
        confidence = _clean(level_raw)
        if s is None or n is None or confidence is None or n <= 0:
            bounds.append((None, None))
            continue
        if s < 0 or s > n or not 0.0 < confidence < 1.0:
            bounds.append((None, None))
            continue

        z = _NORMAL.inv_cdf((1.0 + confidence) / 2.0)
        p_hat = s / n
        denom = 1.0 + z * z / n
        center = (p_hat + z * z / (2.0 * n)) / denom
        half = z * math.sqrt(p_hat * (1.0 - p_hat) / n + z * z / (4.0 * n * n)) / denom
        low = center - half
        high = center + half
        # At p_hat == 0 (or 1) center and half are mathematically equal, so the
        # difference carries only rounding noise whose sign depends on the build's
        # inv_cdf. Pin the boundary exactly instead of trusting max() to absorb it.
        if s <= 0.0:
            low = 0.0
        if s >= n:
            high = 1.0
        bounds.append((min(1.0, max(0.0, low)), min(1.0, max(0.0, high))))
    return bounds


def wilson_lower(successes: object, trials: object, level: object = 0.95) -> list[float | None]:
    """Lower bound of the two-sided Wilson score interval for a proportion."""
    return [low for low, _ in _wilson(successes, trials, level)]


def wilson_upper(successes: object, trials: object, level: object = 0.95) -> list[float | None]:
    """Upper bound of the two-sided Wilson score interval for a proportion."""
    return [high for _, high in _wilson(successes, trials, level)]


def ztest_two_proportions(
    successes_a: object, trials_a: object, successes_b: object, trials_b: object
) -> list[float | None]:
    """Two-sided two-proportion z-test with pooled variance; returns p-value.

    ``se == 0`` (both samples degenerate) yields ``None`` since z is undefined.
    """
    result: list[float | None] = []
    for s1_raw, n1_raw, s2_raw, n2_raw in _broadcast(successes_a, trials_a, successes_b, trials_b):
        s1 = _clean(s1_raw)
        n1 = _clean(n1_raw)
        s2 = _clean(s2_raw)
        n2 = _clean(n2_raw)
        if s1 is None or n1 is None or s2 is None or n2 is None:
            result.append(None)
            continue
        if n1 <= 0 or n2 <= 0:
            result.append(None)
            continue

        p1 = s1 / n1
        p2 = s2 / n2
        pooled = (s1 + s2) / (n1 + n2)
        se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2))
        if se == 0.0:
            result.append(None)
            continue

        z = (p1 - p2) / se
        result.append(math.erfc(abs(z) / math.sqrt(2.0)))
    return result


def retention_forecast(rates: object, periods: object = None) -> list[float | None]:
    """Fit ``r(p) = A * p**(-b)`` and return fitted values on the same period grid.

    The fit is a log-log linear regression over points with ``p >= 1`` and
    ``r > 0``; period 0 is not part of the model, so its input value is passed
    through unchanged. The regression supplies only the decay exponent: the
    curve is anchored on the first observed rate, because a free-intercept fit
    can predict a rate above 1.0 at period 1 and clipping would hide that.
    Values are clipped to ``[0, 1]`` and ``p < 0`` gives ``None``. What comes
    back is the smoothed/predicted rate per input row, not the coefficients: to
    extrapolate beyond the observed window, pass a longer ``periods`` list than
    the observed one. With fewer than two usable points the input is returned
    as-is (cleaned only).
    """
    rate_list = _as_list(rates)
    if rate_list is None:
        return [None]
    cleaned: list[float | None] = [_clean(r) for r in rate_list]
    if not cleaned:
        return []

    if periods is None:
        grid: list[float | None] = [float(i) for i in range(len(cleaned))]
    else:
        raw_grid = _as_list(periods)
        if raw_grid is None:
            grid = [float(i) for i in range(len(cleaned))]
        else:
            grid = [_clean(p) for p in raw_grid]
            if len(grid) == 1 and len(cleaned) > 1:
                grid = grid * len(cleaned)
            elif len(grid) != len(cleaned):
                raise ValueError(
                    f"periods length {len(grid)} does not match rates length {len(cleaned)}"
                )

    points: list[tuple[float, float]] = []
    for p, r in zip(grid, cleaned, strict=False):
        if p is None or r is None:
            continue
        if p >= 1.0 and r > 0.0:
            points.append((p, r))

    if len(points) < 2 or len({p for p, _ in points}) < 2:
        return cleaned

    slope, _intercept = np.polyfit(
        [math.log(p) for p, _ in points],
        [math.log(r) for _, r in points],
        1,
    )
    anchor_p, anchor_r = min(points)

    result: list[float | None] = []
    for p, r in zip(grid, cleaned, strict=False):
        if p is None or p < 0.0:
            result.append(None)
            continue
        if p == 0.0:
            result.append(r)
            continue
        predicted = anchor_r * (p / anchor_p) ** slope
        result.append(min(1.0, max(0.0, predicted)))
    return result


def ltv_at_horizon(
    revenue_by_period: object, users: object, horizon: object
) -> list[float | None]:
    """Cumulative LTV after a fixed number of periods, per user.

    ``cohort_analysis.py`` cumulates revenue over each cohort's whole observed
    window, so older cohorts mechanically show a higher ``ltv``. Fixing the
    horizon makes cohorts comparable: periods ``0..horizon-1`` are summed, and
    when the observed series is shorter the tail is extrapolated with a
    log-linear fit ``ln R_p = a + b*p`` over the positive periods.

    Extrapolation needs at least two positive periods. With less — typically a
    cohort observed for a single period — the result is ``None`` rather than a
    repeated period-0 figure, which would overstate LTV by an order of
    magnitude. This mirrors ``cohort_analysis.ltv_at_k``, where young cohorts
    are excluded instead of zero- or guess-filled.

    Always returns a one-element list so the value is applied to every row of
    the view; ``users <= 0`` or no revenue data gives ``[None]``.
    """
    horizon_value = _scalar(horizon)
    if horizon_value is None or horizon_value < 1:
        raise ValueError("horizon must be an integer >= 1")
    steps = int(horizon_value)

    cohort = _scalar(users)
    raw_revenue = _as_list(revenue_by_period)
    values: list[float] = []
    for item in raw_revenue or []:
        cleaned_item = _clean(item)
        if cleaned_item is not None:
            values.append(cleaned_item)

    if cohort is None or cohort <= 0 or not values:
        return [None]

    observed = len(values)
    if observed >= steps:
        return [sum(values[:steps]) / cohort]

    total = sum(values)
    positive = [(index, value) for index, value in enumerate(values) if value > 0.0]
    if len(positive) < 2:
        return [None]

    xs = [float(index) for index, _ in positive]
    ys = [math.log(value) for _, value in positive]
    slope, intercept = np.polyfit(xs, ys, 1)
    for period in range(observed, steps):
        total += max(0.0, math.exp(intercept + slope * period))
    return [total / cohort]


# TabPy calls an endpoint with keyword arguments named ``_arg1``, ``_arg2``, ...
# — the same names SCRIPT_* uses. The functions above keep readable parameter
# names for direct use and tests; the adapters below are the only thing the
# server ever sees.


def retention_rate_ep(_arg1: object, _arg2: object) -> list[float | None]:
    """TabPy adapter for :func:`retention_rate`."""
    return retention_rate(_arg1, _arg2)


def wilson_lower_ep(_arg1: object, _arg2: object, _arg3: object = 0.95) -> list[float | None]:
    """TabPy adapter for :func:`wilson_lower`."""
    return wilson_lower(_arg1, _arg2, _arg3)


def wilson_upper_ep(_arg1: object, _arg2: object, _arg3: object = 0.95) -> list[float | None]:
    """TabPy adapter for :func:`wilson_upper`."""
    return wilson_upper(_arg1, _arg2, _arg3)


def ztest_two_proportions_ep(
    _arg1: object, _arg2: object, _arg3: object, _arg4: object
) -> list[float | None]:
    """TabPy adapter for :func:`ztest_two_proportions`."""
    return ztest_two_proportions(_arg1, _arg2, _arg3, _arg4)


def retention_forecast_ep(_arg1: object, _arg2: object = None) -> list[float | None]:
    """TabPy adapter for :func:`retention_forecast`."""
    return retention_forecast(_arg1, _arg2)


def ltv_at_horizon_ep(_arg1: object, _arg2: object, _arg3: object) -> list[float | None]:
    """TabPy adapter for :func:`ltv_at_horizon`."""
    return ltv_at_horizon(_arg1, _arg2, _arg3)


ENDPOINTS: dict[str, callable] = {
    "retention_rate": retention_rate_ep,
    "wilson_lower": wilson_lower_ep,
    "wilson_upper": wilson_upper_ep,
    "ztest_two_proportions": ztest_two_proportions_ep,
    "retention_forecast": retention_forecast_ep,
    "ltv_at_horizon": ltv_at_horizon_ep,
}
