"""Figures for tableau_cohort_analysis EDA — light theme, OO style, PNG 300dpi.

Run:
    /Users/nikitaboarkin/Desktop/00 ide/00 portfolio/.eda-tools/.venv/bin/python \
        reports/eda/scripts/plot_figures.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

warnings.filterwarnings("ignore")
plt.rcParams.update(
    {
        "font.family": ["DejaVu Sans", "sans-serif"],
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)

PROJECT = Path(__file__).resolve().parents[3]
DATA = PROJECT / "cohort_data.csv"
FIG = PROJECT / "reports" / "eda" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PROJECT))
import cohort_analysis as ca  # noqa: E402


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df["cohort_month"] = pd.to_datetime(df["cohort_month"])
    df["join_date"] = pd.to_datetime(df["join_date"])
    return df


def fig1_revenue_distribution(df: pd.DataFrame) -> None:
    fig, axs = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")

    axs[0].hist(
        df["revenue"],
        bins=range(0, int(df["revenue"].max()) + 2),
        color="#4C72B0",
        edgecolor="white",
    )
    axs[0].set(
        xlabel="Monthly revenue (all user-months)",
        ylabel="User-months",
        title=f"Revenue is zero-inflated — {df['revenue'].eq(0).mean():.1%} are inactive months",
    )
    axs[0].grid(axis="y", alpha=0.3)

    active = df.loc[df["is_active"] == 1, "revenue"]
    axs[1].hist(active, bins=range(0, int(active.max()) + 2), color="#55A868", edgecolor="white")
    axs[1].set(
        xlabel="Monthly revenue (active user-months only)",
        ylabel="Active user-months",
        title=f"Active months: mean {active.mean():.2f}, median {active.median():.0f} (Poisson-like)",
    )
    axs[1].grid(axis="y", alpha=0.3)

    fig.suptitle("Fig 1 — Distribution of the revenue metric", fontsize=13)
    fig.savefig(FIG / "fig1_revenue_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig2_cohort_sizes(df: pd.DataFrame) -> None:
    sizes = ca.cohort_sizes(df)
    labels = [str(p) for p in sizes.index]
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    bars = ax.bar(labels, sizes.to_numpy(), color="#4C72B0", edgecolor="black")
    ax.axhline(
        sizes.mean(),
        color="#C44E52",
        linestyle="--",
        linewidth=1.5,
        label=f"mean = {sizes.mean():.1f}",
    )
    ax.bar_label(bars, fmt="%d", padding=2, fontsize=9)
    ax.set(
        xlabel="Cohort month (join month)",
        ylabel="Users (period-0 rows)",
        title="Fig 2 — Cohort sizes: acquisition is roughly uniform across 10 months",
    )
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.savefig(FIG / "fig2_cohort_sizes.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig3_retention_curve(df: pd.DataFrame) -> None:
    curve = ca.retention_curves(df)
    p = curve.index.to_numpy()
    theo = np.array([1.0 if x == 0 else 0.85 * 0.75 ** (x - 1) for x in p])
    fig, ax = plt.subplots(figsize=(10, 5.5), layout="constrained")
    ax.plot(
        p,
        curve.to_numpy(),
        marker="o",
        linewidth=2,
        color="#4C72B0",
        label="Observed blended retention",
    )
    ax.plot(
        p,
        theo,
        linestyle="--",
        linewidth=2,
        color="#C44E52",
        label=r"Theory: $0.85 \cdot 0.75^{\,p-1}$",
    )
    for x, y in zip(p, curve.to_numpy()):
        if x > 0:
            ax.annotate(
                f"{y:.1%}",
                (x, y),
                textcoords="offset points",
                xytext=(0, 8),
                fontsize=8,
                ha="center",
            )
    ax.set(
        xlabel="Period (months since join)",
        ylabel="Retention (share active)",
        title="Fig 3 — Blended retention tracks the generative formula (period 0 = 100% by convention)",
    )
    ax.set_ylim(0, 1.08)
    ax.legend(frameon=False)
    ax.grid(alpha=0.3)
    fig.savefig(FIG / "fig3_retention_curve.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig4_retention_heatmap(df: pd.DataFrame) -> None:
    mat = ca.retention_matrix(df)
    data = mat.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(11, 5.5), layout="constrained")
    im = ax.imshow(data, cmap="viridis", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(mat.shape[1]), [str(c) for c in mat.columns])
    ax.set_yticks(range(mat.shape[0]), [str(i) for i in mat.index])
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if not np.isnan(data[i, j]):
                ax.text(
                    j,
                    i,
                    f"{data[i, j]:.0%}",
                    ha="center",
                    va="center",
                    color="white" if data[i, j] < 0.55 else "black",
                    fontsize=8,
                )
    ax.set(
        xlabel="Period (months since join)",
        ylabel="Cohort month",
        title="Fig 4 — Retention matrix (cohort x period), triangular by observation window",
    )
    cbar = fig.colorbar(im, ax=ax, shrink=0.9)
    cbar.set_label("Retention")
    fig.savefig(FIG / "fig4_retention_heatmap.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig5_ltv_at_k3(df: pd.DataFrame) -> None:
    ltv = ca.ltv_at_k(df, 3)
    labels = [str(p) for p in ltv.index]
    vals = ltv.to_numpy(dtype=float)
    colors = ["#55A868" if not np.isnan(v) else "#CCCCCC" for v in vals]
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    bars = ax.bar(labels, np.nan_to_num(vals), color=colors, edgecolor="black")
    mean_def = np.nanmean(vals)
    ax.axhline(
        mean_def,
        color="#C44E52",
        linestyle="--",
        linewidth=1.5,
        label=f"mean of defined cohorts = {mean_def:.1f}",
    )
    ax.bar_label(
        bars, labels=[f"{v:.1f}" if not np.isnan(v) else "n/a" for v in vals], padding=2, fontsize=9
    )
    ax.set(
        xlabel="Cohort month",
        ylabel="Cumulative revenue per user, periods 0-2",
        title="Fig 5 — LTV@3 (fixed horizon): comparable across cohorts; young cohorts excluded (grey)",
    )
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.savefig(FIG / "fig5_ltv_at_k3.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig6_revenue_behaviour(df: pd.DataFrame) -> None:
    active = df[df["is_active"] == 1]
    per_period = active.groupby("period")["revenue"].mean()
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    ax.plot(per_period.index, per_period.to_numpy(), marker="o", linewidth=2, color="#8172B3")
    ax.axhline(
        10.0, color="#C44E52", linestyle="--", linewidth=1.5, label=r"generative $\lambda = 10$"
    )
    ax.set(
        xlabel="Period (months since join)",
        ylabel="Mean revenue per active user-month",
        title="Fig 6 — Revenue behaviour ~flat over tenure (λ=10); late-period blips are small-n noise",
        ylim=(0, 14),
    )
    ax.legend(frameon=False)
    ax.grid(alpha=0.3)
    fig.savefig(FIG / "fig6_revenue_behaviour.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    df = load()
    fig1_revenue_distribution(df)
    fig2_cohort_sizes(df)
    fig3_retention_curve(df)
    fig4_retention_heatmap(df)
    fig5_ltv_at_k3(df)
    fig6_revenue_behaviour(df)
    print("Figures written to", FIG)
