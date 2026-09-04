"""Unit tests: synthetic generator contract + real_data.load_real_data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cohort_analysis import DataConfig, generate_data, retention_matrix
from real_data import load_real_data


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
    assert list(df.columns) == ["user_id", "cohort_month", "join_date", "period", "is_active", "revenue"]
    assert df["cohort_month"].iloc[0] == pd.Timestamp("2023-01-01")
    assert df["is_active"].dtype == "int64"


def test_load_real_data_drops_pii_columns(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path,
        [{"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 1, "revenue": 10, "email": "a@b.c"}],
    )
    df = load_real_data(path)
    assert "email" not in df.columns


def test_load_real_data_rejects_bad_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        load_real_data(_write_csv(tmp_path, [{"user_id": 1}]))
    with pytest.raises(ValueError, match="is_active"):
        load_real_data(
            _write_csv(tmp_path, [{"user_id": 1, "join_date": "2023-01-15", "period": 0, "is_active": 2, "revenue": 0}])
        )
    with pytest.raises(ValueError, match="period"):
        load_real_data(
            _write_csv(tmp_path, [{"user_id": 1, "join_date": "2023-01-15", "period": -1, "is_active": 1, "revenue": 0}])
        )
    with pytest.raises(FileNotFoundError):
        load_real_data(tmp_path / "nope.csv")
