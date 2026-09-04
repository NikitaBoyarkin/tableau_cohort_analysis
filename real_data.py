"""Load real cohort data from CSV into the standard user-period contract.

Contract (one row per user-period), same as the synthetic generator:
    user_id, cohort_month, join_date, period, is_active, revenue

cohort_month is derived from join_date (data-model convention). Any extra
columns in the CSV (PII: email, phone, name) are dropped — whitelist-only.
"""

from __future__ import annotations

import pathlib

import pandas as pd

CONTRACT = ["user_id", "cohort_month", "join_date", "period", "is_active", "revenue"]
REQUIRED = ["user_id", "join_date", "period", "is_active", "revenue"]


def load_real_data(path: str | pathlib.Path) -> pd.DataFrame:
    """Read a CSV into the 6-column user-period contract.

    Raises FileNotFoundError if the file is missing, ValueError if required
    columns are absent or values are out of range.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"data file not found: {path}")
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    df = df[REQUIRED].copy()  # PII-scrub: whitelist only
    df["join_date"] = pd.to_datetime(df["join_date"]).dt.to_period("M").dt.to_timestamp()
    df["cohort_month"] = df["join_date"]
    df["user_id"] = df["user_id"].astype("int64")
    df["period"] = df["period"].astype("int64")
    df["is_active"] = df["is_active"].astype("int64")
    df["revenue"] = df["revenue"].astype("int64")
    if not df["is_active"].isin([0, 1]).all():
        raise ValueError("is_active must be 0 or 1")
    if (df["period"] < 0).any():
        raise ValueError("period must be >= 0")
    if (df["revenue"] < 0).any():
        raise ValueError("revenue must be >= 0")
    return df[CONTRACT]
