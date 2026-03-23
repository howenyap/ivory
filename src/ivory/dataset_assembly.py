"""Final modeling dataset assembly for phase 2c."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from ivory.collection import format_progress, log_progress
from ivory.config import load_schema

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "raw"
FEATURE_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "features"
SQL_FEATURES_PATH = FEATURE_ARTIFACT_DIR / "sql_features.parquet"
SQL_FEATURE_EXCLUSIONS_PATH = FEATURE_ARTIFACT_DIR / "sql_feature_exclusions.parquet"
PLAN_FEATURES_PATH = FEATURE_ARTIFACT_DIR / "plan_features.parquet"
PLAN_FEATURE_EXCLUSIONS_PATH = FEATURE_ARTIFACT_DIR / "plan_feature_exclusions.parquet"
FEATURES_PATH = FEATURE_ARTIFACT_DIR / "features.parquet"
FEATURES_SCHEMA_PATH = ROOT_DIR / "schemas" / "features.schema.json"

RAW_SUCCESS_COLUMNS = (
    "observation_id",
    "run_attempt_id",
    "query_instance_id",
    "template_id",
    "parameter_set_id",
    "scale_factor",
    "planner_total_cost",
    "planning_time_ms",
    "execution_time_ms",
)
SQL_JOIN_KEYS = (
    "query_instance_id",
    "template_id",
    "parameter_set_id",
    "scale_factor",
)
PLAN_AUDIT_KEYS = (
    "query_instance_id",
    "template_id",
    "parameter_set_id",
    "scale_factor",
)


def assemble_feature_dataset() -> dict[str, Any]:
    """Assemble the final observation-grain modeling dataset."""
    features_schema = load_schema(FEATURES_SCHEMA_PATH)
    sql_feature_columns = tuple(
        features_schema["properties"]["sql_features"]["required"]
    )
    plan_feature_columns = tuple(
        features_schema["properties"]["plan_features"]["required"]
    )

    successful_observations = load_successful_observations()
    sql_features = pl.read_parquet(SQL_FEATURES_PATH)
    sql_feature_exclusions = pl.read_parquet(SQL_FEATURE_EXCLUSIONS_PATH)
    plan_features = pl.read_parquet(PLAN_FEATURES_PATH)
    plan_feature_exclusions = pl.read_parquet(PLAN_FEATURE_EXCLUSIONS_PATH)

    eligible_observations = apply_feature_exclusions(
        successful_observations=successful_observations,
        sql_feature_exclusions=sql_feature_exclusions,
        plan_feature_exclusions=plan_feature_exclusions,
    )
    log_progress(
        "dataset assembly start | "
        f"successful_observations={successful_observations.height} "
        f"eligible_observations={eligible_observations.height}",
        level="info",
    )

    validate_sql_feature_join_keys(sql_features)
    validate_plan_feature_join_keys(plan_features)
    validate_no_duplicate_rows(
        eligible_observations, "observation_id", "raw observations"
    )
    validate_no_duplicate_rows(
        sql_features, "query_instance_id", "SQL feature artifact"
    )
    validate_no_duplicate_rows(plan_features, "observation_id", "plan feature artifact")

    joined = eligible_observations.join(
        sql_features.select(
            *SQL_JOIN_KEYS,
            "broadcast_to_modeling_grain",
            "feature_status",
            *sql_feature_columns,
        ),
        on=list(SQL_JOIN_KEYS),
        how="left",
        validate="m:1",
    ).join(
        plan_features.select(
            "observation_id",
            *PLAN_AUDIT_KEYS,
            "broadcast_to_modeling_grain",
            "feature_status",
            *plan_feature_columns,
        ),
        on="observation_id",
        how="left",
        suffix="_plan",
        validate="1:1",
    )

    validate_join_completeness(joined, "feature_status", "SQL features")
    validate_join_completeness(joined, "feature_status_plan", "plan features")
    validate_plan_key_alignment(joined)
    validate_target_nulls(joined)

    rows = build_feature_rows(
        joined=joined,
        sql_feature_columns=sql_feature_columns,
        plan_feature_columns=plan_feature_columns,
    )
    features_df = pl.DataFrame(rows, orient="row").with_columns(
        pl.col("null_indicator_columns").cast(pl.List(pl.String))
    )
    validate_features_schema(features_df, features_schema)
    validate_feature_coverage(eligible_observations, features_df)

    FEATURE_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    features_df.write_parquet(FEATURES_PATH)
    log_progress(
        "dataset assembly complete | "
        f"completed={format_progress(features_df.height, features_df.height)} "
        f"features={features_df.height}",
        level="success",
    )

    return {
        "features_path": str(FEATURES_PATH),
        "successful_observations": successful_observations.height,
        "eligible_observations": eligible_observations.height,
        "feature_rows": features_df.height,
        "sql_feature_exclusions": sql_feature_exclusions.height,
        "plan_feature_exclusions": plan_feature_exclusions.height,
    }


def load_successful_observations() -> pl.DataFrame:
    """Load canonical successful raw observations for the final modeling dataset."""
    raw_paths = sorted(RAW_ARTIFACT_DIR.glob("sf_*/raw_runs.parquet"))
    if not raw_paths:
        raise FileNotFoundError(
            f"No raw run artifacts found under {RAW_ARTIFACT_DIR}. "
            "Run collection before dataset assembly."
        )

    raw_runs = pl.concat([pl.read_parquet(path) for path in raw_paths], how="vertical")
    successful_observations = (
        raw_runs.filter(
            (pl.col("status") == "success")
            & pl.col("include_in_modeling")
            & ~pl.col("is_excluded")
        )
        .select(*RAW_SUCCESS_COLUMNS)
        .sort("observation_id")
    )
    if successful_observations.is_empty():
        raise ValueError(
            "No successful raw observations were available for dataset assembly."
        )

    return successful_observations


def apply_feature_exclusions(
    *,
    successful_observations: pl.DataFrame,
    sql_feature_exclusions: pl.DataFrame,
    plan_feature_exclusions: pl.DataFrame,
) -> pl.DataFrame:
    """Remove observations explicitly excluded by upstream feature stages."""
    eligible = successful_observations
    if sql_feature_exclusions.height:
        eligible = eligible.join(
            sql_feature_exclusions.select("query_instance_id").unique(),
            on="query_instance_id",
            how="anti",
        )
    if plan_feature_exclusions.height:
        eligible = eligible.join(
            plan_feature_exclusions.select("observation_id").unique(),
            on="observation_id",
            how="anti",
        )
    if eligible.is_empty():
        raise ValueError(
            "Every successful raw observation was excluded before dataset assembly."
        )
    return eligible.sort("observation_id")


def build_feature_rows(
    *,
    joined: pl.DataFrame,
    sql_feature_columns: tuple[str, ...],
    plan_feature_columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Materialize final nested rows according to the frozen output schema."""
    rows: list[dict[str, Any]] = []
    for row in joined.iter_rows(named=True):
        sql_feature_values = {column: row[column] for column in sql_feature_columns}
        plan_feature_values = {column: row[column] for column in plan_feature_columns}
        null_indicator_columns = sorted(
            [
                *(
                    f"sql_features.{column}"
                    for column, value in sql_feature_values.items()
                    if value is None
                ),
                *(
                    f"plan_features.{column}"
                    for column, value in plan_feature_values.items()
                    if value is None
                ),
            ]
        )

        rows.append(
            {
                "observation_id": row["observation_id"],
                "run_attempt_id": row["run_attempt_id"],
                "query_instance_id": row["query_instance_id"],
                "template_id": row["template_id"],
                "parameter_set_id": row["parameter_set_id"],
                "scale_factor": row["scale_factor"],
                "sql_features_broadcast": row["broadcast_to_modeling_grain"],
                "plan_features_broadcast": row["broadcast_to_modeling_grain_plan"],
                "null_indicator_columns": null_indicator_columns,
                "targets": {
                    "planner_total_cost": row["planner_total_cost"],
                    "planning_time_ms": row["planning_time_ms"],
                    "execution_time_ms": row["execution_time_ms"],
                },
                "sql_features": sql_feature_values,
                "plan_features": plan_feature_values,
            }
        )
    return rows


def validate_sql_feature_join_keys(sql_features: pl.DataFrame) -> None:
    """Ensure SQL features stay at the query-instance grain and remain join-safe."""
    conflicts = (
        sql_features.group_by("query_instance_id")
        .agg(
            pl.col("template_id").n_unique().alias("template_id_unique"),
            pl.col("parameter_set_id").n_unique().alias("parameter_set_id_unique"),
            pl.col("scale_factor").n_unique().alias("scale_factor_unique"),
        )
        .filter(
            (pl.col("template_id_unique") > 1)
            | (pl.col("parameter_set_id_unique") > 1)
            | (pl.col("scale_factor_unique") > 1)
        )
    )
    if conflicts.height:
        raise ValueError("SQL feature artifact has conflicting join keys.")


def validate_plan_feature_join_keys(plan_features: pl.DataFrame) -> None:
    """Ensure plan features stay at the observation grain and retain audit keys."""
    conflicts = (
        plan_features.group_by("observation_id")
        .agg(
            pl.col("query_instance_id").n_unique().alias("query_instance_id_unique"),
            pl.col("template_id").n_unique().alias("template_id_unique"),
            pl.col("parameter_set_id").n_unique().alias("parameter_set_id_unique"),
            pl.col("scale_factor").n_unique().alias("scale_factor_unique"),
        )
        .filter(
            (pl.col("query_instance_id_unique") > 1)
            | (pl.col("template_id_unique") > 1)
            | (pl.col("parameter_set_id_unique") > 1)
            | (pl.col("scale_factor_unique") > 1)
        )
    )
    if conflicts.height:
        raise ValueError("Plan feature artifact has conflicting observation keys.")


def validate_no_duplicate_rows(
    frame: pl.DataFrame, key: str, artifact_name: str
) -> None:
    """Reject duplicate key rows before assembly joins can multiply them."""
    duplicates = frame.group_by(key).len().filter(pl.col("len") > 1)
    if duplicates.height:
        duplicate_values = ", ".join(duplicates[key].to_list())
        raise ValueError(
            f"{artifact_name} contains duplicate {key} rows: {duplicate_values}"
        )


def validate_join_completeness(
    joined: pl.DataFrame, indicator_column: str, artifact_name: str
) -> None:
    """Fail fast when a required left join would introduce unexpected nulls."""
    missing = joined.filter(pl.col(indicator_column).is_null()).select("observation_id")
    if missing.height:
        raise ValueError(
            f"Dataset assembly missing {artifact_name} for observation_id values: "
            + ", ".join(missing["observation_id"].to_list())
        )


def validate_plan_key_alignment(joined: pl.DataFrame) -> None:
    """Ensure observation-level plan rows agree with canonical raw identifiers."""
    mismatches = joined.filter(
        (pl.col("query_instance_id") != pl.col("query_instance_id_plan"))
        | (pl.col("template_id") != pl.col("template_id_plan"))
        | (pl.col("parameter_set_id") != pl.col("parameter_set_id_plan"))
        | (pl.col("scale_factor") != pl.col("scale_factor_plan"))
    ).select("observation_id")
    if mismatches.height:
        raise ValueError(
            "Plan feature join keys disagree with raw observation keys for "
            + ", ".join(mismatches["observation_id"].to_list())
        )


def validate_target_nulls(joined: pl.DataFrame) -> None:
    """Required targets may not be null in the successful observation dataset."""
    null_targets = joined.filter(
        pl.any_horizontal(
            pl.col("planner_total_cost").is_null(),
            pl.col("planning_time_ms").is_null(),
            pl.col("execution_time_ms").is_null(),
        )
    ).select("observation_id")
    if null_targets.height:
        raise ValueError(
            "Successful observations are missing required targets for "
            + ", ".join(null_targets["observation_id"].to_list())
        )


def validate_features_schema(
    features_df: pl.DataFrame, features_schema: dict[str, Any]
) -> None:
    """Ensure the assembled feature artifact matches the frozen output schema."""
    required_columns = set(features_schema["required"])
    property_columns = set(features_schema["properties"])
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
        raise ValueError(f"Feature schema coverage failed:\n{details}")

    null_indicator_dtype = features_df.schema["null_indicator_columns"]
    if null_indicator_dtype != pl.List(pl.String):
        raise ValueError(
            "Feature schema type mismatch for null_indicator_columns: "
            f"{null_indicator_dtype!s}"
        )

    target_field_names = _struct_field_names(features_df.schema["targets"])
    expected_target_field_names = list(
        features_schema["properties"]["targets"]["required"]
    )
    if target_field_names != expected_target_field_names:
        raise ValueError(
            "Feature schema field mismatch for targets: "
            f"expected={expected_target_field_names} actual={target_field_names}"
        )

    sql_feature_field_names = _struct_field_names(features_df.schema["sql_features"])
    expected_sql_feature_field_names = list(
        features_schema["properties"]["sql_features"]["required"]
    )
    if sql_feature_field_names != expected_sql_feature_field_names:
        detail = (
            f"expected={expected_sql_feature_field_names} "
            f"actual={sql_feature_field_names}"
        )
        raise ValueError(f"Feature schema field mismatch for sql_features: {detail}")

    plan_feature_field_names = _struct_field_names(features_df.schema["plan_features"])
    expected_plan_feature_field_names = list(
        features_schema["properties"]["plan_features"]["required"]
    )
    if plan_feature_field_names != expected_plan_feature_field_names:
        detail = (
            f"expected={expected_plan_feature_field_names} "
            f"actual={plan_feature_field_names}"
        )
        raise ValueError(f"Feature schema field mismatch for plan_features: {detail}")


def validate_feature_coverage(
    eligible_observations: pl.DataFrame, features_df: pl.DataFrame
) -> None:
    """Prove that final rows exactly cover the eligible successful observations."""
    raw_ids = set(eligible_observations["observation_id"].to_list())
    feature_ids = set(features_df["observation_id"].to_list())

    if features_df.height != len(feature_ids):
        raise ValueError(
            "Final feature artifact contains duplicate observation_id rows."
        )
    if raw_ids != feature_ids:
        missing = sorted(raw_ids - feature_ids)
        unexpected = sorted(feature_ids - raw_ids)
        details = json.dumps(
            {
                "missing_observation_ids": missing,
                "unexpected_observation_ids": unexpected,
            },
            indent=2,
        )
        raise ValueError(f"Final feature coverage failed:\n{details}")


def _struct_field_names(dtype: pl.DataType) -> list[str]:
    """Return ordered struct field names for schema validation."""
    if not isinstance(dtype, pl.Struct):
        raise ValueError(f"Expected struct dtype, got {dtype!s}")
    return [field.name for field in dtype.fields]
