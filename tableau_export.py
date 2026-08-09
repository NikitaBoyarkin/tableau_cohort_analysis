"""Export the synthetic cohort dataset to Tableau-ready artifacts.

Produces, under ./tableau/:
    cohort_export.csv   - denormalized one-row-per-user-period table, the best
                          shape for a Tableau cohort retention view.
    cohort_extract.hyper - a Tableau Hyper extract built from the same table
                          (load it via "Connect to Data" -> Tableau Extract).

The CSV is sufficient on its own. The .hyper extract avoids re-typing in
Tableau Desktop and is built with the official Tableau Hyper API.

    uv run python tableau_export.py
"""

from __future__ import annotations

import pathlib

import pandas as pd

from cohort_analysis import DataConfig, generate_data

EXPORT_DIR = pathlib.Path(__file__).parent / "tableau"


def build_export_frame(cfg: DataConfig | None = None) -> pd.DataFrame:
    df = generate_data(cfg)
    # Actual calendar month of each user-period observation (join_month + period).
    # Vectorized month math on datetime64[M] (no per-row DateOffset object dtype).
    jm = df["join_date"].to_numpy().astype("datetime64[M]")
    period_date = pd.to_datetime(pd.Series(jm + df["period"].to_numpy().astype("timedelta64[M]")))
    out = pd.DataFrame(
        {
            "user_id": df["user_id"].astype("int32"),
            "cohort_month": pd.to_datetime(df["cohort_month"]).dt.to_period("M").dt.to_timestamp(),
            "cohort_label": df["cohort_month"].dt.strftime("%Y-%m"),
            "join_date": pd.to_datetime(df["join_date"]).dt.normalize(),
            "period": df["period"].astype("int8"),
            "period_date": pd.to_datetime(period_date).dt.normalize(),
            "is_active": df["is_active"].astype("int8"),
            "revenue": df["revenue"].astype("int32"),
        }
    )
    return out


def write_csv(df: pd.DataFrame) -> pathlib.Path:
    EXPORT_DIR.mkdir(exist_ok=True)
    path = EXPORT_DIR / "cohort_export.csv"
    df.to_csv(path, index=False, date_format="%Y-%m-%d")
    return path


def write_hyper(df: pd.DataFrame) -> pathlib.Path | None:
    """Build a .hyper extract. Returns the path, or None if the API is unavailable."""
    try:
        from tableauhyperapi import (
            Connection,
            CreateMode,
            HyperProcess,
            Inserter,
            SqlType,
            TableDefinition,
            TableName,
        )
    except ImportError as exc:
        print(f"[skip] .hyper export unavailable: {exc}")
        return None

    EXPORT_DIR.mkdir(exist_ok=True)
    hyper_path = EXPORT_DIR / "cohort_extract.hyper"
    if hyper_path.exists():
        hyper_path.unlink()

    table_def = TableDefinition(TableName("cohort", "cohort_export"))
    table_def.add_column("user_id", SqlType.big_int())
    table_def.add_column("cohort_month", SqlType.date())
    table_def.add_column("cohort_label", SqlType.text())
    table_def.add_column("join_date", SqlType.date())
    table_def.add_column("period", SqlType.small_int())
    table_def.add_column("period_date", SqlType.date())
    table_def.add_column("is_active", SqlType.small_int())
    table_def.add_column("revenue", SqlType.big_int())

    telemetry = "tableau"  # send usage telemetry to Tableau (default); use "false" to opt out
    with HyperProcess(telemetry=telemetry) as hyper:
        with Connection(
            hyper.endpoint, str(hyper_path), CreateMode.CREATE
        ) as conn:
            conn.catalog.create_schema("cohort")
            conn.catalog.create_table(table_def)
            with Inserter(conn, table_def) as inserter:
                for row in df.itertuples(index=False, name=None):
                    inserter.add_row(list(row))
                inserter.execute()

    return hyper_path


def main() -> None:
    df = build_export_frame()
    csv_path = write_csv(df)
    print(f"CSV  -> {csv_path}  ({len(df)} rows)")
    hyper_path = write_hyper(df)
    if hyper_path:
        print(f"Hyper -> {hyper_path}")


if __name__ == "__main__":
    main()
