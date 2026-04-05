"""Phase 3b evaluation pipeline: grouped split, ablations, and error analysis."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import polars as pl

from ivory.baseline_modeling import (
    FEATURES_PATH,
    TARGET_NAMES,
    TRAINING_MANIFEST_PATH,
    build_model_family_estimators,
    compute_regression_metrics,
    determine_constant_feature_columns,
    determine_target_exclusions,
    flatten_modeling_dataset,
    inverse_transform_target,
    load_modeling_dataset,
    q_error,
    to_feature_matrix,
    to_target_vector,
    transform_target,
    validate_metrics_artifact,
)
from ivory.collection import log_progress
from ivory.config import load_config, load_schema

ROOT_DIR = Path(__file__).resolve().parents[2]
EVALUATION_DIR = ROOT_DIR / "artifacts" / "evaluation"
GROUPED_METRICS_PATH = EVALUATION_DIR / "grouped_metrics.json"
GROUPED_SPLIT_MANIFEST_PATH = EVALUATION_DIR / "grouped_split_manifest.json"
ABLATIONS_PATH = EVALUATION_DIR / "ablations.json"
ERROR_ANALYSIS_PATH = EVALUATION_DIR / "error_analysis.parquet"
GROUPED_METRICS_SCHEMA_PATH = ROOT_DIR / "schemas" / "grouped_metrics.schema.json"

GROUPED_CV_FOLDS = 5


# ---------------------------------------------------------------------------
# Grouped evaluation
# ---------------------------------------------------------------------------


def run_grouped_evaluation(*, seed: int | None = None) -> dict[str, Any]:
    """5-fold template cross-validation: each fold holds out ~4-5 templates."""
    config = load_config()
    training_seed = int(
        config["experiment"]["seed"] if seed is None else seed
    )

    features_df = load_modeling_dataset(scale_factor=None)
    modeling_df, selected_features = flatten_modeling_dataset(features_df)

    all_templates = sorted(modeling_df["template_id"].unique().to_list())
    folds = _build_kfold_template_splits(all_templates, training_seed, k=GROUPED_CV_FOLDS)
    split_hash = _compute_split_hash_kfold(folds)

    training_manifest = _load_training_manifest()
    selected_families = training_manifest.get("selected_model_family_per_target", {})

    # Accumulate per-fold metrics and error rows
    fold_metrics: dict[str, list[dict[str, Any]]] = {t: [] for t in TARGET_NAMES}
    all_error_rows: list[dict[str, Any]] = []

    for fold_idx, (train_templates, test_templates) in enumerate(folds):
        train_df = modeling_df.filter(pl.col("template_id").is_in(set(train_templates)))
        test_df = modeling_df.filter(pl.col("template_id").is_in(set(test_templates)))

        for target_name in TARGET_NAMES:
            target_exclusions = determine_target_exclusions(target_name)
            constant_cols = determine_constant_feature_columns(train_df, selected_features)
            excluded = set(
                list(TARGET_NAMES)
                + ["dataset_partition"]
                + list(_identifier_columns())
                + constant_cols
            )
            feature_columns = [
                col for col in selected_features
                if col not in excluded and col not in target_exclusions
            ]

            model_family = selected_families.get(target_name, "hist_gradient_boosting")
            estimator = build_model_family_estimators(training_seed)[model_family]

            x_train = to_feature_matrix(train_df, feature_columns)
            y_train = transform_target(to_target_vector(train_df, target_name), target_name)
            x_test = to_feature_matrix(test_df, feature_columns)
            y_test_raw = to_target_vector(test_df, target_name)

            estimator.fit(x_train, y_train)
            y_pred = inverse_transform_target(estimator.predict(x_test), target_name)

            metrics = compute_regression_metrics(y_true=y_test_raw, y_pred=y_pred)
            fold_metrics[target_name].append(metrics)

            if fold_idx == 0:
                all_error_rows.extend(
                    _build_error_rows(
                        test_df=test_df,
                        target_name=target_name,
                        model_family=model_family,
                        y_true=y_test_raw,
                        y_pred=y_pred,
                    )
                )

        log_progress(
            f"grouped cv fold {fold_idx + 1}/{GROUPED_CV_FOLDS} complete | "
            f"train_templates={len(train_templates)} test_templates={len(test_templates)}",
            level="info",
        )

    # Average metrics across folds
    per_target_metrics: dict[str, dict[str, Any]] = {}
    metric_keys = ["mae", "rmse", "mape", "q_error_p50", "q_error_p90", "q_error_p95", "q_error_p99"]
    for target_name in TARGET_NAMES:
        avg: dict[str, Any] = {}
        for k in metric_keys:
            avg[k] = float(sum(fm[k] for fm in fold_metrics[target_name]) / len(folds))
        avg["group_support"] = len(all_templates)
        per_target_metrics[target_name] = avg

    # Use fold 0 for train_groups/test_groups (schema requires disjoint arrays)
    fold0_train, fold0_test = folds[0]

    grouped_metrics_artifact = {
        "artifact_path": "artifacts/evaluation/grouped_metrics.json",
        "grouped_split": {
            "split_mode": "template_grouped_holdout",
            "group_key": "template_id",
            "train_groups": sorted(fold0_train),
            "test_groups": sorted(fold0_test),
            "split_hash": split_hash,
        },
        "targets": per_target_metrics,
    }
    validate_metrics_artifact(
        artifact=grouped_metrics_artifact,
        schema_path=GROUPED_METRICS_SCHEMA_PATH,
    )

    split_manifest = {
        "cv_method": f"{GROUPED_CV_FOLDS}_fold_template_cv",
        "group_key": "template_id",
        "seed": training_seed,
        "split_hash": split_hash,
        "train_template_ids": sorted(fold0_train),
        "test_template_ids": sorted(fold0_test),
        "folds": [
            {"fold": i, "train_template_ids": sorted(tr), "test_template_ids": sorted(te)}
            for i, (tr, te) in enumerate(folds)
        ],
        "counts": {
            "total_templates": len(all_templates),
            "folds": GROUPED_CV_FOLDS,
            "test_templates_per_fold": len(folds[0][1]),
        },
    }

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    GROUPED_METRICS_PATH.write_text(
        json.dumps(grouped_metrics_artifact, indent=2, sort_keys=True) + "\n"
    )
    GROUPED_SPLIT_MANIFEST_PATH.write_text(
        json.dumps(split_manifest, indent=2, sort_keys=True) + "\n"
    )

    log_progress(
        f"grouped cv complete | "
        f"folds={GROUPED_CV_FOLDS} "
        f"templates={len(all_templates)} "
        f"avg_q_error_p50_exec={per_target_metrics['execution_time_ms']['q_error_p50']:.3f}",
        level="success",
    )
    return {
        "grouped_metrics_path": str(GROUPED_METRICS_PATH),
        "grouped_split_manifest_path": str(GROUPED_SPLIT_MANIFEST_PATH),
        "folds": GROUPED_CV_FOLDS,
        "templates": len(all_templates),
        "split_hash": split_hash,
    }


def _build_kfold_template_splits(
    all_templates: list[str], seed: int, k: int
) -> list[tuple[list[str], list[str]]]:
    """Build k deterministic folds where each fold holds out ~len/k templates."""
    from ivory.baseline_modeling import deterministic_shuffle

    shuffled = deterministic_shuffle(all_templates, seed)
    fold_size = max(1, len(shuffled) // k)
    folds = []
    for i in range(k):
        start = i * fold_size
        end = start + fold_size if i < k - 1 else len(shuffled)
        test_templates = sorted(shuffled[start:end])
        train_templates = sorted(shuffled[:start] + shuffled[end:])
        folds.append((train_templates, test_templates))
    return folds


def _compute_split_hash_kfold(folds: list[tuple[list[str], list[str]]]) -> str:
    """Derive a stable hash from all fold assignments."""
    payload = "|".join(
        ",".join(sorted(tr)) + ":" + ",".join(sorted(te))
        for tr, te in folds
    )
    return sha256(payload.encode()).hexdigest()



def _build_error_rows(
    *,
    test_df: pl.DataFrame,
    target_name: str,
    model_family: str,
    y_true: Any,
    y_pred: Any,
) -> list[dict[str, Any]]:
    metadata = test_df.select(
        "observation_id", "template_id", "scale_factor"
    ).iter_rows(named=True)
    rows: list[dict[str, Any]] = []
    for meta, actual, predicted in zip(metadata, y_true, y_pred, strict=True):
        actual_f = float(actual)
        predicted_f = float(predicted)
        abs_err = abs(actual_f - predicted_f)
        rel_err = abs_err / max(abs(actual_f), 1e-9)
        qe = q_error(actual=actual_f, predicted=predicted_f)
        rows.append(
            {
                **meta,
                "target_name": target_name,
                "model_family": model_family,
                "actual_value": actual_f,
                "predicted_value": predicted_f,
                "absolute_error": abs_err,
                "relative_error": rel_err,
                "q_error": qe,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Ablations
# ---------------------------------------------------------------------------


def run_ablations(*, seed: int | None = None) -> dict[str, Any]:
    """Run feature-family ablations and scale-factor comparisons."""
    config = load_config()
    training_seed = int(
        config["experiment"]["seed"] if seed is None else seed
    )

    features_df = load_modeling_dataset(scale_factor=None)
    modeling_df, selected_features = flatten_modeling_dataset(features_df)

    split = _build_random_instance_split(modeling_df, training_seed)
    train_df = modeling_df.filter(
        pl.col("query_instance_id").is_in(set(split["train_ids"]))
    )
    test_df = modeling_df.filter(
        pl.col("query_instance_id").is_in(set(split["test_ids"]))
    )

    sql_only_features = [f for f in selected_features if f.startswith("sql_features__") or f.startswith("null__sql_features__")]
    plan_only_features = [f for f in selected_features if f.startswith("plan_features__") or f.startswith("null__plan_features__")]
    combined_features = selected_features

    ablation_results: dict[str, Any] = {}

    for ablation_name, feature_set in [
        ("sql_only", sql_only_features),
        ("plan_only", plan_only_features),
        ("combined", combined_features),
    ]:
        ablation_results[ablation_name] = _run_ablation_feature_set(
            train_df=train_df,
            test_df=test_df,
            feature_set=feature_set,
            seed=training_seed,
        )
        log_progress(f"ablation complete: {ablation_name}", level="info")

    ablation_results["single_scale_vs_multi_scale"] = _run_scale_ablation(
        modeling_df=modeling_df,
        selected_features=selected_features,
        seed=training_seed,
    )
    log_progress("ablation complete: single_scale_vs_multi_scale", level="info")

    ablation_results["postgres_cost_proxy"] = _run_postgres_cost_proxy(
        test_df=test_df,
    )
    log_progress("ablation complete: postgres_cost_proxy", level="info")

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    ABLATIONS_PATH.write_text(
        json.dumps(ablation_results, indent=2, sort_keys=True) + "\n"
    )

    log_progress("all ablations complete", level="success")
    return {"ablations_path": str(ABLATIONS_PATH)}


def _run_ablation_feature_set(
    *,
    train_df: pl.DataFrame,
    test_df: pl.DataFrame,
    feature_set: list[str],
    seed: int,
) -> dict[str, dict[str, float]]:
    results: dict[str, dict[str, float]] = {}
    for target_name in TARGET_NAMES:
        target_exclusions = set(determine_target_exclusions(target_name))
        constant_cols = set(determine_constant_feature_columns(train_df, feature_set))
        cols = [
            c for c in feature_set
            if c not in target_exclusions and c not in constant_cols
        ]
        if not cols:
            results[target_name] = {}
            continue
        estimators = build_model_family_estimators(seed)
        estimator = estimators["hist_gradient_boosting"]
        x_train = to_feature_matrix(train_df, cols)
        y_train = transform_target(to_target_vector(train_df, target_name), target_name)
        x_test = to_feature_matrix(test_df, cols)
        y_test_raw = to_target_vector(test_df, target_name)
        estimator.fit(x_train, y_train)
        y_pred = inverse_transform_target(estimator.predict(x_test), target_name)
        results[target_name] = compute_regression_metrics(y_true=y_test_raw, y_pred=y_pred)
    return results


def _run_scale_ablation(
    *,
    modeling_df: pl.DataFrame,
    selected_features: list[str],
    seed: int,
) -> dict[str, dict[str, dict[str, float]]]:
    available_sfs = sorted(modeling_df["scale_factor"].unique().to_list())

    result: dict[str, dict[str, dict[str, float]]] = {}

    # SF 0.1 only
    if 0.1 in available_sfs:
        sf_df = modeling_df.filter(pl.col("scale_factor") == 0.1)
        split = _build_random_instance_split(sf_df, seed)
        train_df = sf_df.filter(pl.col("query_instance_id").is_in(set(split["train_ids"])))
        test_df = sf_df.filter(pl.col("query_instance_id").is_in(set(split["test_ids"])))
        result["sf_0_1_only"] = _run_ablation_feature_set(
            train_df=train_df,
            test_df=test_df,
            feature_set=selected_features,
            seed=seed,
        )

    # Multi-scale: train on all available, test on all available (using same random split)
    multi_split = _build_random_instance_split(modeling_df, seed)
    multi_train_df = modeling_df.filter(
        pl.col("query_instance_id").is_in(set(multi_split["train_ids"]))
    )
    multi_test_df = modeling_df.filter(
        pl.col("query_instance_id").is_in(set(multi_split["test_ids"]))
    )
    scale_label = "_and_".join(
        f"sf_{str(sf).replace('.', '_')}" for sf in available_sfs
    )
    result[scale_label] = _run_ablation_feature_set(
        train_df=multi_train_df,
        test_df=multi_test_df,
        feature_set=selected_features,
        seed=seed,
    )

    return result


def _run_postgres_cost_proxy(*, test_df: pl.DataFrame) -> dict[str, dict[str, float]]:
    """Use planner_total_cost directly as a predictor for execution_time_ms."""
    cost_col = "plan_features__planner_total_cost"
    if cost_col not in test_df.columns:
        return {}

    proxy_df = test_df.filter(pl.col(cost_col).is_not_null())
    if proxy_df.is_empty():
        return {}

    y_true = to_target_vector(proxy_df, "execution_time_ms")
    y_pred = proxy_df[cost_col].to_numpy()
    return {
        "execution_time_ms": compute_regression_metrics(y_true=y_true, y_pred=y_pred)
    }


def _build_random_instance_split(
    modeling_df: pl.DataFrame, seed: int
) -> dict[str, list[str]]:
    """Random 80/20 split by query_instance_id (mirrors Phase 3a logic)."""
    from ivory.baseline_modeling import (
        BASELINE_TEST_FRACTION,
        BASELINE_VALIDATION_FRACTION,
        bounded_partition_size,
        deterministic_shuffle,
    )

    instance_ids = sorted(modeling_df["query_instance_id"].unique().to_list())
    shuffled = deterministic_shuffle(instance_ids, seed)
    test_count = bounded_partition_size(
        total=len(shuffled),
        fraction=BASELINE_TEST_FRACTION,
        minimum=1,
        maximum=len(shuffled) - 2,
    )
    remaining = len(shuffled) - test_count
    val_count = bounded_partition_size(
        total=remaining,
        fraction=BASELINE_VALIDATION_FRACTION,
        minimum=1,
        maximum=remaining - 1,
    )
    test_ids = shuffled[:test_count]
    val_ids = shuffled[test_count: test_count + val_count]
    train_ids = shuffled[test_count + val_count:]
    # For ablations we train on train+validation, test on test
    return {
        "train_ids": train_ids + val_ids,
        "test_ids": test_ids,
    }


# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------


def run_error_analysis(*, seed: int | None = None) -> dict[str, Any]:
    """Generate per-observation error analysis from the grouped test split."""
    if not GROUPED_SPLIT_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Missing grouped split manifest at {GROUPED_SPLIT_MANIFEST_PATH}. "
            "Run `ivory evaluate grouped` first."
        )

    config = load_config()
    training_seed = int(
        config["experiment"]["seed"] if seed is None else seed
    )

    manifest = json.loads(GROUPED_SPLIT_MANIFEST_PATH.read_text())
    test_templates = set(manifest["test_template_ids"])
    train_templates = set(manifest["train_template_ids"])

    features_df = load_modeling_dataset(scale_factor=None)
    modeling_df, selected_features = flatten_modeling_dataset(features_df)

    train_df = modeling_df.filter(pl.col("template_id").is_in(train_templates))
    test_df = modeling_df.filter(pl.col("template_id").is_in(test_templates))

    training_manifest = _load_training_manifest()
    selected_families = training_manifest.get("selected_model_family_per_target", {})

    error_rows: list[dict[str, Any]] = []

    for target_name in TARGET_NAMES:
        target_exclusions = determine_target_exclusions(target_name)
        constant_cols = determine_constant_feature_columns(train_df, selected_features)
        excluded = set(
            list(TARGET_NAMES)
            + ["dataset_partition"]
            + list(_identifier_columns())
            + constant_cols
        )
        feature_columns = [
            col
            for col in selected_features
            if col not in excluded and col not in target_exclusions
        ]

        model_family = selected_families.get(target_name, "hist_gradient_boosting")
        estimator = build_model_family_estimators(training_seed)[model_family]

        x_train = to_feature_matrix(train_df, feature_columns)
        y_train = transform_target(to_target_vector(train_df, target_name), target_name)
        x_test = to_feature_matrix(test_df, feature_columns)
        y_test_raw = to_target_vector(test_df, target_name)

        estimator.fit(x_train, y_train)
        y_pred = inverse_transform_target(estimator.predict(x_test), target_name)

        error_rows.extend(
            _build_error_rows(
                test_df=test_df,
                target_name=target_name,
                model_family=model_family,
                y_true=y_test_raw,
                y_pred=y_pred,
            )
        )

    error_df = (
        pl.DataFrame(error_rows)
        .sort(["target_name", "q_error"], descending=[False, True])
    )

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    error_df.write_parquet(ERROR_ANALYSIS_PATH)

    log_progress(
        f"error analysis complete | rows={error_df.height}",
        level="success",
    )
    return {
        "error_analysis_path": str(ERROR_ANALYSIS_PATH),
        "rows": error_df.height,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identifier_columns() -> tuple[str, ...]:
    from ivory.baseline_modeling import IDENTIFIER_COLUMNS
    return IDENTIFIER_COLUMNS


def _load_training_manifest() -> dict[str, Any]:
    if not TRAINING_MANIFEST_PATH.exists():
        return {}
    return json.loads(TRAINING_MANIFEST_PATH.read_text())
