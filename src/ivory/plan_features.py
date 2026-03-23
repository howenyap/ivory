"""PostgreSQL plan feature extraction for phase 2b."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import polars as pl

from ivory.collection import format_progress, log_progress
from ivory.config import load_schema

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "raw"
FEATURE_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "features"
PLAN_FEATURES_PATH = FEATURE_ARTIFACT_DIR / "plan_features.parquet"
PLAN_FEATURE_EXCLUSIONS_PATH = FEATURE_ARTIFACT_DIR / "plan_feature_exclusions.parquet"
PLAN_FEATURE_SCHEMA_PATH = ROOT_DIR / "schemas" / "plan_features.schema.json"

OBSERVATION_COLUMNS = (
    "observation_id",
    "query_instance_id",
    "template_id",
    "parameter_set_id",
    "scale_factor",
)
NODE_TYPE_COUNT_COLUMNS = {
    "Aggregate": "node_type_aggregate_count",
    "Bitmap Heap Scan": "node_type_bitmap_heap_scan_count",
    "Bitmap Index Scan": "node_type_bitmap_index_scan_count",
    "CTE Scan": "node_type_cte_scan_count",
    "Gather": "node_type_gather_count",
    "Gather Merge": "node_type_gather_merge_count",
    "Hash": "node_type_hash_count",
    "Hash Join": "node_type_hash_join_count",
    "Index Only Scan": "node_type_index_only_scan_count",
    "Index Scan": "node_type_index_scan_count",
    "Limit": "node_type_limit_count",
    "Nested Loop": "node_type_nested_loop_count",
    "Seq Scan": "node_type_seq_scan_count",
    "Sort": "node_type_sort_count",
}
PLAN_FEATURE_POLARS_SCHEMA = pl.Schema(
    {
        "observation_id": pl.String,
        "query_instance_id": pl.String,
        "template_id": pl.String,
        "parameter_set_id": pl.String,
        "scale_factor": pl.Float64,
        "broadcast_to_modeling_grain": pl.Boolean,
        "feature_status": pl.String,
        "plan_node_count": pl.Int64,
        "join_node_count": pl.Int64,
        "scan_node_count": pl.Int64,
        "aggregate_node_count": pl.Int64,
        "sort_node_count": pl.Int64,
        "plan_depth_max": pl.Int64,
        "planner_estimated_rows": pl.Float64,
        "planner_estimated_rows_sum": pl.Float64,
        "planner_estimated_rows_max": pl.Float64,
        "planner_estimated_width": pl.Float64,
        "planner_estimated_width_sum": pl.Float64,
        "planner_estimated_width_max": pl.Float64,
        "planner_startup_cost": pl.Float64,
        "planner_startup_cost_sum": pl.Float64,
        "planner_startup_cost_max": pl.Float64,
        "planner_total_cost": pl.Float64,
        "planner_total_cost_sum": pl.Float64,
        "planner_total_cost_max": pl.Float64,
        "node_type_aggregate_count": pl.Int64,
        "node_type_bitmap_heap_scan_count": pl.Int64,
        "node_type_bitmap_index_scan_count": pl.Int64,
        "node_type_cte_scan_count": pl.Int64,
        "node_type_gather_count": pl.Int64,
        "node_type_gather_merge_count": pl.Int64,
        "node_type_hash_count": pl.Int64,
        "node_type_hash_join_count": pl.Int64,
        "node_type_index_only_scan_count": pl.Int64,
        "node_type_index_scan_count": pl.Int64,
        "node_type_limit_count": pl.Int64,
        "node_type_nested_loop_count": pl.Int64,
        "node_type_seq_scan_count": pl.Int64,
        "node_type_sort_count": pl.Int64,
        "other_node_count": pl.Int64,
    }
)
PLAN_FEATURE_EXCLUSION_POLARS_SCHEMA = pl.Schema(
    {
        "observation_id": pl.String,
        "query_instance_id": pl.String,
        "template_id": pl.String,
        "parameter_set_id": pl.String,
        "scale_factor": pl.Float64,
        "broadcast_to_modeling_grain": pl.Boolean,
        "feature_status": pl.String,
        "parse_status": pl.String,
        "error_class": pl.String,
        "error_message": pl.String,
    }
)


class PlanFeatureError(ValueError):
    """Raised for recoverable plan-record parsing failures."""


def featurize_query_plans() -> dict[str, Any]:
    """Extract deterministic observation-level features from PostgreSQL JSON plans."""
    successful_observations = load_successful_observations()
    observation_lookup = {
        str(row["observation_id"]): row
        for row in successful_observations.iter_rows(named=True)
    }
    feature_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    total_observations = successful_observations.height
    processed = 0

    log_progress(
        f"plan featurization start | observations={total_observations}",
        level="info",
    )

    for record in iter_plan_records():
        observation_id = record.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id:
            raise ValueError("Encountered plan record without a valid observation_id.")
        if observation_id not in observation_lookup:
            raise ValueError(
                "Plan record observation_id does not match a successful raw run: "
                f"{observation_id}"
            )

        observation = observation_lookup[observation_id]
        processed += 1
        try:
            feature_rows.append(build_plan_feature_row(observation, record))
            status = "available"
            level = "info"
        except PlanFeatureError as exc:
            exclusion_rows.append(build_plan_feature_exclusion_row(observation, exc))
            status = "excluded"
            level = "warning"

        if processed == 1 or processed == total_observations or processed % 100 == 0:
            log_plan_featurization_progress(
                index=processed,
                total=total_observations,
                observation_id=observation_id,
                status=status,
                level=level,
            )

    if processed != total_observations:
        raise ValueError(
            "Plan artifact coverage mismatch before validation: "
            f"processed={processed} successful_observations={total_observations}"
        )

    features_df = dataframe_from_rows(feature_rows, PLAN_FEATURE_POLARS_SCHEMA)
    exclusions_df = dataframe_from_rows(
        exclusion_rows, PLAN_FEATURE_EXCLUSION_POLARS_SCHEMA
    )
    validate_plan_feature_schema(features_df)
    validate_plan_feature_coverage(successful_observations, features_df, exclusions_df)

    FEATURE_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    features_df.write_parquet(PLAN_FEATURES_PATH)
    exclusions_df.write_parquet(PLAN_FEATURE_EXCLUSIONS_PATH)
    log_progress(
        "plan featurization complete | "
        f"completed={format_progress(total_observations, total_observations)} "
        f"features={features_df.height} exclusions={exclusions_df.height}",
        level="success",
    )

    return {
        "plan_features_path": str(PLAN_FEATURES_PATH),
        "plan_feature_exclusions_path": str(PLAN_FEATURE_EXCLUSIONS_PATH),
        "input_observations": successful_observations.height,
        "feature_rows": features_df.height,
        "exclusion_rows": exclusions_df.height,
    }


def log_plan_featurization_progress(
    *,
    index: int,
    total: int,
    observation_id: str,
    status: str,
    level: str,
) -> None:
    """Emit a compact progress line for plan featurization."""
    log_progress(
        "plan featurization | "
        f"{format_progress(index, total)} "
        f"observation_id={observation_id} status={status}",
        level=level,
    )


def load_successful_observations() -> pl.DataFrame:
    """Load canonical successful raw observations for plan feature coverage."""
    raw_paths = sorted(RAW_ARTIFACT_DIR.glob("sf_*/raw_runs.parquet"))
    if not raw_paths:
        raise FileNotFoundError(
            f"No raw run artifacts found under {RAW_ARTIFACT_DIR}. "
            "Run collection before plan featurization."
        )

    raw_runs = pl.concat([pl.read_parquet(path) for path in raw_paths], how="vertical")
    successful_observations = raw_runs.filter(pl.col("status") == "success").select(
        *OBSERVATION_COLUMNS
    )
    if successful_observations.is_empty():
        raise ValueError("No successful raw observations were found to featurize.")

    duplicate_ids = (
        successful_observations.group_by("observation_id")
        .len()
        .filter(pl.col("len") > 1)
    )
    if duplicate_ids.height:
        duplicate_list = ", ".join(duplicate_ids["observation_id"].to_list())
        raise ValueError(
            "Conflicting successful raw observation rows were found for "
            f"observation_id values: {duplicate_list}"
        )

    return successful_observations.unique().sort("observation_id")


def iter_plan_records() -> Iterable[dict[str, Any]]:
    """Yield plan records from every per-scale `plans.jsonl` artifact."""
    plan_paths = sorted(RAW_ARTIFACT_DIR.glob("sf_*/plans.jsonl"))
    if not plan_paths:
        raise FileNotFoundError(
            f"No plan artifacts found under {RAW_ARTIFACT_DIR}. "
            "Run collection before plan featurization."
        )

    for path in plan_paths:
        with path.open() as plan_file:
            for line_number, line in enumerate(plan_file, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Malformed JSON in {path} at line {line_number}: {exc}"
                    ) from exc
                if not isinstance(record, dict):
                    raise ValueError(
                        f"Expected JSON object in {path} at line {line_number}."
                    )
                yield record


def build_plan_feature_row(
    observation: dict[str, Any], plan_record: dict[str, Any]
) -> dict[str, Any]:
    """Build one observation-level plan feature row."""
    plan_features = extract_plan_features(plan_record)
    return {
        "observation_id": str(observation["observation_id"]),
        "query_instance_id": str(observation["query_instance_id"]),
        "template_id": str(observation["template_id"]),
        "parameter_set_id": str(observation["parameter_set_id"]),
        "scale_factor": float(observation["scale_factor"]),
        "broadcast_to_modeling_grain": False,
        "feature_status": "available",
        **plan_features,
    }


def build_plan_feature_exclusion_row(
    observation: dict[str, Any], error: Exception
) -> dict[str, Any]:
    """Build one explicit plan-featurization exclusion row."""
    return {
        "observation_id": str(observation["observation_id"]),
        "query_instance_id": str(observation["query_instance_id"]),
        "template_id": str(observation["template_id"]),
        "parameter_set_id": str(observation["parameter_set_id"]),
        "scale_factor": float(observation["scale_factor"]),
        "broadcast_to_modeling_grain": False,
        "feature_status": "excluded",
        "parse_status": "plan_parse_error",
        "error_class": type(error).__name__,
        "error_message": str(error),
    }


def extract_plan_features(plan_record: dict[str, Any]) -> dict[str, Any]:
    """Traverse a PostgreSQL JSON plan tree and aggregate stable numeric summaries."""
    plan_document = plan_record.get("plan")
    if not isinstance(plan_document, dict):
        raise PlanFeatureError("Plan record is missing the top-level `plan` object.")
    root_plan = plan_document.get("Plan")
    if not isinstance(root_plan, dict):
        raise PlanFeatureError("Plan record is missing the root `Plan` node.")

    node_type_counts = {column: 0 for column in NODE_TYPE_COUNT_COLUMNS.values()}
    other_node_count = 0
    plan_node_count = 0
    join_node_count = 0
    scan_node_count = 0
    aggregate_node_count = 0
    sort_node_count = 0
    plan_depth_max = 0
    plan_rows_values: list[float] = []
    plan_width_values: list[float] = []
    startup_cost_values: list[float] = []
    total_cost_values: list[float] = []
    stack: list[tuple[dict[str, Any], int]] = [(root_plan, 1)]

    while stack:
        node, depth = stack.pop()
        if not isinstance(node, dict):
            raise PlanFeatureError("Encountered a non-object plan node.")
        plan_node_count += 1
        plan_depth_max = max(plan_depth_max, depth)

        node_type = node.get("Node Type")
        if not isinstance(node_type, str) or not node_type:
            raise PlanFeatureError("Encountered a plan node without `Node Type`.")

        node_column = NODE_TYPE_COUNT_COLUMNS.get(node_type)
        if node_column is None:
            other_node_count += 1
        else:
            node_type_counts[node_column] += 1

        if _is_join_node(node_type):
            join_node_count += 1
        if _is_scan_node(node_type):
            scan_node_count += 1
        if _is_aggregate_node(node_type):
            aggregate_node_count += 1
        if _is_sort_node(node_type):
            sort_node_count += 1

        plan_rows = _require_numeric(node, "Plan Rows")
        plan_width = _require_numeric(node, "Plan Width")
        startup_cost = _require_numeric(node, "Startup Cost")
        total_cost = _require_numeric(node, "Total Cost")
        plan_rows_values.append(plan_rows)
        plan_width_values.append(plan_width)
        startup_cost_values.append(startup_cost)
        total_cost_values.append(total_cost)

        child_nodes = node.get("Plans", [])
        if child_nodes is None:
            child_nodes = []
        if not isinstance(child_nodes, list):
            raise PlanFeatureError(
                "Plan node `Plans` field must be a list when present."
            )
        for child in reversed(child_nodes):
            stack.append((child, depth + 1))

    return {
        "plan_node_count": plan_node_count,
        "join_node_count": join_node_count,
        "scan_node_count": scan_node_count,
        "aggregate_node_count": aggregate_node_count,
        "sort_node_count": sort_node_count,
        "plan_depth_max": plan_depth_max,
        "planner_estimated_rows": plan_rows_values[0],
        "planner_estimated_rows_sum": sum(plan_rows_values),
        "planner_estimated_rows_max": max(plan_rows_values),
        "planner_estimated_width": plan_width_values[0],
        "planner_estimated_width_sum": sum(plan_width_values),
        "planner_estimated_width_max": max(plan_width_values),
        "planner_startup_cost": startup_cost_values[0],
        "planner_startup_cost_sum": sum(startup_cost_values),
        "planner_startup_cost_max": max(startup_cost_values),
        "planner_total_cost": total_cost_values[0],
        "planner_total_cost_sum": sum(total_cost_values),
        "planner_total_cost_max": max(total_cost_values),
        **node_type_counts,
        "other_node_count": other_node_count,
    }


def validate_plan_feature_schema(features_df: pl.DataFrame) -> None:
    """Ensure the plan feature artifact columns match the frozen schema contract."""
    schema = load_schema(PLAN_FEATURE_SCHEMA_PATH)
    required_columns = set(schema["required"])
    property_columns = set(schema["properties"])
    actual_columns = set(features_df.columns)

    missing_columns = sorted(required_columns - actual_columns)
    extra_columns = sorted(actual_columns - property_columns)
    if missing_columns or extra_columns:
        details = json.dumps(
            {
                "missing_columns": missing_columns,
                "extra_columns": extra_columns,
            },
            indent=2,
        )
        raise ValueError(f"Plan feature schema coverage failed:\n{details}")


def validate_plan_feature_coverage(
    observations: pl.DataFrame,
    features_df: pl.DataFrame,
    exclusions_df: pl.DataFrame,
) -> None:
    """Prove that feature rows plus exclusions exactly cover raw observations."""
    raw_ids = set(observations["observation_id"].to_list())
    feature_ids = set(features_df["observation_id"].to_list())
    exclusion_ids = set(exclusions_df["observation_id"].to_list())

    if features_df.height != len(feature_ids):
        raise ValueError(
            "Plan feature artifact contains duplicate observation_id rows."
        )
    if exclusions_df.height != len(exclusion_ids):
        raise ValueError(
            "Plan feature exclusion artifact contains duplicate observation_id rows."
        )
    if feature_ids & exclusion_ids:
        raise ValueError(
            "Plan feature rows and exclusion rows are not disjoint by observation_id."
        )
    if raw_ids != feature_ids | exclusion_ids:
        missing = sorted(raw_ids - (feature_ids | exclusion_ids))
        unexpected = sorted((feature_ids | exclusion_ids) - raw_ids)
        details = json.dumps(
            {
                "missing_observation_ids": missing,
                "unexpected_observation_ids": unexpected,
            },
            indent=2,
        )
        raise ValueError(f"Plan feature coverage failed:\n{details}")


def dataframe_from_rows(rows: list[dict[str, Any]], schema: pl.Schema) -> pl.DataFrame:
    """Materialize rows into a DataFrame with a stable schema, even when empty."""
    return pl.DataFrame(rows, schema=schema, orient="row")


def _is_join_node(node_type: str) -> bool:
    return node_type in {"Hash Join", "Merge Join", "Nested Loop"}


def _is_scan_node(node_type: str) -> bool:
    return "Scan" in node_type


def _is_aggregate_node(node_type: str) -> bool:
    return "Aggregate" in node_type


def _is_sort_node(node_type: str) -> bool:
    return "Sort" in node_type


def _require_numeric(node: dict[str, Any], key: str) -> float:
    value = node.get(key)
    if not isinstance(value, int | float):
        raise PlanFeatureError(f"Plan node is missing numeric `{key}`.")
    return float(value)
