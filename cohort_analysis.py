"""Cohort retention and LTV analysis on synthetic user data.

Data model (one row per user-period):
    user_id      - synthetic user id
    cohort_month - month the user joined (cohort key, derived from join_date)
    join_date    - first-of-month join date
    period       - months since join (0 = join month)
    is_active    - 1 if the user was active in that month, else 0
    revenue      - revenue generated that month (0 if inactive)

Conventions:
    period 0 retention is 100% by definition (everyone is active the month they
    join). The retention curve decays from period 1 onward.

Run directly to print a text summary:

    uv run python cohort_analysis.py
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

BASE_DATE = pd.Timestamp("2023-01-01")


@dataclass(frozen=True)
class DataConfig:
    num_users: int = 1000
    num_cohorts: int = 10  # join months: BASE_DATE .. BASE_DATE + (num_cohorts-1)
    max_periods: int = 12  # months of history observed per user
    base_retention: float = 0.85  # retention at period 1 (period 0 is always 1.0)
    decay: float = 0.75  # multiplicative decay per period
    revenue_lambda: float = 10.0  # mean monthly revenue per active user (Poisson)
    seed: int = 42


def generate_data(cfg: DataConfig | None = None) -> pd.DataFrame:
    """Generate a synthetic cohort dataset (one row per user-period)."""
    cfg = cfg or DataConfig()
    rng = np.random.default_rng(cfg.seed)

    cohorts = rng.integers(0, cfg.num_cohorts, size=cfg.num_users)
    # Calendar-month spacing via DateOffset; naive 30-day steps collide (Jan31 -> Jan).
    join_dates = np.array([BASE_DATE + pd.DateOffset(months=int(c)) for c in cohorts])

    rows: list[dict] = []
    for user_id, cohort, join_date in zip(
        range(cfg.num_users), cohorts, join_dates, strict=True
    ):
        # Newer cohorts have fewer observable periods (triangular matrix).
        n_periods = min(cfg.max_periods, cfg.num_cohorts - int(cohort))
        for period in range(n_periods):
            if period == 0:
                is_active = 1  # 100% retention in join month by convention
            else:
                p = cfg.base_retention * (cfg.decay ** (period - 1))
                p = min(max(float(p), 0.0), 1.0)
                is_active = int(rng.choice([0, 1], p=[1 - p, p]))
            revenue = int(rng.poisson(cfg.revenue_lambda)) if is_active else 0
            rows.append(
                {
                    "user_id": user_id,
                    "cohort_month": join_date,
                    "join_date": join_date,
                    "period": period,
                    "is_active": is_active,
                    "revenue": revenue,
                }
            )

    df = pd.DataFrame(rows)
    df["cohort_month"] = pd.to_datetime(df["cohort_month"]).dt.to_period("M").dt.to_timestamp()
    df["join_date"] = pd.to_datetime(df["join_date"]).dt.to_period("M").dt.to_timestamp()
    return df


def cohort_sizes(df: pd.DataFrame) -> pd.Series:
    """Number of users per cohort (counted at period 0). Index is a Month PeriodIndex."""
    p0 = df[df["period"] == 0]
    s = p0.groupby("cohort_month")["user_id"].nunique().sort_index()
    s.index = s.index.to_period("M")
    return s


def retention_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Retention rate by cohort (rows) and period (columns), 0..1.

    period 0 is 1.0 by convention. NaN cells = cohort too young to have that period.
    Index is a Month PeriodIndex (so pandas/matplotlib don't need an explicit freq).
    """
    act = df.groupby(["cohort_month", "period"])["is_active"].mean().reset_index()
    mat = act.pivot_table(index="cohort_month", columns="period", values="is_active")
    mat.index = mat.index.to_period("M")
    return mat


def retention_curves(df: pd.DataFrame) -> pd.DataFrame:
    """Mean retention across cohorts for each period (blended retention curve)."""
    return df.groupby("period")["is_active"].mean().rename("retention")


def revenue_by_cohort(df: pd.DataFrame) -> pd.DataFrame:
    """ARPU and total revenue per cohort, cumulatively over all observed periods."""
    g = df.groupby("cohort_month").agg(
        users=("user_id", "nunique"),
        total_revenue=("revenue", "sum"),
        arpu=("revenue", "mean"),
    )
    g.index = g.index.to_period("M")
    g["ltv"] = g["total_revenue"] / g["users"]
    return g


def print_summary(df: pd.DataFrame) -> None:
    print(f"=== Cohort dataset: {df.shape[0]} rows, {df['user_id'].nunique()} users ===")
    print("\n--- Cohort sizes ---")
    print(cohort_sizes(df).to_string())
    print("\n--- Retention matrix (% active) ---")
    print((retention_matrix(df) * 100).round(1).to_string())
    print("\n--- Revenue / LTV by cohort ---")
    print(revenue_by_cohort(df).round(2).to_string())


if __name__ == "__main__":
    print_summary(generate_data())
