"""Tests for cohort_analysis metric correctness (cohort_sizes, retention, LTV)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cohort_analysis import (
    BASE_DATE,
    DataConfig,
    cohort_sizes,
    generate_data,
    ltv_at_k,
    retention_curves,
    retention_matrix,
    revenue_by_cohort,
)

NUM_USERS = 200
NUM_COHORTS = 5
MAX_PERIODS = 4


@pytest.fixture()
def cfg() -> DataConfig:
    """Small, fast, deterministic dataset with a triangular observation window."""
    return DataConfig(
        num_users=NUM_USERS, num_cohorts=NUM_COHORTS, max_periods=MAX_PERIODS, seed=7
    )


@pytest.fixture()
def df(cfg: DataConfig) -> pd.DataFrame:
    return generate_data(cfg)


# --- generate_data invariants ------------------------------------------------


def test_generate_data_invariants(df: pd.DataFrame, cfg: DataConfig) -> None:
    # No revenue without activity.
    assert (df.loc[df["is_active"] == 0, "revenue"] == 0).all()
    assert df["revenue"].min() >= 0

    # Exactly one period-0 row per user, and period 0 is always active.
    p0 = df[df["period"] == 0]
    assert len(p0) == cfg.num_users
    assert df["user_id"].nunique() == cfg.num_users
    assert p0.groupby("user_id").size().eq(1).all()
    assert (p0["is_active"] == 1).all()


def test_generate_data_triangular_window(df: pd.DataFrame, cfg: DataConfig) -> None:
    """Observed periods per cohort == min(max_periods, num_cohorts - cohort_index)."""
    observed = df.groupby("cohort_month")["period"].nunique()
    for cohort_month, n_periods in observed.items():
        cohort_index = (
            (pd.Timestamp(cohort_month).year - BASE_DATE.year) * 12
            + pd.Timestamp(cohort_month).month
            - BASE_DATE.month
        )
        expected = min(cfg.max_periods, cfg.num_cohorts - cohort_index)
        assert n_periods == expected

    # Periods are contiguous from 0.
    for _, grp in df.groupby("cohort_month"):
        assert sorted(grp["period"].unique()) == list(range(grp["period"].nunique()))


# --- cohort_sizes ------------------------------------------------------------


def test_cohort_sizes_counts_unique_period_0_users(df: pd.DataFrame) -> None:
    sizes = cohort_sizes(df)
    expected = (
        df[df["period"] == 0].groupby("cohort_month")["user_id"].nunique().sort_index()
    )
    expected.index = expected.index.to_period("M")
    pd.testing.assert_series_equal(sizes, expected)
    assert sizes.sum() == df["user_id"].nunique()
    assert isinstance(sizes.index, pd.PeriodIndex)


def test_cohort_sizes_raises_without_period_0(df: pd.DataFrame) -> None:
    late = df[df["period"] > 0]
    with pytest.raises(ValueError, match="no period-0 rows"):
        cohort_sizes(late)


# --- retention_curves / retention_matrix -------------------------------------


def test_retention_curves_is_row_weighted_mean(df: pd.DataFrame) -> None:
    curves = retention_curves(df)
    expected = df.groupby("period")["is_active"].mean()
    pd.testing.assert_series_equal(curves, expected.rename("retention"))
    assert curves.name == "retention"
    # Period 0 is 100% active by convention, so the blend is exactly 1.0.
    assert curves.loc[0] == 1.0
    assert curves.between(0.0, 1.0).all()


def test_retention_matrix_is_triangular(df: pd.DataFrame, cfg: DataConfig) -> None:
    mat = retention_matrix(df)
    assert isinstance(mat.index, pd.PeriodIndex)
    assert mat.index.name == "cohort_month"
    assert list(mat.columns) == list(range(cfg.max_periods))

    # Cells the cohort never reached are NaN (present, not dropped).
    for cohort_month in mat.index:
        n_periods = df.loc[df["cohort_month"] == cohort_month.to_timestamp(), "period"].nunique()
        row = mat.loc[cohort_month]
        assert row.iloc[:n_periods].notna().all()
        assert row.iloc[n_periods:].isna().all()

    # Oldest cohort has the full window; newest cohort only period 0.
    assert mat.iloc[0, : cfg.max_periods].notna().all()
    assert mat.iloc[0, 0] == 1.0
    assert mat.iloc[-1].iloc[1:].isna().all()


# --- revenue_by_cohort -------------------------------------------------------


def test_revenue_by_cohort_columns_and_order(df: pd.DataFrame) -> None:
    rev = revenue_by_cohort(df)
    assert list(rev.columns) == ["users", "total_revenue", "arpu_monthly", "periods", "ltv"]
    assert isinstance(rev.index, pd.PeriodIndex)
    assert rev.index.name == "cohort_month"


def test_revenue_by_cohort_metric_definitions(df: pd.DataFrame) -> None:
    rev = revenue_by_cohort(df)
    grouped = df.groupby("cohort_month")
    row_count = grouped.size()
    users = grouped["user_id"].nunique()
    total_revenue = grouped["revenue"].sum()
    index = pd.PeriodIndex(users.index, freq="M", name="cohort_month")

    pd.testing.assert_series_equal(rev["users"], users.set_axis(index).rename("users"))
    pd.testing.assert_series_equal(
        rev["total_revenue"], total_revenue.set_axis(index).rename("total_revenue")
    )

    # arpu_monthly is revenue per user-MONTH row, not per user.
    expected_arpu = (total_revenue / row_count).set_axis(index)
    pd.testing.assert_series_equal(rev["arpu_monthly"], expected_arpu.rename("arpu_monthly"))

    expected_periods = (row_count / users).set_axis(index)
    pd.testing.assert_series_equal(rev["periods"], expected_periods.rename("periods"))

    expected_ltv = (total_revenue / users).set_axis(index)
    pd.testing.assert_series_equal(rev["ltv"], expected_ltv.rename("ltv"))

    # The artifact the label was hiding: ltv == arpu_monthly * periods.
    pd.testing.assert_series_equal(
        rev["ltv"], (rev["arpu_monthly"] * rev["periods"]).rename("ltv")
    )


def test_revenue_by_cohort_users_matches_cohort_sizes(df: pd.DataFrame) -> None:
    rev = revenue_by_cohort(df)
    sizes = cohort_sizes(df)
    pd.testing.assert_series_equal(rev["users"], sizes.reindex(rev.index).rename("users"))


# --- ltv_at_k ----------------------------------------------------------------


def test_ltv_at_k_matches_manual_cumulative_revenue_per_user(df: pd.DataFrame) -> None:
    k = 3
    result = ltv_at_k(df, k)
    assert result.name == "ltv_at_k"
    assert isinstance(result.index, pd.PeriodIndex)
    assert result.index.name == "cohort_month"

    window = df[df["period"] < k]
    manual = window.groupby("cohort_month").apply(
        lambda g: g["revenue"].sum() / g["user_id"].nunique(), include_groups=False
    )
    observed = window.groupby("cohort_month")["period"].nunique()
    expected = manual.where(observed >= k)
    expected.index = expected.index.to_period("M")
    expected.name = "ltv_at_k"

    pd.testing.assert_series_equal(result, expected)


def test_ltv_at_k_excludes_young_cohorts(df: pd.DataFrame, cfg: DataConfig) -> None:
    result = ltv_at_k(df, 3)
    observed = df.groupby("cohort_month")["period"].nunique()
    assert len(result) == cfg.num_cohorts

    for cohort_month, n_periods in observed.items():
        key = pd.Period(cohort_month, freq="M")
        if n_periods >= 3:
            assert pd.notna(result.loc[key])
            assert result.loc[key] > 0
        else:
            assert np.isnan(result.loc[key])

    # With num_cohorts=5, max_periods=4 the windows are 4,4,3,2,1 periods, so
    # cohorts 0-2 reach period 2 and the youngest two are excluded.
    assert list(observed.values) == [4, 4, 3, 2, 1]
    assert result.notna().sum() == 3
    assert result.isna().sum() == 2


def test_ltv_at_k_rejects_non_positive_k(df: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="k must be an integer >= 1"):
        ltv_at_k(df, 0)
    with pytest.raises(ValueError, match="k must be an integer >= 1"):
        ltv_at_k(df, -1)


def test_ltv_at_k_rejects_fractional_k(df: pd.DataFrame) -> None:
    """k=4.5 and k=99 both returned a silently meaningless series before."""
    with pytest.raises(ValueError, match="k must be an integer >= 1"):
        ltv_at_k(df, 4.5)


def test_ltv_at_k_differs_from_age_dependent_ltv(df: pd.DataFrame) -> None:
    """ltv_at_k removes the cohort-age artifact that revenue_by_cohort's ltv has."""
    rev = revenue_by_cohort(df)
    comparable = ltv_at_k(df, 3).dropna()
    assert comparable.index.isin(rev.index).all()
    # Oldest cohort's cumulative LTV spans 4 periods, so it exceeds its LTV@3.
    oldest = comparable.index[0]
    assert rev.loc[oldest, "periods"] > 3
    assert rev.loc[oldest, "ltv"] > comparable.loc[oldest]
