"""Load real cohort data from CSV into the standard user-period contract.

Contract (one row per user-period), same as the synthetic generator:
    user_id, cohort_month, join_date, period, is_active, revenue

cohort_month is derived from join_date (data-model convention). Any extra
columns in the CSV (PII: email, phone, name) are dropped — whitelist-only.

Validation is fail-fast and ordered so the earliest check that can explain the
problem wins: required columns, whitelist select, numeric parse, integrality,
date parse, range checks, duplicate (user_id, period), period-0 coverage.
"""

from __future__ import annotations

import pathlib

import pandas as pd

CONTRACT = ["user_id", "cohort_month", "join_date", "period", "is_active", "revenue"]
REQUIRED = ["user_id", "join_date", "period", "is_active", "revenue"]

_INT_COLUMNS = ["user_id", "period", "is_active", "revenue"]


def _to_int_column(df: pd.DataFrame, col: str, path: pathlib.Path) -> pd.Series:
    """Coerce ``col`` to int64, rejecting non-numeric and non-integral values.

    Both checks run on the pre-cast values, so ``astype("int64")`` can never
    silently truncate a fractional input (is_active 1.9 -> 1, revenue 10.7 -> 10).

    A blank cell counts as an error here rather than falling through to the cast,
    which would raise a pandas-internal IntCastingNaNError naming neither file
    nor column.
    """
    coerced = pd.to_numeric(df[col], errors="coerce")
    if coerced.isna().any():
        raise ValueError(f"{path}: column '{col}' is not numeric or has missing values")
    if (coerced != coerced.round()).any():
        raise ValueError(f"{path}: column '{col}' must contain integers, found non-integral values")
    return coerced.astype("int64")


def load_real_data(path: str | pathlib.Path) -> pd.DataFrame:
    """Read a CSV into the 6-column user-period contract.

    Raises FileNotFoundError if the file is missing, ValueError if required
    columns are absent, values are non-numeric/non-integral/missing, join_date is
    numeric, missing, or unparseable, values are out of range, a (user_id, period)
    pair repeats, or a user has no period-0 row.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"data file not found: {path}")
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing required columns: {missing}")
    df = df[REQUIRED].copy()  # PII-scrub: whitelist only

    for col in _INT_COLUMNS:
        df[col] = _to_int_column(df, col, path)

    if df["join_date"].isna().any():
        raise ValueError(f"{path}: column 'join_date' has missing values")
    if pd.api.types.is_numeric_dtype(df["join_date"]):
        raise ValueError(
            f"{path}: column 'join_date' must be a date string, not a number — "
            "an integer date such as 20230115 is read by pandas as nanoseconds "
            "since 1970 and would silently collapse every user into one cohort"
        )
    try:
        join_date = pd.to_datetime(df["join_date"], errors="raise")
    except (TypeError, ValueError):
        raise ValueError(f"{path}: column 'join_date' is not a parseable date") from None
    if join_date.isna().any():
        raise ValueError(f"{path}: column 'join_date' is not a parseable date")
    df["join_date"] = join_date.dt.to_period("M").dt.to_timestamp()
    df["cohort_month"] = df["join_date"]

    if not df["is_active"].isin([0, 1]).all():
        raise ValueError(f"{path}: is_active must be 0 or 1")
    if (df["period"] < 0).any():
        raise ValueError(f"{path}: period must be >= 0")
    if (df["revenue"] < 0).any():
        raise ValueError(f"{path}: revenue must be >= 0")

    duplicates = df.duplicated(["user_id", "period"])
    if duplicates.any():
        raise ValueError(f"{path}: {int(duplicates.sum())} duplicate (user_id, period) rows")

    users_without_period_0 = set(df["user_id"]) - set(df.loc[df["period"] == 0, "user_id"])
    if users_without_period_0:
        raise ValueError(f"{path}: {len(users_without_period_0)} users have no period-0 row")

    return df[CONTRACT]
