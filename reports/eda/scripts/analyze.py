"""EDA analysis for tableau_cohort_analysis — reproducibility of README claims.

Reads cohort_data.csv (one row per user-month), validates the 6-column contract,
reproduces the retention matrix / blended curve / LTV, checks the seed=42
determinism claim, and prints a machine-readable block for the report.

Run:
    /Users/nikitaboarkin/Desktop/00 ide/00 portfolio/.eda-tools/.venv/bin/python \
        reports/eda/scripts/analyze.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[3]
DATA = PROJECT / "cohort_data.csv"
OUT = PROJECT / "reports" / "eda" / "scripts" / "_analysis.json"

# Make cohort_analysis importable for the determinism check.
sys.path.insert(0, str(PROJECT))
import cohort_analysis as ca  # noqa: E402

results: dict = {}


def main() -> None:
    df = pd.read_csv(DATA)
    df["cohort_month"] = pd.to_datetime(df["cohort_month"])
    df["join_date"] = pd.to_datetime(df["join_date"])

    # ---------------------------------------------------------------- structure
    results["shape"] = list(df.shape)
    results["columns"] = list(df.columns)
    results["users"] = int(df["user_id"].nunique())
    results["cohorts"] = int(df["cohort_month"].nunique())
    results["period_min"] = int(df["period"].min())
    results["period_max"] = int(df["period"].max())
    results["join_date_range"] = [
        str(df["join_date"].min().date()),
        str(df["join_date"].max().date()),
    ]

    # ------------------------------------------------------------ validity (contract)
    checks: dict[str, object] = {}
    checks["is_active_in_0_1"] = bool(df["is_active"].isin([0, 1]).all())
    checks["period_non_negative"] = bool((df["period"] >= 0).all())
    checks["revenue_non_negative"] = bool((df["revenue"] >= 0).all())
    checks["all_integer"] = bool(
        all(
            pd.api.types.is_integer_dtype(df[c])
            for c in ["user_id", "period", "is_active", "revenue"]
        )
    )
    checks["no_full_dup_rows"] = bool(df.duplicated().sum() == 0)
    checks["no_dup_user_period"] = bool(df.duplicated(["user_id", "period"]).sum() == 0)
    # exactly one period-0 row per user
    p0 = df[df["period"] == 0].groupby("user_id").size()
    checks["exactly_one_period0_per_user"] = bool(
        (p0 == 1).all() and len(p0) == df["user_id"].nunique()
    )
    # cohort_month derived from join_date (equal)
    checks["cohort_month_eq_join_date"] = bool((df["cohort_month"] == df["join_date"]).all())
    # join_date is first-of-month
    checks["join_date_is_month_start"] = bool((df["join_date"].dt.day == 1).all())
    # revenue == 0 iff is_active == 0
    checks["revenue_zero_iff_inactive"] = bool(
        ((df["revenue"] == 0) == (df["is_active"] == 0)).all()
    )
    # triangular window: periods per cohort = 10 - cohort_index
    results["max_periods_per_cohort"] = (
        df.groupby("cohort_month")["period"].max().astype(int).to_dict().__str__()
    )
    results["validity_checks"] = checks

    # ---------------------------------------------------------- period-0 convention
    p0_rate = float(df.loc[df["period"] == 0, "is_active"].mean())
    results["period0_retention"] = p0_rate

    # ----------------------------------------------------------- cohort sizes (flow)
    sizes = ca.cohort_sizes(df)
    results["cohort_sizes"] = {str(k): int(v) for k, v in sizes.items()}
    results["cohort_size_total"] = int(sizes.sum())

    # -------------------------------------------------------- retention matrix
    mat = ca.retention_matrix(df)
    results["retention_matrix"] = {
        str(idx): {int(c): (None if pd.isna(v) else round(float(v), 4)) for c, v in row.items()}
        for idx, row in mat.iterrows()
    }

    # blended curve + theoretical formula 0.85 * 0.75^(p-1)
    curve = ca.retention_curves(df)
    theo = {
        p: (1.0 if p == 0 else 0.85 * 0.75 ** (p - 1)) for p in range(int(df["period"].max()) + 1)
    }
    results["blended_curve"] = {int(k): round(float(v), 4) for k, v in curve.items()}
    results["theoretical_curve"] = {k: round(v, 4) for k, v in theo.items()}
    results["curve_abs_diff"] = {
        int(k): round(abs(float(curve[k]) - theo[int(k)]), 4) for k in curve.index
    }

    # ------------------------------------------------------------- revenue / LTV
    rev = ca.revenue_by_cohort(df)
    results["revenue_by_cohort"] = {
        str(idx): {c: (None if pd.isna(v) else round(float(v), 4)) for c, v in row.items()}
        for idx, row in rev.iterrows()
    }
    ltv3 = ca.ltv_at_k(df, 3)
    results["ltv_at_k3"] = {
        str(k): (None if pd.isna(v) else round(float(v), 4)) for k, v in ltv3.items()
    }
    results["ltv_at_k3_mean"] = (
        None if ltv3.dropna().empty else round(float(ltv3.dropna().mean()), 4)
    )
    results["ltv_at_k3_n_defined"] = int(ltv3.notna().sum())
    results["total_revenue"] = int(df["revenue"].sum())
    results["revenue_active_mean"] = round(float(df.loc[df["is_active"] == 1, "revenue"].mean()), 4)
    results["revenue_active_median"] = float(df.loc[df["is_active"] == 1, "revenue"].median())
    results["revenue_zero_share"] = round(float((df["revenue"] == 0).mean()), 4)

    # ------------------------------------------------- determinism check (seed=42)
    regen = ca.generate_data(ca.DataConfig(seed=42))
    regen["cohort_month"] = pd.to_datetime(regen["cohort_month"])
    regen["join_date"] = pd.to_datetime(regen["join_date"])
    same_shape = regen.shape == df.shape
    same_content = same_shape and regen.reset_index(drop=True).equals(df.reset_index(drop=True))
    results["regen_shape"] = list(regen.shape)
    results["seed42_reproduces_csv"] = bool(same_content)

    # --------------------------------------- retention formula fit (log-linear)
    # observed retention p>=1 vs 0.85*0.75^(p-1): fit log(obs) = a + b*(p-1)
    obs = curve[curve.index >= 1].astype(float)
    x = (obs.index.to_numpy() - 1).astype(float)
    y = np.log(obs.to_numpy())
    b, a = np.polyfit(x, y, 1)
    results["formula_fit"] = {
        "base_retention_exp_a": round(float(np.exp(a)), 4),
        "decay_exp_b": round(float(np.exp(b)), 4),
        "r_squared": round(float(np.corrcoef(x, y)[0, 1] ** 2), 4),
    }

    # --------------------------------------------------- table count sanity
    results["tests"] = _count_tests(PROJECT / "tests")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps(results, indent=2, ensure_ascii=False))


def _count_tests(tests_dir: Path) -> dict:
    import re

    out: dict[str, int] = {}
    for f in sorted(tests_dir.glob("test_*.py")):
        n = len(re.findall(r"^\s*def test_", f.read_text(), flags=re.M))
        out[f.name] = n
    out["total"] = sum(out.values())
    return out


if __name__ == "__main__":
    main()
