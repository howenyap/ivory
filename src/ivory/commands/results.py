"""Results-reporting commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import polars as pl


def register_results_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the results command tree."""
    results_parser = subparsers.add_parser(
        "results",
        help="Show saved modeling results.",
        description="Read and summarize saved Ivory result artifacts.",
    )
    results_subparsers = results_parser.add_subparsers(
        dest="results_command", metavar="results-command"
    )

    baseline_parser = results_subparsers.add_parser(
        "baseline",
        help="Show the saved baseline training metrics.",
        description="Read artifacts/models/baseline_* artifacts and print a summary.",
    )
    baseline_parser.add_argument(
        "--metrics-artifact",
        default="artifacts/models/baseline_metrics.json",
        help="Path to the saved baseline metrics JSON artifact.",
    )
    baseline_parser.add_argument(
        "--manifest-artifact",
        default="artifacts/models/training_manifest.json",
        help="Path to the saved baseline training manifest JSON artifact.",
    )
    baseline_parser.add_argument(
        "--predictions-artifact",
        default="artifacts/models/baseline_predictions.parquet",
        help="Path to the saved baseline predictions parquet artifact.",
    )
    baseline_parser.set_defaults(handler=_handle_results_baseline)


def _handle_results_baseline(args: argparse.Namespace) -> int:
    metrics = json.loads(Path(args.metrics_artifact).read_text())
    manifest = json.loads(Path(args.manifest_artifact).read_text())
    predictions = pl.read_parquet(args.predictions_artifact)
    selected_models = manifest.get("selected_model_family_per_target", {})

    split = manifest.get("split", {})
    counts = split.get("counts", {})
    print("Baseline Results")
    print(
        f"  Split: {metrics['split_mode']} | Seed: {manifest.get('seed')} | "
        f"Train/Val/Test rows: {counts.get('train_rows', '?')}/"
        f"{counts.get('validation_rows', '?')}/{counts.get('test_rows', '?')}"
    )

    for target_name, target_metrics in metrics["targets"].items():
        target_model_results = manifest.get("model_results", {}).get(target_name, {})
        print()
        print(
            _format_target_block(
                target_name=target_name,
                target_metrics=target_metrics,
                selected_model=selected_models.get(target_name, "unknown"),
                predictions=predictions,
                model_results=target_model_results,
            )
        )
    return 0


def _format_target_block(
    *,
    target_name: str,
    target_metrics: dict[str, float],
    selected_model: str,
    predictions: pl.DataFrame,
    model_results: dict[str, Any],
) -> str:
    """Render a readable multi-line summary for one target."""
    stats = _prediction_stats(
        predictions=predictions,
        target_name=target_name,
        selected_model=selected_model,
        target_metrics=target_metrics,
        model_results=model_results,
    )
    lines = [
        f"{target_name}",
        f"  Model: {selected_model}",
        (
            "  Absolute: "
            f"RMSE {target_metrics['rmse']:.3f} | "
            f"MAE {target_metrics['mae']:.3f}"
            + (
                f" | Median AE {stats['abs_error_median']:.3f}"
                if stats is not None
                else ""
            )
        ),
        (
            "  Relative: "
            f"MAPE {target_metrics['mape'] * 100:.2f}%"
            + (
                f" | Median {stats['relative_error_median'] * 100:.2f}% | "
                f"IQR {stats['relative_error_q1'] * 100:.2f}% - "
                f"{stats['relative_error_q3'] * 100:.2f}% | "
                f"P90 {stats['relative_error_p90'] * 100:.2f}%"
                if stats is not None
                else ""
            )
        ),
        (
            "  Context: "
            + (
                f"Median actual {stats['actual_median']:.3f} | "
                f"RMSE/median actual {stats['rmse_pct_of_median_actual'] * 100:.2f}% | "
                f"MAE/median actual {stats['mae_pct_of_median_actual'] * 100:.2f}%"
                if stats is not None
                else "Prediction-derived context unavailable for the selected model."
            )
        ),
        (
            "  Other: "
            f"R2 {target_metrics['r2']:.4f} | "
            f"Q-error p50 {target_metrics['q_error_p50']:.3f} | "
            f"Q-error p90 {target_metrics['q_error_p90']:.3f}"
        ),
    ]
    supplemental = stats.get("supplemental_metrics") if stats is not None else None
    if isinstance(supplemental, dict):
        if "smape" in supplemental and supplemental["smape"] is not None:
            lines.append(f"  Supplemental: sMAPE {supplemental['smape'] * 100:.2f}%")
        if supplemental.get("rank_correlation") is not None:
            lines[-1] = (
                f"{lines[-1]} | Rank corr {supplemental['rank_correlation']:.4f}"
            )
    return "\n".join(lines)


def _prediction_stats(
    *,
    predictions: pl.DataFrame,
    target_name: str,
    selected_model: str,
    target_metrics: dict[str, float],
    model_results: dict[str, Any],
) -> dict[str, Any] | None:
    """Compute selected-model prediction summaries used in CLI reporting."""
    subset_filter = (pl.col("target_name") == target_name) & (
        pl.col("model_family") == selected_model
    )
    if "dataset_partition" in predictions.columns:
        subset_filter = subset_filter & (pl.col("dataset_partition") == "test")
    if "is_selected_baseline" in predictions.columns:
        subset = predictions.filter(subset_filter & pl.col("is_selected_baseline"))
    else:
        subset = predictions.filter(subset_filter)
    if subset.is_empty():
        subset = predictions.filter(subset_filter)
    if subset.is_empty():
        return None

    actual = pl.col("actual_value").abs().clip(lower_bound=1e-9)
    abs_error = (pl.col("predicted_value") - pl.col("actual_value")).abs()
    relative_error = abs_error / actual
    summary = subset.select(
        pl.len().alias("n"),
        pl.col("actual_value").median().alias("actual_median"),
        abs_error.median().alias("abs_error_median"),
        relative_error.median().alias("relative_error_median"),
        relative_error.quantile(0.25).alias("relative_error_q1"),
        relative_error.quantile(0.75).alias("relative_error_q3"),
        relative_error.quantile(0.90).alias("relative_error_p90"),
    ).to_dicts()[0]

    actual_median = max(float(summary["actual_median"]), 1e-9)
    selected_model_results = (
        model_results.get(selected_model, {}) if isinstance(model_results, dict) else {}
    )
    return {
        **summary,
        "rmse_pct_of_median_actual": float(target_metrics["rmse"]) / actual_median,
        "mae_pct_of_median_actual": float(target_metrics["mae"]) / actual_median,
        "supplemental_metrics": selected_model_results.get("supplemental_test_metrics"),
    }
