"""Phase 4a report asset generation: figures and tables."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import matplotlib
import polars as pl

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT_DIR / "artifacts" / "report"
FIGURES_DIR = REPORT_DIR / "figures"
TABLES_DIR = ROOT_DIR / "artifacts" / "report" / "tables"
FULL_RERUN_MANIFEST_PATH = REPORT_DIR / "full_rerun_manifest.json"

BASELINE_METRICS_PATH = ROOT_DIR / "artifacts" / "models" / "baseline_metrics.json"
TRAINING_MANIFEST_PATH = ROOT_DIR / "artifacts" / "models" / "training_manifest.json"
GROUPED_METRICS_PATH = ROOT_DIR / "artifacts" / "evaluation" / "grouped_metrics.json"
ABLATIONS_PATH = ROOT_DIR / "artifacts" / "evaluation" / "ablations.json"
ERROR_ANALYSIS_PATH = ROOT_DIR / "artifacts" / "evaluation" / "error_analysis.parquet"

TARGET_LABELS = {
    "execution_time_ms": "Execution Time (ms)",
    "planner_total_cost": "Planner Cost",
    "planning_time_ms": "Planning Time (ms)",
}
TARGET_ORDER = ["execution_time_ms", "planner_total_cost", "planning_time_ms"]
MODEL_LABELS = {
    "dummy_mean": "Dummy Mean",
    "ridge": "Ridge",
    "random_forest": "Random Forest",
    "hist_gradient_boosting": "Hist. GBT",
}
MODEL_ORDER = ["dummy_mean", "ridge", "random_forest", "hist_gradient_boosting"]

EXPECTED_FIGURES = [
    "fig_model_comparison.png",
    "fig_random_vs_grouped.png",
    "fig_ablation_execution_time.png",
    "fig_q_error_by_template.png",
]
EXPECTED_TABLES = [
    "table_baseline_metrics.csv",
    "table_grouped_metrics.csv",
    "table_ablations.csv",
]

STAGE_SENTINELS = {
    "collect": ROOT_DIR / "artifacts" / "raw" / "collection_manifest.json",
    "featurize": ROOT_DIR / "artifacts" / "features" / "features.parquet",
    "train": TRAINING_MANIFEST_PATH,
    "evaluate": ROOT_DIR / "artifacts" / "evaluation" / "grouped_metrics.json",
    "report_assets": FULL_RERUN_MANIFEST_PATH,
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_report_assets() -> dict[str, Any]:
    """Generate all figures and tables from frozen evaluation artifacts."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    training_manifest = json.loads(TRAINING_MANIFEST_PATH.read_text())
    baseline_metrics = json.loads(BASELINE_METRICS_PATH.read_text())
    grouped_metrics = json.loads(GROUPED_METRICS_PATH.read_text())
    ablations = json.loads(ABLATIONS_PATH.read_text())
    error_df = pl.read_parquet(ERROR_ANALYSIS_PATH)

    _fig_model_comparison(training_manifest)
    _fig_random_vs_grouped(baseline_metrics, grouped_metrics)
    _fig_ablation_execution_time(ablations)
    _fig_q_error_by_template(error_df)

    _table_baseline_metrics(training_manifest)
    _table_grouped_metrics(grouped_metrics)
    _table_ablations(ablations)

    return {
        "figures_dir": str(FIGURES_DIR),
        "tables_dir": str(TABLES_DIR),
        "figures": EXPECTED_FIGURES,
        "tables": EXPECTED_TABLES,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _fig_model_comparison(training_manifest: dict[str, Any]) -> None:
    """Grouped bar chart: model families × targets, metric = RMSE."""
    model_results = training_manifest["model_results"]
    selected = training_manifest["selected_model_family_per_target"]

    n_targets = len(TARGET_ORDER)
    n_models = len(MODEL_ORDER)
    x = list(range(n_targets))
    bar_width = 0.18
    offsets = [bar_width * (i - n_models / 2 + 0.5) for i in range(n_models)]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("Baseline Model Comparison by Target", fontsize=13)

    for ax_idx, metric in enumerate(["rmse", "q_error_p50"]):
        ax = axes[ax_idx]
        for model_idx, family in enumerate(MODEL_ORDER):
            values = []
            for target in TARGET_ORDER:
                tm = model_results.get(target, {}).get(family, {}).get("test_metrics", {})
                values.append(tm.get(metric, 0.0))
            bars = ax.bar(
                [xi + offsets[model_idx] for xi in x],
                values,
                width=bar_width,
                label=MODEL_LABELS[family],
            )
            # Bold edge for selected model
            for bar_idx, bar in enumerate(bars):
                target = TARGET_ORDER[bar_idx]
                if selected.get(target) == family:
                    bar.set_edgecolor("black")
                    bar.set_linewidth(2)

        ax.set_xticks(x)
        ax.set_xticklabels(
            [TARGET_LABELS[t] for t in TARGET_ORDER], fontsize=9
        )
        metric_label = "RMSE" if metric == "rmse" else "Q-Error (p50)"
        ax.set_ylabel(metric_label)
        ax.set_title(metric_label)
        ax.legend(fontsize=8)
        ax.set_ylim(bottom=0)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig_model_comparison.png", dpi=150)
    plt.close(fig)


def _fig_random_vs_grouped(
    baseline_metrics: dict[str, Any],
    grouped_metrics: dict[str, Any],
) -> None:
    """Side-by-side bar chart: random split vs grouped split q-errors."""
    n_targets = len(TARGET_ORDER)
    bar_width = 0.25
    x = list(range(n_targets))

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Random vs Grouped-by-Template Evaluation", fontsize=13)

    for ax_idx, metric in enumerate(["q_error_p50", "q_error_p90"]):
        ax = axes[ax_idx]
        random_vals = [
            baseline_metrics["targets"][t].get(metric, 0.0) for t in TARGET_ORDER
        ]
        grouped_vals = [
            grouped_metrics["targets"][t].get(metric, 0.0) for t in TARGET_ORDER
        ]
        ax.bar(
            [xi - bar_width / 2 for xi in x],
            random_vals,
            width=bar_width,
            label="Random split",
            color="#4c72b0",
        )
        ax.bar(
            [xi + bar_width / 2 for xi in x],
            grouped_vals,
            width=bar_width,
            label="Grouped (template holdout)",
            color="#dd8452",
        )
        ax.set_xticks(x)
        ax.set_xticklabels(
            [TARGET_LABELS[t] for t in TARGET_ORDER], fontsize=9
        )
        metric_label = "Q-Error (p50)" if metric == "q_error_p50" else "Q-Error (p90)"
        ax.set_ylabel(metric_label)
        ax.set_title(metric_label)
        ax.legend(fontsize=9)
        ax.set_ylim(bottom=0)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig_random_vs_grouped.png", dpi=150)
    plt.close(fig)


def _fig_ablation_execution_time(ablations: dict[str, Any]) -> None:
    """Horizontal bar chart: feature ablations for execution_time_ms."""
    conditions = ["sql_only", "plan_only", "combined"]
    condition_labels = ["SQL features only", "Plan features only", "Combined"]
    target = "execution_time_ms"

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("Feature Ablation — Execution Time (ms)", fontsize=13)

    proxy = ablations.get("postgres_cost_proxy", {}).get(target, {})

    for ax_idx, metric in enumerate(["rmse", "q_error_p50"]):
        ax = axes[ax_idx]
        values = []
        for cond in conditions:
            v = ablations.get(cond, {}).get(target, {}).get(metric, 0.0)
            values.append(v)

        bars = ax.barh(condition_labels, values, color="#4c72b0")
        for bar, val in zip(bars, values):
            ax.text(
                val * 1.01, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=8,
            )

        if proxy and metric in proxy:
            proxy_val = proxy[metric]
            ax.axvline(
                x=proxy_val, color="red", linestyle="--", linewidth=1.2,
                label=f"PG cost proxy ({proxy_val:.1f})",
            )
            ax.legend(fontsize=8)

        metric_label = "RMSE" if metric == "rmse" else "Q-Error (p50)"
        ax.set_xlabel(metric_label)
        ax.set_title(metric_label)
        ax.set_xlim(left=0)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig_ablation_execution_time.png", dpi=150)
    plt.close(fig)


def _fig_q_error_by_template(error_df: pl.DataFrame) -> None:
    """Box plot of q_error per template, filtered to execution_time_ms."""
    df = error_df.filter(pl.col("target_name") == "execution_time_ms")

    medians = (
        df.group_by("template_id")
        .agg(pl.col("q_error").median().alias("median_q_error"))
        .sort("median_q_error", descending=True)
    )
    template_order = medians["template_id"].to_list()

    data_by_template = {
        tid: df.filter(pl.col("template_id") == tid)["q_error"].to_list()
        for tid in template_order
    }

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.boxplot(
        [data_by_template[tid] for tid in template_order],
        labels=template_order,
        vert=True,
        patch_artist=True,
        boxprops={"facecolor": "#4c72b0", "alpha": 0.6},
        medianprops={"color": "black", "linewidth": 1.5},
        flierprops={"marker": ".", "markersize": 3},
    )
    ax.axhline(y=1.0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Query Template")
    ax.set_ylabel("Q-Error")
    ax.set_title("Q-Error Distribution per Template — Execution Time (ms)")
    ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig_q_error_by_template.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _table_baseline_metrics(training_manifest: dict[str, Any]) -> None:
    """model_family × target × metric CSV."""
    model_results = training_manifest["model_results"]
    selected = training_manifest["selected_model_family_per_target"]
    metrics = ["mae", "rmse", "mape", "q_error_p50", "q_error_p90", "r2"]

    rows = []
    for target in TARGET_ORDER:
        for family in MODEL_ORDER:
            tm = model_results.get(target, {}).get(family, {}).get("test_metrics", {})
            row = {
                "target": target,
                "model_family": family,
                "is_selected": selected.get(target) == family,
            }
            for m in metrics:
                row[m] = tm.get(m, "")
            rows.append(row)

    _write_csv(
        TABLES_DIR / "table_baseline_metrics.csv",
        fieldnames=["target", "model_family", "is_selected"] + metrics,
        rows=rows,
    )


def _table_grouped_metrics(grouped_metrics: dict[str, Any]) -> None:
    """target × metric CSV for grouped evaluation."""
    metrics = ["mae", "rmse", "mape", "q_error_p50", "q_error_p90", "q_error_p95", "q_error_p99", "group_support"]
    rows = []
    for target in TARGET_ORDER:
        tm = grouped_metrics["targets"].get(target, {})
        row = {"target": target}
        for m in metrics:
            row[m] = tm.get(m, "")
        rows.append(row)

    _write_csv(
        TABLES_DIR / "table_grouped_metrics.csv",
        fieldnames=["target"] + metrics,
        rows=rows,
    )


def _table_ablations(ablations: dict[str, Any]) -> None:
    """ablation_condition × target × metric CSV."""
    conditions = ["sql_only", "plan_only", "combined"]
    metrics = ["mae", "rmse", "mape", "q_error_p50", "r2"]
    rows = []
    for cond in conditions:
        for target in TARGET_ORDER:
            tm = ablations.get(cond, {}).get(target, {})
            row = {"condition": cond, "target": target}
            for m in metrics:
                row[m] = tm.get(m, "")
            rows.append(row)

    # Also add postgres_cost_proxy row for execution_time_ms
    proxy_tm = ablations.get("postgres_cost_proxy", {}).get("execution_time_ms", {})
    if proxy_tm:
        row = {"condition": "postgres_cost_proxy", "target": "execution_time_ms"}
        for m in metrics:
            row[m] = proxy_tm.get(m, "")
        rows.append(row)

    _write_csv(
        TABLES_DIR / "table_ablations.csv",
        fieldnames=["condition", "target"] + metrics,
        rows=rows,
    )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Verify and manifest
# ---------------------------------------------------------------------------


def verify_report_assets() -> list[str]:
    """Return list of missing expected asset paths. Empty = all present."""
    missing = []
    for name in EXPECTED_FIGURES:
        p = FIGURES_DIR / name
        if not p.exists():
            missing.append(str(p.relative_to(ROOT_DIR)))
    for name in EXPECTED_TABLES:
        p = TABLES_DIR / name
        if not p.exists():
            missing.append(str(p.relative_to(ROOT_DIR)))
    return missing


def write_full_rerun_manifest() -> dict[str, Any]:
    """Write full_rerun_manifest.json recording stage completion."""
    artifact_checks: dict[str, str] = {}
    stages: dict[str, str] = {}

    for stage, sentinel in STAGE_SENTINELS.items():
        exists = sentinel.exists()
        artifact_checks[stage] = str(sentinel.relative_to(ROOT_DIR))
        if stage == "report_assets":
            # report_assets sentinel is the manifest itself — check other assets instead
            missing = verify_report_assets()
            stages[stage] = "completed" if not missing else "missing"
        else:
            stages[stage] = "completed" if exists else "missing"

    manifest = {
        "stages": stages,
        "artifact_checks": artifact_checks,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FULL_RERUN_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest
