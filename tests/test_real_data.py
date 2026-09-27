"""Unit tests: synthetic generator contract + real_data.load_real_data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cohort_analysis import DataConfig, generate_data, retention_matrix
from real_data import CONTRACT, load_real_data


def _write_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "cohort.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_generate_data_is_deterministic() -> None:
    a = generate_data(DataConfig(seed=42))
    b = generate_data(DataConfig(seed=42))
    assert a.equals(b)


def test_retention_period0_is_100_percent() -> None:
    mat = retention_matrix(generate_data())
    assert (mat[0] == 1.0).all()


def test_load_real_data_returns_contract(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path,
        [
            {"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": 10},
            {"user_id": 1, "join_date": "2023-01-15", "period": 1, "is_active": 0, "revenue": 0},
        ],
    )
    df = load_real_data(path)
    assert list(df.columns) == [
        "user_id",
        "cohort_month",
        "join_date",
        "period",
        "is_active",
        "revenue",
    ]
    assert df["cohort_month"].iloc[0] == pd.Timestamp("2023-01-01")
    assert df["is_active"].dtype == "int64"


def test_load_real_data_drops_pii_columns(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path,
        [
            {
                "user_id": 1,
                "join_date": "2023-01-15",
                "period": 0,
                "is_active": 1,
                "revenue": 10,
                "email": "a@b.c",
            }
        ],
    )
    df = load_real_data(path)
    assert "email" not in df.columns


def test_load_real_data_rejects_bad_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        load_real_data(_write_csv(tmp_path, [{"user_id": 1}]))
    with pytest.raises(ValueError, match="is_active"):
        load_real_data(
            _write_csv(
                tmp_path,
                [
                    {
                        "user_id": 1,
                        "join_date": "2023-01-15",
                        "period": 0,
                        "is_active": 2,
                        "revenue": 0,
                    }
                ],
            )
        )
    with pytest.raises(ValueError, match="period"):
        load_real_data(
            _write_csv(
                tmp_path,
                [
                    {
                        "user_id": 1,
                        "join_date": "2023-01-15",
                        "period": -1,
                        "is_active": 1,
                        "revenue": 0,
                    }
                ],
            )
        )
    with pytest.raises(FileNotFoundError):
        load_real_data(tmp_path / "nope.csv")


def test_load_real_data_rejects_duplicate_user_period(tmp_path: Path) -> None:
    rows = [
        {"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": 10},
        {"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": 10},
    ]
    with pytest.raises(ValueError, match="duplicate"):
        load_real_data(_write_csv(tmp_path, rows))


def test_load_real_data_rejects_missing_period_zero(tmp_path: Path) -> None:
    rows = [{"user_id": 1, "join_date": "2023-01-15", "period": 1, "is_active": 1, "revenue": 10}]
    with pytest.raises(ValueError, match="period-0"):
        load_real_data(_write_csv(tmp_path, rows))


def test_load_real_data_rejects_fractional_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-integral"):
        load_real_data(
            _write_csv(
                tmp_path,
                [
                    {
                        "user_id": 1,
                        "join_date": "2023-01-15",
                        "period": 0,
                        "is_active": 1,
                        "revenue": 10.7,
                    }
                ],
            )
        )
    with pytest.raises(ValueError, match="non-integral"):
        load_real_data(
            _write_csv(
                tmp_path,
                [
                    {
                        "user_id": 1,
                        "join_date": "2023-01-15",
                        "period": 0,
                        "is_active": 1.5,
                        "revenue": 10,
                    }
                ],
            )
        )


def test_load_real_data_rejects_non_numeric_value(tmp_path: Path) -> None:
    rows = [
        {"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": "abc"}
    ]
    with pytest.raises(ValueError, match="not numeric") as excinfo:
        load_real_data(_write_csv(tmp_path, rows))
    assert "revenue" in str(excinfo.value)


def test_load_real_data_rejects_unparseable_join_date(tmp_path: Path) -> None:
    rows = [{"user_id": 1, "join_date": "not-a-date", "period": 0, "is_active": 1, "revenue": 0}]
    with pytest.raises(ValueError, match="join_date"):
        load_real_data(_write_csv(tmp_path, rows))


def test_load_real_data_rejects_numeric_join_date(tmp_path: Path) -> None:
    """A YYYYMMDD integer column is the most common export flavour, and pandas
    reads it as nanoseconds since 1970 — every user lands in one cohort."""
    rows = [{"user_id": 1, "join_date": 20230115, "period": 0, "is_active": 1, "revenue": 0}]
    with pytest.raises(ValueError, match="must be a date string") as excinfo:
        load_real_data(_write_csv(tmp_path, rows))
    assert "join_date" in str(excinfo.value)


def test_load_real_data_rejects_blank_join_date(tmp_path: Path) -> None:
    """A blank date becomes NaT and would silently drop the user from every
    cohort denominator instead of failing."""
    rows = [
        {"user_id": 1, "join_date": "", "period": 0, "is_active": 1, "revenue": 0},
        {"user_id": 2, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": 0},
    ]
    with pytest.raises(ValueError, match="join_date") as excinfo:
        load_real_data(_write_csv(tmp_path, rows))
    assert "missing" in str(excinfo.value)
    # An entirely blank column is read as float64, so the missing-value check
    # must run before the numeric-dtype check or the error blames integer input.
    all_blank = [{"user_id": 1, "join_date": "", "period": 0, "is_active": 1, "revenue": 0}]
    with pytest.raises(ValueError, match="missing") as excinfo:
        load_real_data(_write_csv(tmp_path, all_blank))
    assert "not a number" not in str(excinfo.value)


def test_load_real_data_rejects_blank_numeric_cell(tmp_path: Path) -> None:
    """A blank cell must name the file and column, not surface a pandas
    IntCastingNaNError."""
    rows = [
        {"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": 10},
        {"user_id": 1, "join_date": "2023-01-15", "period": 1, "is_active": 1, "revenue": ""},
    ]
    with pytest.raises(ValueError, match="revenue") as excinfo:
        load_real_data(_write_csv(tmp_path, rows))
    assert str(tmp_path) in str(excinfo.value)


def test_missing_column_error_names_the_path(tmp_path: Path) -> None:
    rows = [{"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1}]
    with pytest.raises(ValueError, match="missing required columns") as excinfo:
        load_real_data(_write_csv(tmp_path, rows))
    assert str(tmp_path) in str(excinfo.value)


def test_load_real_data_rejects_negative_revenue(tmp_path: Path) -> None:
    rows = [{"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": -5}]
    with pytest.raises(ValueError, match="revenue"):
        load_real_data(_write_csv(tmp_path, rows))


def test_load_real_data_happy_path(tmp_path: Path) -> None:
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
    df = load_real_data(_write_csv(tmp_path, rows))
    assert list(df.columns) == CONTRACT
    assert df["period"].tolist() == [0, 1, 2, 0, 1, 2]
    assert df["cohort_month"].tolist() == [pd.Timestamp("2023-03-01")] * 6
    assert df["join_date"].tolist() == [pd.Timestamp("2023-03-01")] * 6
    for col in ("user_id", "period", "is_active", "revenue"):
        assert df[col].dtype == "int64"
