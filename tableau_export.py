"""Export a cohort dataset to Tableau-ready artifacts.

Produces, under ./tableau/:
    cohort_export.csv   - denormalized one-row-per-user-period table, the best
                          shape for a Tableau cohort retention view.
    cohort_extract.hyper - a Tableau Hyper extract built from the same table
                          (load it via "Connect to Data" -> Tableau Extract).

The CSV is sufficient on its own. The .hyper extract avoids re-typing in
Tableau Desktop and is built with the official Tableau Hyper API.

Input: either the synthetic generator (default) or any DataFrame that follows
the 6-column user-period contract produced by ``real_data.load_real_data``
(``user_id, cohort_month, join_date, period, is_active, revenue``). Swapping
the source is a single argument:

    from real_data import load_real_data
    from tableau_export import build_export_frame, main

    df = build_export_frame(load_real_data("cohort_data.csv"))

    uv run python tableau_export.py
"""

from __future__ import annotations

import pathlib

import pandas as pd

from cohort_analysis import DataConfig, generate_data

EXPORT_DIR = pathlib.Path(__file__).parent / "tableau"

# Columns required from the caller-supplied frame (the real_data contract).
REQUIRED_INPUT_COLUMNS = [
    "user_id",
    "cohort_month",
    "join_date",
    "period",
    "is_active",
    "revenue",
]

# Exact output contract; consumers (Tableau workbook, notebook) rely on names
# and order. Kept in sync with the Hyper table definition below.
EXPORT_COLUMNS = [
    "user_id",
    "cohort_month",
    "cohort_label",
    "join_date",
    "period",
    "period_date",
    "is_active",
    "revenue",
]

# (column name, Hyper type) in table-definition order.
HYPER_SCHEMA = [
    ("user_id", "big_int"),
    ("cohort_month", "date"),
    ("cohort_label", "text"),
    ("join_date", "date"),
    ("period", "big_int"),
    ("period_date", "date"),
    ("is_active", "big_int"),
    ("revenue", "big_int"),
]


def build_export_frame(
    df: pd.DataFrame | None = None, cfg: DataConfig | None = None
) -> pd.DataFrame:
    """Build the denormalized Tableau export frame.

    Args:
        df: A frame following the 6-column user-period contract. ``None``
            (the default) generates synthetic data via ``generate_data``.
        cfg: Synthetic-generator config; only used when ``df`` is None.

    Returns:
        A frame with exactly ``EXPORT_COLUMNS`` in order. Integer columns are
        ``int64`` (no lossy narrowing) and date columns are month-aligned.
    """
    if df is None:
        df = generate_data(cfg)

    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"input frame is missing required columns: {missing}")

    # Month-aligned dates: join_date / cohort_month collapse to the 1st of their month.
    join_month = pd.to_datetime(df["join_date"]).dt.to_period("M").dt.to_timestamp()
    cohort_month = pd.to_datetime(df["cohort_month"]).dt.to_period("M").dt.to_timestamp()
    period = df["period"].astype("int64")

    # Calendar month of each observation = join month + period months.
    # Vectorized month math on datetime64[M] arrays (no per-row DateOffset objects).
    join_m = join_month.to_numpy().astype("datetime64[M]")
    period_m = period.to_numpy().astype("timedelta64[M]")
    period_date = pd.Series(pd.to_datetime(join_m + period_m).to_numpy(), index=df.index)

    out = pd.DataFrame(
        {
            "user_id": df["user_id"].astype("int64"),
            "cohort_month": cohort_month,
            "cohort_label": cohort_month.dt.strftime("%Y-%m"),
            "join_date": join_month,
            "period": period,
            "period_date": period_date,
            "is_active": df["is_active"].astype("int64"),
            "revenue": df["revenue"].astype("int64"),
        },
        index=df.index,
    )
    return out[EXPORT_COLUMNS]


def write_csv(df: pd.DataFrame) -> pathlib.Path:
    """Write the export frame to ./tableau/cohort_export.csv."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / "cohort_export.csv"
    df.to_csv(path, index=False, date_format="%Y-%m-%d")
    return path


def write_hyper(df: pd.DataFrame) -> pathlib.Path | None:
    """Build a .hyper extract. Returns the path, or None if the API is unavailable."""
    offending = [col for col in df.columns if df[col].isna().any()]
    if offending:
        raise ValueError(
            f"cannot write a .hyper extract: NaN values in column(s) {offending}; "
            "fill or drop them before exporting"
        )

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

    sql_types = {
        "big_int": SqlType.big_int,
        "date": SqlType.date,
        "text": SqlType.text,
    }
    table_def = TableDefinition(TableName("cohort", "cohort_export"))
    for column, type_name in HYPER_SCHEMA:
        table_def.add_column(column, sql_types[type_name]())

    # Fail loudly on a schema drift instead of letting the Inserter raise an
    # opaque type error. Checked before the Hyper process is started.
    table_columns = [col.name.unescaped for col in table_def.columns]
    if list(df.columns) != table_columns:
        raise ValueError(
            f"DataFrame columns {list(df.columns)} do not match table definition "
            f"columns {table_columns}"
        )

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    hyper_path = EXPORT_DIR / "cohort_extract.hyper"
    if hyper_path.exists():
        hyper_path.unlink()

    telemetry = "false"  # opt out of sending usage telemetry to Tableau
    with HyperProcess(telemetry=telemetry) as hyper:
        with Connection(hyper.endpoint, str(hyper_path), CreateMode.CREATE) as conn:
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
