"""Score curated query formulations with the trained planner-total-cost model."""

from __future__ import annotations

import argparse
import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
import sqlglot

from ivory.baseline_modeling import flatten_modeling_dataset, to_feature_matrix
from ivory.config import load_config
from ivory.plan_features import build_plan_feature_row
from ivory.postgres import database_connection, project_postgres_config
from ivory.query_compare_validation import _display_path
from ivory.sql_features import build_sql_feature_row

ROOT_DIR = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = ROOT_DIR / "query_compare" / "benchmark.json"
DEFAULT_OUTPUT_PATH = (
    ROOT_DIR
    / "query_compare"
    / "results"
    / "predictions"
    / "query_compare_predictions_sf_1.parquet"
)
DEFAULT_SUMMARY_PATH = (
    ROOT_DIR
    / "query_compare"
    / "results"
    / "predictions"
    / "query_compare_predictions_sf_1.json"
)
DEFAULT_EXPLAIN_DIR = ROOT_DIR / "query_compare" / "results" / "explains"
DEFAULT_MANIFEST_PATH = ROOT_DIR / "artifacts" / "models" / "training_manifest.json"
TARGET_NAME = "planner_total_cost"


@dataclass(frozen=True)
class Formulation:
    template_id: str
    formulation_label: str
    formulation_kind: str
    parameter_set_id: str
    scale_factor: float
    sql_text: str
    sql_path: str

    @property
    def formulation_id(self) -> str:
        return f"{self.template_id}__{self.formulation_label}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ivory.query_compare_prediction",
        description=(
            "Compare curated SQL formulations with the trained "
            "planner_total_cost estimator."
        ),
    )
    parser.add_argument(
        "--benchmark",
        default=str(BENCHMARK_PATH),
        help="Path to the query-comparison benchmark JSON artifact.",
    )
    parser.add_argument(
        "--database",
        default="tpch_sf_1",
        help="Database name to score against. Defaults to tpch_sf_1.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to write the canonical Parquet prediction artifact.",
    )
    parser.add_argument(
        "--summary-output",
        default=str(DEFAULT_SUMMARY_PATH),
        help="Path to write the compact JSON prediction summary.",
    )
    parser.add_argument(
        "--explain-dir",
        default=str(DEFAULT_EXPLAIN_DIR),
        help="Directory for per-formulation EXPLAIN JSON captures.",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Training manifest used to resolve the selected baseline model.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help=(
            "Run EXPLAIN (ANALYZE, FORMAT JSON) so measured execution_time_ms is "
            "captured alongside planner and model costs."
        ),
    )
    return parser


def load_selected_estimator(*, manifest_path: Path) -> tuple[str, list[str], Any]:
    """Load the selected baseline estimator and its feature columns."""
    manifest = json.loads(manifest_path.read_text())
    selected_family = manifest["selected_model_family_per_target"][TARGET_NAME]
    feature_columns = manifest["final_model_input_columns_per_model"][selected_family][
        TARGET_NAME
    ]
    relative_model_path = manifest["model_artifact_paths"][TARGET_NAME][selected_family]
    estimator_path = ROOT_DIR / relative_model_path
    estimator = pickle.loads(estimator_path.read_bytes())
    return selected_family, feature_columns, estimator


def load_formulations(*, benchmark_path: Path) -> list[Formulation]:
    """Return the baseline and accepted alternatives from the benchmark."""
    benchmark = json.loads(benchmark_path.read_text())
    formulations: list[Formulation] = []
    for template in benchmark["templates"]:
        template_id = str(template["template_id"])
        parameter_set_id = str(template["parameter_set_id"])
        scale_factor = float(template["scale_factor"])
        formulations.append(
            Formulation(
                template_id=template_id,
                formulation_label="baseline",
                formulation_kind="baseline",
                parameter_set_id=parameter_set_id,
                scale_factor=scale_factor,
                sql_text=str(template["baseline_sql"]),
                sql_path=str(
                    template.get(
                        "baseline_sql_path", f"query_compare/sql/{template_id}_base.sql"
                    )
                ),
            )
        )
        for index, alternative in enumerate(template["accepted_formulations"], start=1):
            formulation_type = str(alternative["formulation_type"])
            formulations.append(
                Formulation(
                    template_id=template_id,
                    formulation_label=str(alternative["formulation_id"]),
                    formulation_kind="accepted_alternative",
                    parameter_set_id=parameter_set_id,
                    scale_factor=scale_factor,
                    sql_text=str(alternative["sql"]),
                    sql_path=str(
                        alternative.get(
                            "sql_path",
                            (
                                "query_compare/sql/"
                                f"{template_id}_formulation_{index}_{formulation_type}.sql"
                            ),
                        )
                    ),
                )
            )
    return formulations


def fetch_explain_plan(
    *, database: str, sql_text: str, analyze: bool = False
) -> dict[str, Any]:
    """Run EXPLAIN and return the top-level plan document."""
    config = load_config()
    settings = project_postgres_config(config)
    explain_clause = (
        "EXPLAIN (ANALYZE, FORMAT JSON)"
        if analyze
        else "EXPLAIN (FORMAT JSON)"
    )
    with database_connection(settings, database) as conn:
        row = conn.execute(f"{explain_clause} {sql_text}").fetchone()
    plan_document = row["QUERY PLAN"][0]
    if not isinstance(plan_document, dict):
        raise ValueError("Expected EXPLAIN (FORMAT JSON) to return a JSON object.")
    return plan_document


def build_feature_frame(
    *, formulation: Formulation, plan_document: dict[str, Any]
) -> pl.DataFrame:
    """Construct a one-row assembled-feature frame for estimator inference."""
    query_instance = {
        "query_instance_id": formulation.formulation_id,
        "template_id": formulation.template_id,
        "parameter_set_id": formulation.parameter_set_id,
        "scale_factor": formulation.scale_factor,
        "sql_text": formulation.sql_text,
    }
    sql_feature_row = build_sql_feature_row(
        query_instance,
        sqlglot.parse_one(formulation.sql_text, read="postgres"),
    )
    observation = {
        "observation_id": formulation.formulation_id,
        "query_instance_id": formulation.formulation_id,
        "template_id": formulation.template_id,
        "parameter_set_id": formulation.parameter_set_id,
        "scale_factor": formulation.scale_factor,
    }
    plan_feature_row = build_plan_feature_row(observation, {"plan": plan_document})
    return pl.DataFrame(
        [
            {
                "observation_id": formulation.formulation_id,
                "run_attempt_id": formulation.formulation_id,
                "query_instance_id": formulation.formulation_id,
                "template_id": formulation.template_id,
                "parameter_set_id": formulation.parameter_set_id,
                "scale_factor": formulation.scale_factor,
                "sql_features_broadcast": bool(
                    sql_feature_row["broadcast_to_modeling_grain"]
                ),
                "plan_features_broadcast": bool(
                    plan_feature_row["broadcast_to_modeling_grain"]
                ),
                "targets": {
                    "planner_total_cost": plan_feature_row["planner_total_cost"],
                    "planning_time_ms": None,
                    "execution_time_ms": None,
                },
                "sql_features": {
                    key: value
                    for key, value in sql_feature_row.items()
                    if key
                    not in {
                        "query_instance_id",
                        "template_id",
                        "parameter_set_id",
                        "scale_factor",
                        "broadcast_to_modeling_grain",
                        "feature_status",
                    }
                },
                "plan_features": {
                    key: value
                    for key, value in plan_feature_row.items()
                    if key
                    not in {
                        "observation_id",
                        "query_instance_id",
                        "template_id",
                        "parameter_set_id",
                        "scale_factor",
                        "broadcast_to_modeling_grain",
                        "feature_status",
                    }
                },
            }
        ]
    )


def rank_within_template(
    rows: list[dict[str, Any]], *, value_key: str, rank_key: str
) -> None:
    """Assign dense ranks within each template, preserving ties."""
    by_template: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_template.setdefault(str(row["template_id"]), []).append(row)
    for template_rows in by_template.values():
        ordered = sorted(
            template_rows, key=lambda row: float(row[value_key])
        )
        previous_value: float | None = None
        current_rank = 0
        for row in ordered:
            value = float(row[value_key])
            if previous_value is None or value != previous_value:
                current_rank += 1
                previous_value = value
            row[rank_key] = current_rank


def rank_within_template_if_present(
    rows: list[dict[str, Any]], *, value_key: str, rank_key: str
) -> None:
    """Assign ranks only for templates where every row has the metric."""
    for row in rows:
        row[rank_key] = None
    by_template: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_template.setdefault(str(row["template_id"]), []).append(row)
    for template_rows in by_template.values():
        if any(row.get(value_key) is None for row in template_rows):
            continue
        rank_within_template(
            template_rows,
            value_key=value_key,
            rank_key=rank_key,
        )


def add_baseline_deltas(rows: list[dict[str, Any]]) -> None:
    """Add per-template deltas relative to the baseline formulation."""
    baseline_by_template = {
        str(row["template_id"]): row
        for row in rows
        if row["formulation_kind"] == "baseline"
    }
    for row in rows:
        baseline = baseline_by_template[str(row["template_id"])]
        row["planner_total_cost_delta_vs_baseline"] = float(
            row["planner_total_cost"]
        ) - float(baseline["planner_total_cost"])
        row["model_predicted_cost_delta_vs_baseline"] = float(
            row["model_predicted_cost"]
        ) - float(baseline["model_predicted_cost"])
        execution_time_ms = row.get("execution_time_ms")
        baseline_execution_time_ms = baseline.get("execution_time_ms")
        row["execution_time_ms_delta_vs_baseline"] = (
            float(execution_time_ms) - float(baseline_execution_time_ms)
            if execution_time_ms is not None
            and baseline_execution_time_ms is not None
            else None
        )


def _winner_rows_for_metric(
    rows: list[dict[str, Any]], *, metric_key: str
) -> list[dict[str, Any]]:
    available_rows = [row for row in rows if row.get(metric_key) is not None]
    if not available_rows:
        return []
    best_value = min(float(row[metric_key]) for row in available_rows)
    return sorted(
        [
            row
            for row in available_rows
            if float(row[metric_key]) == best_value
        ],
        key=lambda row: str(row["formulation_id"]),
    )


def _dense_rank_correlation(
    rows: list[dict[str, Any]], *, left_rank_key: str, right_rank_key: str
) -> float | None:
    """Return Pearson correlation over dense-rank vectors for comparable rows."""
    paired_rows = [
        row
        for row in rows
        if row.get(left_rank_key) is not None and row.get(right_rank_key) is not None
    ]
    if len(paired_rows) < 2:
        return None
    left_ranks = [float(row[left_rank_key]) for row in paired_rows]
    right_ranks = [float(row[right_rank_key]) for row in paired_rows]
    count = len(paired_rows)
    left_mean = sum(left_ranks) / count
    right_mean = sum(right_ranks) / count
    numerator = sum(
        (left - left_mean) * (right - right_mean)
        for left, right in zip(left_ranks, right_ranks, strict=True)
    )
    left_variance = sum((left - left_mean) ** 2 for left in left_ranks)
    right_variance = sum((right - right_mean) ** 2 for right in right_ranks)
    if left_variance == 0.0 or right_variance == 0.0:
        return None
    return numerator / ((left_variance * right_variance) ** 0.5)


def build_summary(
    *,
    rows: list[dict[str, Any]],
    benchmark_path: Path,
    database: str,
    model_family: str,
    output_path: Path,
    explain_dir: Path,
    analyze: bool,
) -> dict[str, Any]:
    """Build a compact JSON summary derived from the prediction rows."""
    templates: list[dict[str, Any]] = []
    for template_id in sorted({str(row["template_id"]) for row in rows}):
        template_rows = [
            row for row in rows if str(row["template_id"]) == template_id
        ]
        baseline = next(
            row for row in template_rows if row["formulation_kind"] == "baseline"
        )
        best_predicted_rows = _winner_rows_for_metric(
            template_rows, metric_key="model_predicted_cost"
        )
        best_planner_rows = _winner_rows_for_metric(
            template_rows, metric_key="planner_total_cost"
        )
        best_runtime_rows = _winner_rows_for_metric(
            template_rows, metric_key="execution_time_ms"
        )
        best_predicted_ids = [
            str(row["formulation_id"]) for row in best_predicted_rows
        ]
        best_planner_ids = [
            str(row["formulation_id"]) for row in best_planner_rows
        ]
        best_runtime_ids = [
            str(row["formulation_id"]) for row in best_runtime_rows
        ]
        best_predicted_id = (
            best_predicted_ids[0] if len(best_predicted_ids) == 1 else None
        )
        best_planner_id = best_planner_ids[0] if len(best_planner_ids) == 1 else None
        best_runtime_id = best_runtime_ids[0] if len(best_runtime_ids) == 1 else None
        planner_vs_model_agree = (
            best_planner_id == best_predicted_id
            if best_planner_id is not None and best_predicted_id is not None
            else None
        )
        planner_vs_runtime_agree = (
            best_planner_id == best_runtime_id
            if best_planner_id is not None and best_runtime_id is not None
            else None
        )
        model_vs_runtime_agree = (
            best_predicted_id == best_runtime_id
            if best_predicted_id is not None and best_runtime_id is not None
            else None
        )
        all_signals_agree = (
            best_planner_id == best_predicted_id == best_runtime_id
            if best_planner_id is not None
            and best_predicted_id is not None
            and best_runtime_id is not None
            else None
        )
        templates.append(
            {
                "template_id": template_id,
                "baseline_formulation_id": baseline["formulation_id"],
                "baseline_predicted_cost": baseline["model_predicted_cost"],
                "baseline_execution_time_ms": baseline["execution_time_ms"],
                "best_predicted_formulation_ids": best_predicted_ids,
                "best_predicted_formulation_id": best_predicted_id,
                "best_predicted_cost": (
                    best_predicted_rows[0]["model_predicted_cost"]
                    if best_predicted_rows
                    else None
                ),
                "best_planner_formulation_ids": best_planner_ids,
                "best_planner_formulation_id": best_planner_id,
                "best_planner_total_cost": (
                    best_planner_rows[0]["planner_total_cost"]
                    if best_planner_rows
                    else None
                ),
                "best_execution_time_formulation_ids": best_runtime_ids,
                "best_execution_time_formulation_id": best_runtime_id,
                "best_execution_time_ms": (
                    best_runtime_rows[0]["execution_time_ms"]
                    if best_runtime_rows
                    else None
                ),
                "planner_vs_model_agree": planner_vs_model_agree,
                "planner_vs_runtime_agree": planner_vs_runtime_agree,
                "model_vs_runtime_agree": model_vs_runtime_agree,
                "all_signals_agree": all_signals_agree,
                "planner_vs_model_dense_rank_correlation": _dense_rank_correlation(
                    template_rows,
                    left_rank_key="planner_total_cost_rank",
                    right_rank_key="model_predicted_cost_rank",
                ),
                "planner_vs_runtime_dense_rank_correlation": _dense_rank_correlation(
                    template_rows,
                    left_rank_key="planner_total_cost_rank",
                    right_rank_key="execution_time_ms_rank",
                ),
                "model_vs_runtime_dense_rank_correlation": _dense_rank_correlation(
                    template_rows,
                    left_rank_key="model_predicted_cost_rank",
                    right_rank_key="execution_time_ms_rank",
                ),
            }
        )
    return {
        "artifact_name": "query_compare_prediction_summary",
        "benchmark_path": _display_path(benchmark_path),
        "database": database,
        "target_name": TARGET_NAME,
        "model_family": model_family,
        "runtime_collection_enabled": analyze,
        "prediction_artifact_path": _display_path(output_path),
        "explain_artifact_dir": _display_path(explain_dir),
        "templates": templates,
    }


def predict_query_compare_costs(
    *,
    benchmark_path: Path,
    database: str,
    output_path: Path,
    summary_output_path: Path,
    explain_dir: Path,
    manifest_path: Path,
    analyze: bool = False,
) -> dict[str, Any]:
    """Score every curated formulation and write prediction artifacts."""
    model_family, feature_columns, estimator = load_selected_estimator(
        manifest_path=manifest_path
    )
    formulations = load_formulations(benchmark_path=benchmark_path)
    rows: list[dict[str, Any]] = []
    explain_dir.mkdir(parents=True, exist_ok=True)
    expected_explain_paths = {
        explain_dir / f"{formulation.formulation_id}.json"
        for formulation in formulations
    }
    for stale_path in explain_dir.glob("*.json"):
        if stale_path not in expected_explain_paths:
            stale_path.unlink()

    for formulation in formulations:
        sql_path = ROOT_DIR / formulation.sql_path
        if not sql_path.exists():
            raise FileNotFoundError(
                f"Missing curated SQL file for formulation at {sql_path}."
            )
        plan_document = fetch_explain_plan(
            database=database,
            sql_text=formulation.sql_text,
            analyze=analyze,
        )
        explain_path = explain_dir / f"{formulation.formulation_id}.json"
        explain_path.write_text(
            json.dumps(plan_document, indent=2, sort_keys=True) + "\n"
        )

        feature_df = build_feature_frame(
            formulation=formulation,
            plan_document=plan_document,
        )
        modeling_df, _ = flatten_modeling_dataset(feature_df)
        missing_columns = [
            column for column in feature_columns if column not in modeling_df.columns
        ]
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(
                "Prediction features are missing columns required by the selected "
                f"model: {missing}"
            )
        predicted_cost = float(
            estimator.predict(to_feature_matrix(modeling_df, feature_columns))[0]
        )
        root_plan = plan_document["Plan"]
        rows.append(
            {
                "template_id": formulation.template_id,
                "formulation_id": formulation.formulation_label,
                "formulation_kind": formulation.formulation_kind,
                "parameter_set_id": formulation.parameter_set_id,
                "scale_factor": formulation.scale_factor,
                "database": database,
                "sql_path": formulation.sql_path,
                "planner_total_cost": float(root_plan["Total Cost"]),
                "execution_time_ms": (
                    float(plan_document["Execution Time"])
                    if analyze and "Execution Time" in plan_document
                    else None
                ),
                "model_predicted_cost": predicted_cost,
                "model_family": model_family,
                "runtime_collection_enabled": analyze,
                "explain_artifact_path": _display_path(explain_path),
            }
        )

    rank_within_template(
        rows, value_key="planner_total_cost", rank_key="planner_total_cost_rank"
    )
    rank_within_template(
        rows,
        value_key="model_predicted_cost",
        rank_key="model_predicted_cost_rank",
    )
    rank_within_template_if_present(
        rows,
        value_key="execution_time_ms",
        rank_key="execution_time_ms_rank",
    )
    add_baseline_deltas(rows)
    rows.sort(
        key=lambda row: (str(row["template_id"]), str(row["formulation_id"]))
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(output_path)

    summary_output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_summary(
        rows=rows,
        benchmark_path=benchmark_path,
        database=database,
        model_family=model_family,
        output_path=output_path,
        explain_dir=explain_dir,
        analyze=analyze,
    )
    summary_output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    summary = predict_query_compare_costs(
        benchmark_path=Path(args.benchmark),
        database=args.database,
        output_path=Path(args.output),
        summary_output_path=Path(args.summary_output),
        explain_dir=Path(args.explain_dir),
        manifest_path=Path(args.manifest),
        analyze=bool(args.analyze),
    )
    print(
        "Query comparison prediction complete: "
        f"database={summary['database']} "
        f"templates={len(summary['templates'])} "
        f"model_family={summary['model_family']} "
        f"analyze={summary['runtime_collection_enabled']} "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
