"""SQL structural feature extraction for phase 2a."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from ivory.collection import format_progress, log_progress
from ivory.config import load_schema

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "raw"
FEATURE_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "features"
SQL_FEATURES_PATH = FEATURE_ARTIFACT_DIR / "sql_features.parquet"
SQL_FEATURE_EXCLUSIONS_PATH = FEATURE_ARTIFACT_DIR / "sql_feature_exclusions.parquet"
SQL_FEATURE_SCHEMA_PATH = ROOT_DIR / "schemas" / "sql_features.schema.json"

QUERY_INSTANCE_COLUMNS = (
    "query_instance_id",
    "template_id",
    "parameter_set_id",
    "scale_factor",
    "sql_text",
)
SQL_FEATURE_POLARS_SCHEMA = pl.Schema(
    {
        "query_instance_id": pl.String,
        "template_id": pl.String,
        "parameter_set_id": pl.String,
        "scale_factor": pl.Float64,
        "broadcast_to_modeling_grain": pl.Boolean,
        "feature_status": pl.String,
        "aggregation_present": pl.Boolean,
        "selected_column_count": pl.Int64,
        "table_count": pl.Int64,
        "join_count": pl.Int64,
        "predicate_count": pl.Int64,
        "group_by_count": pl.Int64,
        "order_by_count": pl.Int64,
        "limit_count": pl.Int64,
        "subquery_count": pl.Int64,
    }
)
SQL_FEATURE_EXCLUSION_POLARS_SCHEMA = pl.Schema(
    {
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


def featurize_sql_queries() -> dict[str, Any]:
    """Extract SQL structural features from successful raw query instances."""
    query_instances = load_successful_query_instances()
    feature_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    total_query_instances = query_instances.height
    log_progress(
        f"sql featurization start | query_instances={total_query_instances}",
        level="info",
    )

    for index, query_instance in enumerate(
        query_instances.iter_rows(named=True), start=1
    ):
        try:
            parsed = sqlglot.parse_one(query_instance["sql_text"], read="postgres")
        except ParseError as exc:
            exclusion_rows.append(build_sql_feature_exclusion_row(query_instance, exc))
            log_sql_featurization_progress(
                index=index,
                total=total_query_instances,
                query_instance_id=str(query_instance["query_instance_id"]),
                status="excluded",
                level="warning",
            )
            continue

        feature_rows.append(build_sql_feature_row(query_instance, parsed))
        if index == 1 or index == total_query_instances or index % 100 == 0:
            log_sql_featurization_progress(
                index=index,
                total=total_query_instances,
                query_instance_id=str(query_instance["query_instance_id"]),
                status="available",
                level="info",
            )

    features_df = dataframe_from_rows(feature_rows, SQL_FEATURE_POLARS_SCHEMA)
    exclusions_df = dataframe_from_rows(
        exclusion_rows, SQL_FEATURE_EXCLUSION_POLARS_SCHEMA
    )
    validate_sql_feature_schema(features_df)
    validate_sql_feature_coverage(query_instances, features_df, exclusions_df)

    FEATURE_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    features_df.write_parquet(SQL_FEATURES_PATH)
    exclusions_df.write_parquet(SQL_FEATURE_EXCLUSIONS_PATH)
    log_progress(
        "sql featurization complete | "
        f"completed={format_progress(total_query_instances, total_query_instances)} "
        f"features={features_df.height} exclusions={exclusions_df.height}",
        level="success",
    )

    return {
        "sql_features_path": str(SQL_FEATURES_PATH),
        "sql_feature_exclusions_path": str(SQL_FEATURE_EXCLUSIONS_PATH),
        "input_query_instances": query_instances.height,
        "feature_rows": features_df.height,
        "exclusion_rows": exclusions_df.height,
    }


def log_sql_featurization_progress(
    *,
    index: int,
    total: int,
    query_instance_id: str,
    status: str,
    level: str,
) -> None:
    """Emit a compact progress line for SQL featurization."""
    log_progress(
        "sql featurization | "
        f"{format_progress(index, total)} "
        f"query_instance_id={query_instance_id} status={status}",
        level=level,
    )


def load_successful_query_instances() -> pl.DataFrame:
    """Load the canonical successful query-instance inputs from raw artifacts."""
    raw_paths = sorted(RAW_ARTIFACT_DIR.glob("sf_*/raw_runs.parquet"))
    if not raw_paths:
        raise FileNotFoundError(
            f"No raw run artifacts found under {RAW_ARTIFACT_DIR}. "
            "Run collection before SQL featurization."
        )

    raw_runs = pl.concat([pl.read_parquet(path) for path in raw_paths], how="vertical")
    successful_query_instances = (
        raw_runs.filter(pl.col("status") == "success")
        .select(*QUERY_INSTANCE_COLUMNS)
        .unique()
        .sort("query_instance_id")
    )
    if successful_query_instances.is_empty():
        raise ValueError("No successful raw query instances were found to featurize.")

    duplicate_ids = (
        successful_query_instances.group_by("query_instance_id")
        .len()
        .filter(pl.col("len") > 1)
    )
    if duplicate_ids.height:
        duplicate_list = ", ".join(duplicate_ids["query_instance_id"].to_list())
        raise ValueError(
            "Conflicting successful raw query-instance rows were found for "
            f"query_instance_id values: {duplicate_list}"
        )

    return successful_query_instances


def build_sql_feature_row(
    query_instance: dict[str, Any], parsed_sql: Any
) -> dict[str, Any]:
    """Build one SQL feature row at query-instance grain."""
    features = extract_sql_features(parsed_sql)
    return {
        "query_instance_id": str(query_instance["query_instance_id"]),
        "template_id": str(query_instance["template_id"]),
        "parameter_set_id": str(query_instance["parameter_set_id"]),
        "scale_factor": float(query_instance["scale_factor"]),
        "broadcast_to_modeling_grain": True,
        "feature_status": "available",
        **features,
    }


def build_sql_feature_exclusion_row(
    query_instance: dict[str, Any], error: ParseError
) -> dict[str, Any]:
    """Build one explicit SQL-featurization exclusion row."""
    return {
        "query_instance_id": str(query_instance["query_instance_id"]),
        "template_id": str(query_instance["template_id"]),
        "parameter_set_id": str(query_instance["parameter_set_id"]),
        "scale_factor": float(query_instance["scale_factor"]),
        "broadcast_to_modeling_grain": True,
        "feature_status": "excluded",
        "parse_status": "parse_error",
        "error_class": type(error).__name__,
        "error_message": str(error),
    }


def extract_sql_features(parsed_sql: Any) -> dict[str, int]:
    """Count stable structural SQL features from a parsed AST."""
    cte_names = {
        cte.alias_or_name
        for cte in parsed_sql.find_all(exp.CTE)
        if cte.alias_or_name is not None
    }

    aggregation_present = any(True for _ in parsed_sql.find_all(exp.AggFunc))
    selected_column_count = len(getattr(parsed_sql, "selects", []))
    table_count = sum(
        1 for table in parsed_sql.find_all(exp.Table) if table.name not in cte_names
    )
    join_count = sum(1 for _ in parsed_sql.find_all(exp.Join))
    predicate_count = sum(1 for _ in parsed_sql.find_all(exp.Predicate))
    group_by_count = sum(
        len(group.expressions)
        for group in parsed_sql.find_all(exp.Group)
        if group.expressions
    )
    order_by_count = sum(
        len(order.expressions)
        for order in parsed_sql.find_all(exp.Order)
        if order.expressions
    )
    limit_count = sum(1 for _ in parsed_sql.find_all(exp.Limit))
    subquery_count = sum(1 for _ in parsed_sql.find_all(exp.Subquery)) + sum(
        1 for _ in parsed_sql.find_all(exp.Exists)
    )

    return {
        "aggregation_present": aggregation_present,
        "selected_column_count": selected_column_count,
        "table_count": table_count,
        "join_count": join_count,
        "predicate_count": predicate_count,
        "group_by_count": group_by_count,
        "order_by_count": order_by_count,
        "limit_count": limit_count,
        "subquery_count": subquery_count,
    }


def validate_sql_feature_schema(features_df: pl.DataFrame) -> None:
    """Ensure the feature artifact columns match the frozen schema contract."""
    schema = load_schema(SQL_FEATURE_SCHEMA_PATH)
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
        raise ValueError(f"SQL feature schema coverage failed:\n{details}")


def validate_sql_feature_coverage(
    query_instances: pl.DataFrame,
    features_df: pl.DataFrame,
    exclusions_df: pl.DataFrame,
) -> None:
    """Prove that feature rows plus exclusions exactly cover raw query instances."""
    raw_ids = set(query_instances["query_instance_id"].to_list())
    feature_ids = set(features_df["query_instance_id"].to_list())
    exclusion_ids = set(exclusions_df["query_instance_id"].to_list())

    if features_df.height != len(feature_ids):
        raise ValueError(
            "SQL feature artifact contains duplicate query_instance_id rows."
        )
    if exclusions_df.height != len(exclusion_ids):
        raise ValueError(
            "SQL feature exclusion artifact contains duplicate query_instance_id rows."
        )
    if feature_ids & exclusion_ids:
        raise ValueError(
            "SQL feature rows and exclusion rows are not disjoint by query_instance_id."
        )
    if raw_ids != feature_ids | exclusion_ids:
        missing = sorted(raw_ids - (feature_ids | exclusion_ids))
        unexpected = sorted((feature_ids | exclusion_ids) - raw_ids)
        details = json.dumps(
            {
                "missing_query_instance_ids": missing,
                "unexpected_query_instance_ids": unexpected,
            },
            indent=2,
        )
        raise ValueError(f"SQL feature coverage failed:\n{details}")


def dataframe_from_rows(rows: list[dict[str, Any]], schema: pl.Schema) -> pl.DataFrame:
    """Materialize rows into a DataFrame with a stable schema, even when empty."""
    return pl.DataFrame(rows, schema=schema, orient="row")
