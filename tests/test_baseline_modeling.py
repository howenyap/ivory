"""Tests for phase 3a baseline modeling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

from ivory import baseline_modeling


def _feature_row(
    *,
    observation_id: str,
    query_instance_id: str,
    template_id: str,
    parameter_set_id: str,
    scale_factor: float,
    planner_total_cost: float,
    planning_time_ms: float,
    execution_time_ms: float,
    join_count: int,
    plan_node_count: int,
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "run_attempt_id": observation_id,
        "query_instance_id": query_instance_id,
        "template_id": template_id,
        "parameter_set_id": parameter_set_id,
        "scale_factor": scale_factor,
        "sql_features_broadcast": True,
        "plan_features_broadcast": False,
        "null_indicator_columns": [],
        "targets": {
            "planner_total_cost": planner_total_cost,
            "planning_time_ms": planning_time_ms,
            "execution_time_ms": execution_time_ms,
        },
        "sql_features": {
            "aggregation_present": join_count > 0,
            "selected_column_count": 4 + join_count,
            "table_count": 1 + join_count,
            "join_count": join_count,
            "predicate_count": 1 + join_count,
            "group_by_count": 0,
            "order_by_count": 0,
            "limit_count": 0,
            "subquery_count": 0,
        },
        "plan_features": {
            "plan_node_count": plan_node_count,
            "join_node_count": join_count,
            "scan_node_count": 1,
            "aggregate_node_count": 0,
            "sort_node_count": 0,
            "planner_estimated_rows": 100.0 + (join_count * 10),
            "planner_total_cost": planner_total_cost,
        },
    }


class BaselineModelingTests(unittest.TestCase):
    def test_train_baseline_models_emits_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            feature_dir = root_dir / "artifacts" / "features"
            models_dir = root_dir / "artifacts" / "models"
            schema_dir = root_dir / "schemas"
            feature_dir.mkdir(parents=True)
            models_dir.mkdir(parents=True)
            schema_dir.mkdir(parents=True)

            rows = []
            for index, scale_factor in enumerate(
                [0.1, 0.1, 1.0, 1.0, 3.0, 3.0], start=1
            ):
                query_instance_id = f"q-{index}"
                template_id = f"t-{index % 3}"
                parameter_set_id = f"p-{index}"
                join_count = index % 2
                planner_total_cost = 100.0 + (scale_factor * 50.0) + index
                planning_time_ms = 5.0 + index
                execution_time_ms = 20.0 + (scale_factor * 25.0) + (join_count * 3.0)
                rows.append(
                    _feature_row(
                        observation_id=f"{query_instance_id}-obs-1",
                        query_instance_id=query_instance_id,
                        template_id=template_id,
                        parameter_set_id=parameter_set_id,
                        scale_factor=scale_factor,
                        planner_total_cost=planner_total_cost,
                        planning_time_ms=planning_time_ms,
                        execution_time_ms=execution_time_ms,
                        join_count=join_count,
                        plan_node_count=3 + join_count,
                    )
                )
                rows.append(
                    _feature_row(
                        observation_id=f"{query_instance_id}-obs-2",
                        query_instance_id=query_instance_id,
                        template_id=template_id,
                        parameter_set_id=parameter_set_id,
                        scale_factor=scale_factor,
                        planner_total_cost=planner_total_cost + 1.0,
                        planning_time_ms=planning_time_ms + 0.5,
                        execution_time_ms=execution_time_ms + 1.0,
                        join_count=join_count,
                        plan_node_count=4 + join_count,
                    )
                )

            pl.DataFrame(rows).write_parquet(feature_dir / "features.parquet")
            schema_dir.joinpath("baseline_metrics.schema.json").write_text(
                Path("schemas/baseline_metrics.schema.json").read_text()
            )
            schema_dir.joinpath("features.schema.json").write_text(
                Path("schemas/features.schema.json").read_text()
            )
            config = {
                "experiment": {
                    "seed": 20260322,
                    "split_modes": {
                        "baseline": "random_query_instance_split",
                    },
                }
            }

            with (
                patch.object(baseline_modeling, "ROOT_DIR", root_dir),
                patch.object(baseline_modeling, "load_config", return_value=config),
                patch.object(
                    baseline_modeling, "FEATURES_PATH", feature_dir / "features.parquet"
                ),
                patch.object(baseline_modeling, "MODELS_DIR", models_dir),
                patch.object(
                    baseline_modeling,
                    "BASELINE_METRICS_PATH",
                    models_dir / "baseline_metrics.json",
                ),
                patch.object(
                    baseline_modeling,
                    "BASELINE_PREDICTIONS_PATH",
                    models_dir / "baseline_predictions.parquet",
                ),
                patch.object(
                    baseline_modeling,
                    "TRAINING_MANIFEST_PATH",
                    models_dir / "training_manifest.json",
                ),
                patch.object(
                    baseline_modeling,
                    "BASELINE_SCHEMA_PATH",
                    schema_dir / "baseline_metrics.schema.json",
                ),
                patch.object(
                    baseline_modeling,
                    "FEATURES_SCHEMA_PATH",
                    schema_dir / "features.schema.json",
                ),
            ):
                summary = baseline_modeling.train_baseline_models(seed=1234)

            self.assertEqual(summary["rows"], 12)
            metrics = json.loads((models_dir / "baseline_metrics.json").read_text())
            self.assertEqual(
                metrics["artifact_path"], "artifacts/models/baseline_metrics.json"
            )
            self.assertEqual(metrics["split_mode"], "random_query_instance_split")
            self.assertEqual(
                set(metrics["targets"]), set(baseline_modeling.TARGET_NAMES)
            )

            predictions = pl.read_parquet(models_dir / "baseline_predictions.parquet")
            self.assertIn("is_selected_baseline", predictions.columns)
            self.assertTrue(predictions.height > 0)
            self.assertEqual(
                set(predictions["model_family"].unique().to_list()),
                set(baseline_modeling.model_family_names()),
            )

            manifest = json.loads((models_dir / "training_manifest.json").read_text())
            self.assertIn("selected_features", manifest)
            self.assertIn("excluded_columns", manifest)
            self.assertIn("final_model_input_columns_per_model", manifest)
            self.assertIn("split", manifest)
            self.assertIn("seed", manifest)
            self.assertIn("model_artifact_paths", manifest)
            self.assertIn(
                "plan_features__planner_total_cost",
                manifest["target_specific_excluded_columns"]["planner_total_cost"],
            )
            for target_paths in manifest["model_artifact_paths"].values():
                for relative_path in target_paths.values():
                    self.assertTrue((root_dir / relative_path).exists())

    def test_train_baseline_models_can_filter_scale_factor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            feature_dir = root_dir / "artifacts" / "features"
            models_dir = root_dir / "artifacts" / "models"
            schema_dir = root_dir / "schemas"
            feature_dir.mkdir(parents=True)
            models_dir.mkdir(parents=True)
            schema_dir.mkdir(parents=True)

            pl.DataFrame(
                [
                    _feature_row(
                        observation_id=f"q-{index}-obs",
                        query_instance_id=f"q-{index}",
                        template_id=f"t-{index}",
                        parameter_set_id=f"p-{index}",
                        scale_factor=scale_factor,
                        planner_total_cost=50.0 + index,
                        planning_time_ms=5.0 + index,
                        execution_time_ms=15.0 + index,
                        join_count=index % 2,
                        plan_node_count=3 + index,
                    )
                    for index, scale_factor in enumerate(
                        [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 1.0, 1.0, 1.0], start=1
                    )
                ]
            ).write_parquet(feature_dir / "features.parquet")
            schema_dir.joinpath("baseline_metrics.schema.json").write_text(
                Path("schemas/baseline_metrics.schema.json").read_text()
            )
            schema_dir.joinpath("features.schema.json").write_text(
                Path("schemas/features.schema.json").read_text()
            )
            config = {
                "experiment": {
                    "seed": 20260322,
                    "split_modes": {
                        "baseline": "random_query_instance_split",
                    },
                }
            }

            with (
                patch.object(baseline_modeling, "ROOT_DIR", root_dir),
                patch.object(baseline_modeling, "load_config", return_value=config),
                patch.object(
                    baseline_modeling, "FEATURES_PATH", feature_dir / "features.parquet"
                ),
                patch.object(baseline_modeling, "MODELS_DIR", models_dir),
                patch.object(
                    baseline_modeling,
                    "BASELINE_METRICS_PATH",
                    models_dir / "baseline_metrics.json",
                ),
                patch.object(
                    baseline_modeling,
                    "BASELINE_PREDICTIONS_PATH",
                    models_dir / "baseline_predictions.parquet",
                ),
                patch.object(
                    baseline_modeling,
                    "TRAINING_MANIFEST_PATH",
                    models_dir / "training_manifest.json",
                ),
                patch.object(
                    baseline_modeling,
                    "BASELINE_SCHEMA_PATH",
                    schema_dir / "baseline_metrics.schema.json",
                ),
                patch.object(
                    baseline_modeling,
                    "FEATURES_SCHEMA_PATH",
                    schema_dir / "features.schema.json",
                ),
            ):
                summary = baseline_modeling.train_baseline_models(
                    seed=1234,
                    scale_factor=0.1,
                )

            self.assertEqual(summary["rows"], 6)
            manifest = json.loads((models_dir / "training_manifest.json").read_text())
            self.assertEqual(
                manifest["preprocessing_choices"]["scale_factor_filter"],
                0.1,
            )


if __name__ == "__main__":
    unittest.main()
