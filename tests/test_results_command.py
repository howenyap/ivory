"""Tests for the results-reporting command output."""

from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import polars as pl

import ivory.cli as cli


class ResultsCommandTests(unittest.TestCase):
    def test_results_baseline_prints_relative_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            metrics_path = root_dir / "baseline_metrics.json"
            manifest_path = root_dir / "training_manifest.json"
            predictions_path = root_dir / "baseline_predictions.parquet"

            metrics_path.write_text(
                json.dumps(
                    {
                        "artifact_path": "artifacts/models/baseline_metrics.json",
                        "split_mode": "random_query_instance_split",
                        "targets": {
                            "execution_time_ms": {
                                "mae": 20.0,
                                "rmse": 30.0,
                                "mape": 0.10,
                                "q_error_p50": 1.05,
                                "q_error_p90": 1.20,
                                "q_error_p95": 1.30,
                                "q_error_p99": 1.50,
                                "r2": 0.95,
                            }
                        },
                    }
                )
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "seed": 20260322,
                        "split": {
                            "counts": {
                                "train_rows": 10,
                                "validation_rows": 2,
                                "test_rows": 3,
                            }
                        },
                        "selected_model_family_per_target": {
                            "execution_time_ms": "random_forest"
                        },
                        "model_results": {
                            "execution_time_ms": {
                                "random_forest": {
                                    "supplemental_test_metrics": {
                                        "smape": 0.12,
                                        "rank_correlation": 0.91,
                                    }
                                }
                            }
                        },
                    }
                )
            )
            pl.DataFrame(
                [
                    {
                        "observation_id": "obs-1",
                        "query_instance_id": "q-1",
                        "template_id": "t-1",
                        "parameter_set_id": "p-1",
                        "scale_factor": 1.0,
                        "dataset_partition": "test",
                        "target_name": "execution_time_ms",
                        "model_family": "random_forest",
                        "actual_value": 100.0,
                        "predicted_value": 90.0,
                        "is_selected_baseline": True,
                    },
                    {
                        "observation_id": "obs-2",
                        "query_instance_id": "q-2",
                        "template_id": "t-2",
                        "parameter_set_id": "p-2",
                        "scale_factor": 1.0,
                        "dataset_partition": "test",
                        "target_name": "execution_time_ms",
                        "model_family": "random_forest",
                        "actual_value": 200.0,
                        "predicted_value": 180.0,
                        "is_selected_baseline": True,
                    },
                    {
                        "observation_id": "obs-3",
                        "query_instance_id": "q-3",
                        "template_id": "t-3",
                        "parameter_set_id": "p-3",
                        "scale_factor": 1.0,
                        "dataset_partition": "test",
                        "target_name": "execution_time_ms",
                        "model_family": "random_forest",
                        "actual_value": 300.0,
                        "predicted_value": 330.0,
                        "is_selected_baseline": True,
                    },
                ]
            ).write_parquet(predictions_path)

            stdout = StringIO()
            with patch("sys.stdout", stdout):
                result = cli.main(
                    [
                        "results",
                        "baseline",
                        "--metrics-artifact",
                        str(metrics_path),
                        "--manifest-artifact",
                        str(manifest_path),
                        "--predictions-artifact",
                        str(predictions_path),
                    ]
                )

            self.assertEqual(result, 0)
            output = stdout.getvalue()
            self.assertIn("Baseline Results", output)
            self.assertIn("Model: random_forest", output)
            self.assertIn("Relative: MAPE 10.00%", output)
            self.assertIn("RMSE/median actual 15.00%", output)
            self.assertIn("Rank corr 0.9100", output)

    def test_results_baseline_degrades_gracefully_for_older_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            metrics_path = root_dir / "baseline_metrics.json"
            manifest_path = root_dir / "training_manifest.json"
            predictions_path = root_dir / "baseline_predictions.parquet"

            metrics_path.write_text(
                json.dumps(
                    {
                        "artifact_path": "artifacts/models/baseline_metrics.json",
                        "split_mode": "random_query_instance_split",
                        "targets": {
                            "planner_total_cost": {
                                "mae": 1000.0,
                                "rmse": 4000.0,
                                "mape": 0.01,
                                "q_error_p50": 1.00,
                                "q_error_p90": 1.02,
                                "q_error_p95": 1.05,
                                "q_error_p99": 1.10,
                                "r2": 0.99,
                            }
                        },
                    }
                )
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "seed": 20260322,
                        "selected_model_family_per_target": {
                            "planner_total_cost": "random_forest"
                        },
                    }
                )
            )
            pl.DataFrame(
                [
                    {
                        "observation_id": "obs-1",
                        "query_instance_id": "q-1",
                        "template_id": "t-1",
                        "parameter_set_id": "p-1",
                        "scale_factor": 1.0,
                        "dataset_partition": "test",
                        "target_name": "planner_total_cost",
                        "model_family": "random_forest",
                        "actual_value": 100000.0,
                        "predicted_value": 99000.0,
                    },
                    {
                        "observation_id": "obs-2",
                        "query_instance_id": "q-2",
                        "template_id": "t-2",
                        "parameter_set_id": "p-2",
                        "scale_factor": 1.0,
                        "dataset_partition": "test",
                        "target_name": "planner_total_cost",
                        "model_family": "random_forest",
                        "actual_value": 120000.0,
                        "predicted_value": 121000.0,
                    },
                ]
            ).write_parquet(predictions_path)

            stdout = StringIO()
            with patch("sys.stdout", stdout):
                result = cli.main(
                    [
                        "results",
                        "baseline",
                        "--metrics-artifact",
                        str(metrics_path),
                        "--manifest-artifact",
                        str(manifest_path),
                        "--predictions-artifact",
                        str(predictions_path),
                    ]
                )

            self.assertEqual(result, 0)
            output = stdout.getvalue()
            self.assertIn("planner_total_cost", output)
            self.assertIn("Model: random_forest", output)
            self.assertIn("MAPE 1.00%", output)


if __name__ == "__main__":
    unittest.main()
