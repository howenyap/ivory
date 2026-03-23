"""Baseline training pipeline for phase 3a."""

from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import polars as pl
from jsonschema import Draft202012Validator
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ivory.collection import log_progress
from ivory.config import load_config, load_schema

ROOT_DIR = Path(__file__).resolve().parents[2]
FEATURES_PATH = ROOT_DIR / "artifacts" / "features" / "features.parquet"
FEATURES_SCHEMA_PATH = ROOT_DIR / "schemas" / "features.schema.json"
MODELS_DIR = ROOT_DIR / "artifacts" / "models"
BASELINE_METRICS_PATH = MODELS_DIR / "baseline_metrics.json"
BASELINE_PREDICTIONS_PATH = MODELS_DIR / "baseline_predictions.parquet"
TRAINING_MANIFEST_PATH = MODELS_DIR / "training_manifest.json"
BASELINE_SCHEMA_PATH = ROOT_DIR / "schemas" / "baseline_metrics.schema.json"

TARGET_NAMES = (
    "planner_total_cost",
    "planning_time_ms",
    "execution_time_ms",
)
IDENTIFIER_COLUMNS = (
    "observation_id",
    "run_attempt_id",
    "query_instance_id",
    "template_id",
    "parameter_set_id",
)
BASELINE_TEST_FRACTION = 0.2
BASELINE_VALIDATION_FRACTION = 0.2


@dataclass(frozen=True)
class SplitAssignments:
    """Deterministic split membership for the baseline pipeline."""

    train_query_instance_ids: tuple[str, ...]
    validation_query_instance_ids: tuple[str, ...]
    test_query_instance_ids: tuple[str, ...]


def train_baseline_models(
    *, seed: int | None = None, scale_factor: float | None = None
) -> dict[str, Any]:
    """Train baseline regressors and emit stable artifacts."""
    config = load_config()
    experiment = config["experiment"]
    training_seed = int(experiment["seed"] if seed is None else seed)
    split_mode = str(experiment["split_modes"]["baseline"])

    features_df = load_modeling_dataset(scale_factor=scale_factor)
    modeling_df, selected_features = flatten_modeling_dataset(features_df)
    split = build_split_assignments(modeling_df, training_seed)
    partitioned = add_dataset_partition(modeling_df, split)
    train_df = partitioned.filter(pl.col("dataset_partition") == "train")
    validation_df = partitioned.filter(pl.col("dataset_partition") == "validation")
    test_df = partitioned.filter(pl.col("dataset_partition") == "test")

    preprocessing_choices = {
        "struct_flattening": (
            "flatten nested SQL and plan feature structs into top-level "
            "columns with family prefixes"
        ),
        "null_indicators": (
            "derive binary indicator columns for every flattened feature "
            "column and fill null feature values with zero after indicator "
            "extraction"
        ),
        "bool_cast": (
            "cast boolean feature leaves and null indicators to Float64 "
            "before model fitting"
        ),
        "scale_factor_filter": None if scale_factor is None else float(scale_factor),
        "validation_selection": (
            "select the canonical baseline model family per target using "
            "validation RMSE, then refit the selected family on "
            "train+validation before held-out test evaluation"
        ),
        "supplemental_metrics": (
            "record sMAPE for every target and rank correlation for "
            "execution_time_ms in the training manifest because the frozen "
            "baseline_metrics schema does not allow extra keys"
        ),
        "constant_feature_detection": (
            "detect and exclude constant features using the training "
            "partition only so held-out rows never influence preprocessing"
        ),
    }

    constant_feature_columns = determine_constant_feature_columns(
        train_df, selected_features
    )
    per_target_results: dict[str, dict[str, Any]] = {}
    predictions_rows: list[dict[str, Any]] = []
    final_model_input_columns_per_model: dict[str, dict[str, list[str]]] = {}
    model_results_manifest: dict[str, dict[str, Any]] = {}
    model_artifact_paths: dict[str, dict[str, str]] = {}
    selected_model_family_per_target: dict[str, str] = {}
    excluded_columns = sorted(
        [
            *IDENTIFIER_COLUMNS,
            "dataset_partition",
            *TARGET_NAMES,
            *constant_feature_columns,
        ]
    )

    for target_name in TARGET_NAMES:
        target_exclusions = determine_target_exclusions(target_name)
        final_feature_columns = [
            column
            for column in selected_features
            if column not in excluded_columns and column not in target_exclusions
        ]
        for model_family in model_family_names():
            final_model_input_columns_per_model.setdefault(model_family, {})[
                target_name
            ] = list(final_feature_columns)

        family_results, family_predictions, final_estimators = train_target_models(
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
            target_name=target_name,
            feature_columns=final_feature_columns,
            seed=training_seed,
        )
        model_results_manifest[target_name] = family_results
        model_artifact_paths[target_name] = save_final_estimators(
            target_name=target_name,
            estimators=final_estimators,
        )

        selected_model_family = select_model_family(family_results)
        selected_model_family_per_target[target_name] = selected_model_family
        selected_result = family_results[selected_model_family]
        per_target_results[target_name] = selected_result["test_metrics"]
        predictions_rows.extend(
            row for row in family_predictions if row["target_name"] == target_name
        )

    metrics_artifact = {
        "artifact_path": "artifacts/models/baseline_metrics.json",
        "split_mode": split_mode,
        "targets": per_target_results,
    }
    validate_metrics_artifact(
        artifact=metrics_artifact,
        schema_path=BASELINE_SCHEMA_PATH,
    )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_METRICS_PATH.write_text(
        json.dumps(metrics_artifact, indent=2, sort_keys=True) + "\n"
    )
    build_predictions_dataframe(predictions_rows).write_parquet(
        BASELINE_PREDICTIONS_PATH
    )

    training_manifest = {
        "artifact_paths": {
            "baseline_metrics": str(BASELINE_METRICS_PATH.relative_to(ROOT_DIR)),
            "baseline_predictions": str(
                BASELINE_PREDICTIONS_PATH.relative_to(ROOT_DIR)
            ),
            "training_manifest": str(TRAINING_MANIFEST_PATH.relative_to(ROOT_DIR)),
        },
        "selected_features": selected_features,
        "excluded_columns": excluded_columns,
        "target_specific_excluded_columns": {
            target_name: determine_target_exclusions(target_name)
            for target_name in TARGET_NAMES
        },
        "final_model_input_columns_per_model": final_model_input_columns_per_model,
        "target_names": list(TARGET_NAMES),
        "split": serialize_split_manifest(
            split=split,
            split_mode=split_mode,
            training_seed=training_seed,
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
        ),
        "seed": training_seed,
        "model_family_names": model_family_names(),
        "model_artifact_paths": model_artifact_paths,
        "selected_model_family_per_target": selected_model_family_per_target,
        "preprocessing_choices": preprocessing_choices,
        "model_results": model_results_manifest,
    }
    TRAINING_MANIFEST_PATH.write_text(
        json.dumps(training_manifest, indent=2, sort_keys=True) + "\n"
    )

    log_progress(
        "baseline training complete | "
        f"rows={features_df.height} "
        f"train={train_df.height} "
        f"validation={validation_df.height} "
        f"test={test_df.height}",
        level="success",
    )

    return {
        "rows": features_df.height,
        "train_rows": train_df.height,
        "validation_rows": validation_df.height,
        "test_rows": test_df.height,
        "metrics_path": str(BASELINE_METRICS_PATH),
        "predictions_path": str(BASELINE_PREDICTIONS_PATH),
        "manifest_path": str(TRAINING_MANIFEST_PATH),
    }


def load_modeling_dataset(*, scale_factor: float | None) -> pl.DataFrame:
    """Load the assembled modeling dataset, optionally filtering by scale factor."""
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"Missing modeling dataset at {FEATURES_PATH}. "
            "Run `uv run python -m ivory.cli featurize assemble` first."
        )

    features_df = pl.read_parquet(FEATURES_PATH).sort("observation_id")
    if scale_factor is not None:
        features_df = features_df.filter(pl.col("scale_factor") == float(scale_factor))
        if features_df.is_empty():
            raise ValueError(
                "No feature rows matched the requested scale factor "
                f"{float(scale_factor):.1f}."
            )
    return features_df


def flatten_modeling_dataset(
    features_df: pl.DataFrame,
) -> tuple[pl.DataFrame, list[str]]:
    """Flatten the nested modeling dataset into stable top-level feature columns."""
    features_schema = load_schema(FEATURES_SCHEMA_PATH)
    sql_feature_names = features_schema["properties"]["sql_features"]["required"]
    plan_feature_names = features_schema["properties"]["plan_features"]["required"]
    feature_df = features_df.select(
        *IDENTIFIER_COLUMNS,
        "scale_factor",
        "sql_features_broadcast",
        "plan_features_broadcast",
        *[
            pl.col("targets").struct.field(target_name).alias(target_name)
            for target_name in TARGET_NAMES
        ],
        *[
            pl.col("sql_features")
            .struct.field(field_name)
            .alias(f"sql_features__{field_name}")
            for field_name in sql_feature_names
        ],
        *[
            pl.col("plan_features")
            .struct.field(field_name)
            .alias(f"plan_features__{field_name}")
            for field_name in plan_feature_names
        ],
    )

    flattened_feature_columns = [
        column
        for column in feature_df.columns
        if column
        not in {
            *IDENTIFIER_COLUMNS,
            *TARGET_NAMES,
        }
    ]
    null_indicator_expressions = [
        pl.col(column).is_null().cast(pl.Float64).alias(f"null__{column}")
        for column in flattened_feature_columns
    ]
    fill_expressions = [
        cast_feature_to_float(pl.col(column)).fill_null(0.0).alias(column)
        for column in flattened_feature_columns
    ]

    modeled_df = feature_df.with_columns(*null_indicator_expressions).with_columns(
        *fill_expressions
    )
    selected_features = sorted(
        [
            *flattened_feature_columns,
            *(f"null__{column}" for column in flattened_feature_columns),
        ]
    )
    return modeled_df, selected_features


def cast_feature_to_float(expression: pl.Expr) -> pl.Expr:
    """Normalize feature dtypes to Float64 for scikit-learn estimators."""
    return expression.cast(pl.Float64, strict=False)


def build_split_assignments(modeling_df: pl.DataFrame, seed: int) -> SplitAssignments:
    """Deterministically split query instances into train, validation, and test."""
    query_instance_ids = sorted(modeling_df["query_instance_id"].unique().to_list())
    if len(query_instance_ids) < 3:
        raise ValueError(
            "Baseline training requires at least three query instances so train, "
            "validation, and test partitions are all non-empty."
        )

    shuffled = deterministic_shuffle(query_instance_ids, seed)
    test_count = bounded_partition_size(
        total=len(shuffled),
        fraction=BASELINE_TEST_FRACTION,
        minimum=1,
        maximum=len(shuffled) - 2,
    )
    remaining_after_test = len(shuffled) - test_count
    validation_count = bounded_partition_size(
        total=remaining_after_test,
        fraction=BASELINE_VALIDATION_FRACTION,
        minimum=1,
        maximum=remaining_after_test - 1,
    )

    test_ids = tuple(sorted(shuffled[:test_count]))
    validation_ids = tuple(sorted(shuffled[test_count : test_count + validation_count]))
    train_ids = tuple(sorted(shuffled[test_count + validation_count :]))
    return SplitAssignments(
        train_query_instance_ids=train_ids,
        validation_query_instance_ids=validation_ids,
        test_query_instance_ids=test_ids,
    )


def bounded_partition_size(
    *, total: int, fraction: float, minimum: int, maximum: int
) -> int:
    """Return a bounded integer partition size for deterministic splitting."""
    if maximum < minimum:
        raise ValueError("Invalid split bounds: maximum must be >= minimum.")
    proposed = int(round(total * fraction))
    return max(minimum, min(maximum, proposed))


def deterministic_shuffle(values: list[str], seed: int) -> list[str]:
    """Shuffle string values deterministically without introducing extra deps."""
    keyed = [(stable_random_key(value=value, seed=seed), value) for value in values]
    keyed.sort()
    return [value for _, value in keyed]


def stable_random_key(*, value: str, seed: int) -> str:
    """Build a stable ordering key from the seed and input value."""
    payload = f"{seed}:{value}".encode()
    return sha256(payload).hexdigest()


def add_dataset_partition(
    modeling_df: pl.DataFrame, split: SplitAssignments
) -> pl.DataFrame:
    """Annotate each row with its dataset partition."""
    train_ids = set(split.train_query_instance_ids)
    validation_ids = set(split.validation_query_instance_ids)
    test_ids = set(split.test_query_instance_ids)
    return modeling_df.with_columns(
        pl.when(pl.col("query_instance_id").is_in(train_ids))
        .then(pl.lit("train"))
        .when(pl.col("query_instance_id").is_in(validation_ids))
        .then(pl.lit("validation"))
        .when(pl.col("query_instance_id").is_in(test_ids))
        .then(pl.lit("test"))
        .otherwise(pl.lit("unknown"))
        .alias("dataset_partition")
    )


def determine_target_exclusions(target_name: str) -> list[str]:
    """Return leakage-prone or target-equivalent columns to exclude."""
    exclusions: list[str] = []
    if target_name == "planner_total_cost":
        exclusions.append("plan_features__planner_total_cost")
        exclusions.append("null__plan_features__planner_total_cost")
    return exclusions


def determine_constant_feature_columns(
    modeling_df: pl.DataFrame, selected_features: list[str]
) -> list[str]:
    """Identify constant features once so they can be excluded from all models."""
    constant_columns: list[str] = []
    for column in selected_features:
        if modeling_df.select(pl.col(column).n_unique()).item() <= 1:
            constant_columns.append(column)
    return constant_columns


def train_target_models(
    *,
    train_df: pl.DataFrame,
    validation_df: pl.DataFrame,
    test_df: pl.DataFrame,
    target_name: str,
    feature_columns: list[str],
    seed: int,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Train all model families for a single target."""
    if not feature_columns:
        raise ValueError(f"No feature columns remain for target {target_name}.")

    train_validation_df = pl.concat([train_df, validation_df], how="vertical")
    x_train = to_feature_matrix(train_df, feature_columns)
    y_train = to_target_vector(train_df, target_name)
    x_validation = to_feature_matrix(validation_df, feature_columns)
    y_validation = to_target_vector(validation_df, target_name)
    x_train_validation = to_feature_matrix(train_validation_df, feature_columns)
    y_train_validation = to_target_vector(train_validation_df, target_name)
    x_test = to_feature_matrix(test_df, feature_columns)
    y_test = to_target_vector(test_df, target_name)

    family_results: dict[str, dict[str, Any]] = {}
    final_estimators: dict[str, Any] = {}
    predictions_rows: list[dict[str, Any]] = []
    for model_family, estimator in build_model_family_estimators(seed).items():
        estimator.fit(x_train, y_train)
        validation_predictions = estimator.predict(x_validation)
        validation_metrics = compute_regression_metrics(
            y_true=y_validation,
            y_pred=validation_predictions,
        )
        supplemental_validation_metrics = compute_supplemental_metrics(
            y_true=y_validation,
            y_pred=validation_predictions,
            target_name=target_name,
        )

        final_estimator = build_model_family_estimators(seed)[model_family]
        final_estimator.fit(x_train_validation, y_train_validation)
        test_predictions = final_estimator.predict(x_test)
        test_metrics = compute_regression_metrics(
            y_true=y_test, y_pred=test_predictions
        )
        supplemental_test_metrics = compute_supplemental_metrics(
            y_true=y_test,
            y_pred=test_predictions,
            target_name=target_name,
        )
        final_estimators[model_family] = final_estimator

        family_results[model_family] = {
            "validation_metrics": validation_metrics,
            "supplemental_validation_metrics": supplemental_validation_metrics,
            "test_metrics": test_metrics,
            "supplemental_test_metrics": supplemental_test_metrics,
        }
        predictions_rows.extend(
            build_prediction_rows(
                test_df=test_df,
                target_name=target_name,
                model_family=model_family,
                actual_values=y_test,
                predicted_values=test_predictions,
            )
        )

    selected_family = select_model_family(family_results)
    for row in predictions_rows:
        row["is_selected_baseline"] = row["model_family"] == selected_family
    return family_results, predictions_rows, final_estimators


def build_model_family_estimators(seed: int) -> dict[str, Any]:
    """Create the baseline estimator set."""
    return {
        "dummy_mean": DummyRegressor(strategy="mean"),
        "ridge": Pipeline(
            steps=[
                ("scale", StandardScaler()),
                ("model", Ridge(alpha=1.0)),
            ]
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=200,
            random_state=seed,
            n_jobs=1,
        ),
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            random_state=seed,
        ),
    }


def model_family_names() -> list[str]:
    """Return the canonical model family order for artifacts."""
    return list(build_model_family_estimators(seed=0))


def select_model_family(family_results: dict[str, dict[str, Any]]) -> str:
    """Choose the canonical baseline family using validation RMSE, then MAE."""
    ordered = sorted(
        family_results.items(),
        key=lambda item: (
            item[1]["validation_metrics"]["rmse"],
            item[1]["validation_metrics"]["mae"],
            item[0],
        ),
    )
    return ordered[0][0]


def to_feature_matrix(df: pl.DataFrame, feature_columns: list[str]) -> Any:
    """Convert a Polars frame into a NumPy feature matrix."""
    return df.select(feature_columns).to_numpy()


def to_target_vector(df: pl.DataFrame, target_name: str) -> Any:
    """Convert a target column into a NumPy vector."""
    return df[target_name].to_numpy()


def compute_regression_metrics(*, y_true: Any, y_pred: Any) -> dict[str, float]:
    """Compute the frozen baseline regression metric set."""
    absolute_errors = [
        abs(actual - predicted)
        for actual, predicted in zip(y_true, y_pred, strict=True)
    ]
    squared_errors = [
        (actual - predicted) ** 2
        for actual, predicted in zip(y_true, y_pred, strict=True)
    ]
    mae = sum(absolute_errors) / len(absolute_errors)
    rmse = math.sqrt(sum(squared_errors) / len(squared_errors))
    mape_terms = [
        abs((actual - predicted) / actual)
        for actual, predicted in zip(y_true, y_pred, strict=True)
        if actual != 0
    ]
    mape = sum(mape_terms) / len(mape_terms) if mape_terms else 0.0
    q_errors = [
        q_error(actual=float(actual), predicted=float(predicted))
        for actual, predicted in zip(y_true, y_pred, strict=True)
    ]
    actual_mean = sum(float(value) for value in y_true) / len(y_true)
    total_sum_squares = sum((float(value) - actual_mean) ** 2 for value in y_true)
    residual_sum_squares = sum(squared_errors)
    r2 = (
        1.0 - (residual_sum_squares / total_sum_squares)
        if total_sum_squares > 0
        else 0.0
    )
    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "mape": float(mape),
        "q_error_p50": percentile(q_errors, 0.50),
        "q_error_p90": percentile(q_errors, 0.90),
        "q_error_p95": percentile(q_errors, 0.95),
        "q_error_p99": percentile(q_errors, 0.99),
        "r2": float(r2),
    }


def compute_supplemental_metrics(
    *, y_true: Any, y_pred: Any, target_name: str
) -> dict[str, float | None]:
    """Compute phase-doc metrics excluded from the frozen JSON schema."""
    smape_terms = [
        (
            abs(float(actual) - float(predicted))
            / max((abs(float(actual)) + abs(float(predicted))) / 2.0, 1e-9)
        )
        for actual, predicted in zip(y_true, y_pred, strict=True)
    ]
    supplemental: dict[str, float | None] = {
        "smape": float(sum(smape_terms) / len(smape_terms)) if smape_terms else 0.0,
        "rank_correlation": None,
    }
    if target_name == "execution_time_ms":
        supplemental["rank_correlation"] = rank_correlation(
            y_true=y_true, y_pred=y_pred
        )
    return supplemental


def q_error(*, actual: float, predicted: float) -> float:
    """Compute q-error with a small floor to keep the metric finite."""
    floor = 1e-9
    actual_value = max(abs(actual), floor)
    predicted_value = max(abs(predicted), floor)
    return max(actual_value / predicted_value, predicted_value / actual_value)


def percentile(values: list[float], quantile: float) -> float:
    """Compute a deterministic nearest-rank percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(len(ordered) * quantile) - 1)
    return float(ordered[min(rank, len(ordered) - 1)])


def build_prediction_rows(
    *,
    test_df: pl.DataFrame,
    target_name: str,
    model_family: str,
    actual_values: Any,
    predicted_values: Any,
) -> list[dict[str, Any]]:
    """Build stable prediction rows for the held-out test partition."""
    metadata = test_df.select(
        "observation_id",
        "query_instance_id",
        "template_id",
        "parameter_set_id",
        "scale_factor",
    ).iter_rows(named=True)
    rows: list[dict[str, Any]] = []
    for meta, actual, predicted in zip(
        metadata, actual_values, predicted_values, strict=True
    ):
        rows.append(
            {
                **meta,
                "dataset_partition": "test",
                "target_name": target_name,
                "model_family": model_family,
                "actual_value": float(actual),
                "predicted_value": float(predicted),
            }
        )
    return rows


def build_predictions_dataframe(predictions_rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Materialize held-out predictions in a stable row ordering."""
    predictions_df = pl.DataFrame(predictions_rows).sort(
        [
            "target_name",
            "model_family",
            "observation_id",
        ]
    )
    if "is_selected_baseline" in predictions_df.columns:
        predictions_df = predictions_df.with_columns(
            pl.col("is_selected_baseline").cast(pl.Boolean)
        )
    return predictions_df


def serialize_split_manifest(
    *,
    split: SplitAssignments,
    split_mode: str,
    training_seed: int,
    train_df: pl.DataFrame,
    validation_df: pl.DataFrame,
    test_df: pl.DataFrame,
) -> dict[str, Any]:
    """Serialize split metadata needed for leakage auditing."""
    return {
        "split_mode": split_mode,
        "group_key": "query_instance_id",
        "seed": training_seed,
        "fractions": {
            "test_query_instances": BASELINE_TEST_FRACTION,
            "validation_query_instances_within_train_pool": (
                BASELINE_VALIDATION_FRACTION
            ),
        },
        "train_query_instance_ids": list(split.train_query_instance_ids),
        "validation_query_instance_ids": list(split.validation_query_instance_ids),
        "test_query_instance_ids": list(split.test_query_instance_ids),
        "counts": {
            "train_rows": train_df.height,
            "validation_rows": validation_df.height,
            "test_rows": test_df.height,
            "train_query_instances": len(split.train_query_instance_ids),
            "validation_query_instances": len(split.validation_query_instance_ids),
            "test_query_instances": len(split.test_query_instance_ids),
        },
    }


def save_final_estimators(
    *, target_name: str, estimators: dict[str, Any]
) -> dict[str, str]:
    """Persist fitted estimators in stable artifact locations."""
    estimator_dir = MODELS_DIR / "baseline_estimators" / target_name
    estimator_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths: dict[str, str] = {}
    for model_family, estimator in estimators.items():
        artifact_path = estimator_dir / f"{model_family}.pkl"
        artifact_path.write_bytes(pickle.dumps(estimator))
        artifact_paths[model_family] = str(artifact_path.relative_to(ROOT_DIR))
    return artifact_paths


def rank_correlation(*, y_true: Any, y_pred: Any) -> float:
    """Compute Spearman-style rank correlation with average ranks for ties."""
    actual_ranks = average_ranks([float(value) for value in y_true])
    predicted_ranks = average_ranks([float(value) for value in y_pred])
    return pearson_correlation(actual_ranks, predicted_ranks)


def average_ranks(values: list[float]) -> list[float]:
    """Assign average ranks so tied values remain deterministic."""
    enumerated = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(enumerated):
        end = start + 1
        while end < len(enumerated) and enumerated[end][1] == enumerated[start][1]:
            end += 1
        average_rank = ((start + 1) + end) / 2.0
        for index in range(start, end):
            ranks[enumerated[index][0]] = average_rank
        start = end
    return ranks


def pearson_correlation(left: list[float], right: list[float]) -> float:
    """Compute Pearson correlation for equal-length numeric vectors."""
    if len(left) != len(right) or not left:
        return 0.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_denominator = math.sqrt(
        sum((left_value - left_mean) ** 2 for left_value in left)
    )
    right_denominator = math.sqrt(
        sum((right_value - right_mean) ** 2 for right_value in right)
    )
    denominator = left_denominator * right_denominator
    if denominator == 0.0:
        return 0.0
    return float(numerator / denominator)


def validate_metrics_artifact(
    *, artifact: dict[str, Any], schema_path: str | Path
) -> None:
    """Validate a metrics artifact against the provided JSON schema."""
    schema = load_schema(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(artifact)
