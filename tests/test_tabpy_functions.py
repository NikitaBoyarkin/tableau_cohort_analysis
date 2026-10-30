"""Unit tests: TabPy endpoints contract (types, lengths, nulls, statistics)."""

from __future__ import annotations

import math

import numpy as np
import pytest

import tabpy_functions
from tabpy_functions import (
    ENDPOINTS,
    ltv_at_horizon,
    retention_forecast,
    retention_rate,
    wilson_lower,
    wilson_upper,
    ztest_two_proportions,
)


def assert_clean_list(result: object) -> list:
    """Assert a plain, JSON-safe list: no ndarray, no NaN, no inf."""
    assert isinstance(result, list), f"expected list, got {type(result)!r}"
    assert not isinstance(result, np.ndarray)
    for value in result:
        if isinstance(value, bool) or value is None:
            continue
        assert isinstance(value, (int, float)), f"unexpected value {value!r}"
        assert not math.isnan(float(value)), f"NaN in result: {result!r}"
        assert math.isfinite(float(value)), f"inf in result: {result!r}"
    return result


def test_endpoints_registry_has_six_callables() -> None:
    assert set(ENDPOINTS) == {
        "retention_rate",
        "wilson_lower",
        "wilson_upper",
        "ztest_two_proportions",
        "retention_forecast",
        "ltv_at_horizon",
    }
    assert all(callable(fn) for fn in ENDPOINTS.values())


def test_endpoints_accept_tabpy_keyword_argument_names() -> None:
    # TabPy invokes an endpoint with _arg1.._argN as *keyword* arguments
    # (that is what /query and SCRIPT_* send). A readable parameter name raises
    # TypeError: "got an unexpected keyword argument '_arg1'" at query time.
    assert ENDPOINTS["retention_rate"](_arg1=[50], _arg2=[100]) == [0.5]
    assert ENDPOINTS["wilson_lower"](_arg1=[50], _arg2=[100], _arg3=0.95)[0] == pytest.approx(
        0.4038, abs=1e-3
    )
    assert ENDPOINTS["wilson_upper"](_arg1=[50], _arg2=[100])[0] == pytest.approx(0.5962, abs=1e-3)
    assert ENDPOINTS["ztest_two_proportions"](_arg1=90, _arg2=100, _arg3=10, _arg4=100)[0] < 1e-6
    assert ENDPOINTS["retention_forecast"](_arg1=[1.0, 0.8, 0.6])[0] == 1.0
    assert ENDPOINTS["ltv_at_horizon"](_arg1=[10.0, 20.0], _arg2=10, _arg3=2) == [3.0]


def test_retention_rate_scalar_and_list_broadcast() -> None:
    scalar = assert_clean_list(retention_rate(50, 100))
    assert scalar == [0.5]

    mixed = assert_clean_list(retention_rate([50, 25, 10], 100))
    assert mixed == [0.5, 0.25, 0.1]

    stretched = assert_clean_list(retention_rate(50, [100, 200]))
    assert stretched == [0.5, 0.25]


def test_retention_rate_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError):
        retention_rate([1, 2, 3], [10, 20])


def test_retention_rate_null_and_nan_become_none() -> None:
    result = assert_clean_list(retention_rate([50, float("nan"), None], 100))
    assert result == [0.5, None, None]

    result = assert_clean_list(retention_rate(50, [None, float("nan")]))
    assert result == [None, None]


def test_retention_rate_zero_cohort_size_is_none() -> None:
    assert retention_rate(5, 0) == [None]
    assert retention_rate(5, -10) == [None]


def test_retention_rate_clips_to_unit_interval() -> None:
    assert retention_rate(200, 100) == [1.0]
    assert retention_rate(-5, 100) == [0.0]


def test_wilson_bounds_exact_value_50_of_100() -> None:
    low = assert_clean_list(wilson_lower(50, 100, 0.95))[0]
    high = assert_clean_list(wilson_upper(50, 100, 0.95))[0]
    assert low == pytest.approx(0.4038, abs=1e-3)
    assert high == pytest.approx(0.5962, abs=1e-3)
    assert low <= 0.5 <= high


def test_wilson_zero_successes_edge_case() -> None:
    low = assert_clean_list(wilson_lower(0, 10))[0]
    high = assert_clean_list(wilson_upper(0, 10))[0]
    assert low == 0.0
    assert 0.0 < high < 1.0


def test_wilson_all_successes_edge_case() -> None:
    low = assert_clean_list(wilson_lower(10, 10))[0]
    high = assert_clean_list(wilson_upper(10, 10))[0]
    assert high == 1.0
    assert 0.0 < low < 1.0


def test_wilson_zero_trials_is_none() -> None:
    assert wilson_lower(0, 0) == [None]
    assert wilson_upper(5, 0) == [None]


def test_wilson_level_broadcast_and_length() -> None:
    result = assert_clean_list(wilson_lower([50, 50, 50], [100, 100, 100], [0.95, 0.9, 0.95]))
    assert len(result) == 3
    assert result[0] == pytest.approx(result[2])
    assert result[1] > result[0]


def test_ztest_identical_proportions_gives_one() -> None:
    p_value = assert_clean_list(ztest_two_proportions(10, 100, 20, 200))[0]
    assert p_value == pytest.approx(1.0, abs=1e-9)


def test_ztest_large_difference_is_significant() -> None:
    p_value = assert_clean_list(ztest_two_proportions(90, 100, 10, 100))[0]
    assert p_value < 1e-6


def test_ztest_zero_trials_is_none() -> None:
    assert ztest_two_proportions(0, 0, 10, 100) == [None]
    result = assert_clean_list(ztest_two_proportions([5, 5], [10, 10], [1, 1], [10, 0]))
    assert result[0] == pytest.approx(0.051, abs=1e-3)
    assert result[1] is None


def test_ztest_broadcast_length_and_types() -> None:
    result = assert_clean_list(ztest_two_proportions([10, 20], 100, 10, [100, 200]))
    assert len(result) == 2
    with pytest.raises(ValueError):
        ztest_two_proportions([10, 20], [100, 100], 10, [100, 200, 50])


def test_retention_forecast_recovers_power_law() -> None:
    noise = [0.0, 0.002, -0.003, 0.001, -0.002, 0.003, -0.001]
    rates = [1.0] + [0.85 * p**-0.6 + noise[p] for p in range(1, 7)]

    result = assert_clean_list(retention_forecast(rates))
    assert len(result) == len(rates)
    assert result[0] == pytest.approx(1.0)
    for p in range(1, 7):
        assert result[p] == pytest.approx(0.85 * p**-0.6, abs=0.05)


def test_retention_forecast_passes_through_when_unfittable() -> None:
    assert retention_forecast([1.0]) == [1.0]
    assert retention_forecast([1.0, 0.5], periods=[0, 0]) == [1.0, 0.5]


def test_retention_forecast_negative_period_is_none() -> None:
    rates = [1.0, 0.85, 0.70, 0.60, 0.55, 0.50]
    periods = [0, 1, 2, 3, -1, 5]
    result = assert_clean_list(retention_forecast(rates, periods))
    assert result[4] is None
    assert all(value is not None for index, value in enumerate(result) if index != 4)


def test_retention_forecast_periods_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        retention_forecast([1.0, 0.8, 0.6], periods=[0, 1])


def test_ltv_at_horizon_without_extrapolation() -> None:
    result = assert_clean_list(ltv_at_horizon([10.0, 20.0, 30.0], 10, 2))
    assert result == [3.0]
    assert len(result) == 1


def test_ltv_at_horizon_extrapolation_is_monotonic() -> None:
    revenue = [100.0, 50.0, 40.0]
    three = ltv_at_horizon(revenue, 10, 3)[0]
    four = ltv_at_horizon(revenue, 10, 4)[0]
    five = ltv_at_horizon(revenue, 10, 5)[0]
    assert three == pytest.approx(19.0)
    assert three <= four <= five


def test_ltv_at_horizon_ignores_nulls_in_series() -> None:
    result = assert_clean_list(ltv_at_horizon([100.0, None, float("nan"), 40.0], 10, 2))
    assert result == [14.0]


def test_ltv_at_horizon_args_errors_and_empty() -> None:
    with pytest.raises(ValueError):
        ltv_at_horizon([10.0, 20.0], 10, 0)
    assert ltv_at_horizon([10.0, 20.0], 0, 2) == [None]
    assert ltv_at_horizon([], 10, 2) == [None]


def test_ltv_at_horizon_accepts_single_element_lists() -> None:
    # Over REST TabPy sends constants as {"_arg2": [100], "_arg3": [12]}.
    assert ltv_at_horizon([10.0, 20.0], [10], [2]) == ltv_at_horizon([10.0, 20.0], 10, 2)


def test_ltv_at_horizon_needs_two_points_to_extrapolate() -> None:
    # A single observed period cannot be extrapolated: repeating the period-0
    # figure would inflate LTV by an order of magnitude.
    assert ltv_at_horizon([1000.0], 100, 12) == [None]
    assert ltv_at_horizon([1000.0, 800.0], 100, 12)[0] is not None


def test_all_endpoints_never_emit_nan() -> None:
    assert_clean_list(retention_rate([float("nan"), 5], [float("inf"), 10]))
    assert_clean_list(wilson_lower([float("nan"), 5], [10, float("inf")]))
    assert_clean_list(wilson_upper([5, 5], [10, 20], float("nan")))
    assert_clean_list(ztest_two_proportions([float("nan"), 5], [10, 20], 5, 20))
    assert_clean_list(retention_forecast([float("nan"), 0.8, 0.6]))
    assert_clean_list(tabpy_functions.ltv_at_horizon([100.0, float("nan")], 10, 4))
