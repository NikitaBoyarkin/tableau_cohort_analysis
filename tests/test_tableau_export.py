"""Unit tests: tableau_export build/write contract (synthetic + real data)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import tableau_export
from real_data import load_real_data
from tableau_export import (
    EXPORT_COLUMNS,
    build_export_frame,
    write_csv,
    write_hyper,
)


def _write_clean_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a user-period CSV honouring real_data's validation rules."""
    path = tmp_path / "cohort.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def real_frame(tmp_path: Path) -> pd.DataFrame:
    """A small real-data frame: 2 users x 3 periods, one row per (user, period)."""
    rows = [
        {
            "user_id": user_id,
            "join_date": "2023-03-05",
            "period": period,
            "is_active": 1 if period == 0 else 0,
            "revenue": 5 if period == 0 else 0,
        }
        for user_id in (1, 2)
        for period in range(3)
    ]
    return load_real_data(_write_clean_csv(tmp_path, rows))


def test_output_columns_and_order(real_frame: pd.DataFrame) -> None:
    out = build_export_frame(df=real_frame)
    assert list(out.columns) == EXPORT_COLUMNS
    assert EXPORT_COLUMNS == [
        "user_id",
        "cohort_month",
        "cohort_label",
        "join_date",
        "period",
        "period_date",
        "is_active",
        "revenue",
    ]


def test_default_build_uses_synthetic_data() -> None:
    out = build_export_frame()
    assert list(out.columns) == EXPORT_COLUMNS
    assert len(out) > 0
    assert out["user_id"].nunique() == 1000


def test_accepts_real_data_frame(real_frame: pd.DataFrame) -> None:
    out = build_export_frame(df=real_frame)
    assert list(out.columns) == EXPORT_COLUMNS
    assert (out["cohort_label"] == out["cohort_month"].dt.strftime("%Y-%m")).all()
    assert out["cohort_label"].unique().tolist() == ["2023-03"]
    for col in ("user_id", "period", "is_active", "revenue"):
        assert out[col].dtype == "int64"


def test_period_date_is_join_month_plus_period(real_frame: pd.DataFrame) -> None:
    out = build_export_frame(df=real_frame)
    for _, row in out.iterrows():
        assert row["join_date"] == pd.Timestamp("2023-03-01")
        expected = pd.Timestamp("2023-03-01") + pd.DateOffset(months=int(row["period"]))
        assert row["period_date"] == expected
    # At least one multi-period row beyond period 0 was checked.
    assert (out["period"] > 0).any()
    assert out.loc[out["period"] == 2, "period_date"].iloc[0] == pd.Timestamp("2023-05-01")


def test_large_revenue_survives_without_overflow(tmp_path: Path) -> None:
    rows = [
        {
            "user_id": 1,
            "join_date": "2023-01-10",
            "period": 0,
            "is_active": 1,
            "revenue": 3_000_000_000,
        },
        {"user_id": 1, "join_date": "2023-01-10", "period": 1, "is_active": 1, "revenue": 0},
    ]
    out = build_export_frame(df=load_real_data(_write_clean_csv(tmp_path, rows)))
    assert out["revenue"].iloc[0] == 3_000_000_000
    assert int(out["revenue"].iloc[0]) > 0
    assert out["revenue"].dtype == "int64"


def test_missing_required_column_raises(real_frame: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="revenue"):
        build_export_frame(df=real_frame.drop(columns=["revenue"]))
    with pytest.raises(ValueError, match="missing required columns"):
        build_export_frame(df=pd.DataFrame({"user_id": [1]}))


def test_write_csv_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tableau_export, "EXPORT_DIR", tmp_path)
    out = build_export_frame()
    path = write_csv(out)
    assert path.exists()
    back = pd.read_csv(path)
    assert back.shape == out.shape
    assert list(back.columns) == EXPORT_COLUMNS


def test_write_hyper_raises_on_nan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The NaN guard runs before the optional import, so it always raises."""
    monkeypatch.setattr(tableau_export, "EXPORT_DIR", tmp_path)
    out = build_export_frame()
    out.loc[out.index[0], "revenue"] = float("nan")
    with pytest.raises(ValueError, match="revenue"):
        write_hyper(out)


def test_write_hyper_rejects_column_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("tableauhyperapi")
    monkeypatch.setattr(tableau_export, "EXPORT_DIR", tmp_path)
    out = build_export_frame().rename(columns={"revenue": "revenue_usd"})
    with pytest.raises(ValueError, match="revenue_usd"):
        write_hyper(out)
