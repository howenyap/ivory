"""Tests for phase 2b plan feature extraction."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

from ivory import plan_features


def _raw_runs_row(
    *,
    observation_id: str,
    query_instance_id: str,
    template_id: str,
    parameter_set_id: str,
    scale_factor: float,
    status: str = "success",
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "run_attempt_id": observation_id,
        "run_id": f"{observation_id}-run",
        "run_number": 1,
        "query_instance_id": query_instance_id,
        "template_id": template_id,
        "parameter_set_id": parameter_set_id,
        "scale_factor": scale_factor,
        "attempt_index": 0,
        "attempt_number": 1,
        "is_retry": False,
        "status": status,
        "run_status": "succeeded" if status == "success" else status,
        "failure_reason": None,
        "include_in_modeling": status == "success",
        "is_excluded": False,
        "exclusion_stage": None,
        "exclusion_reason": None,
        "planner_total_cost": 9.0,
        "planning_time_ms": 2.0,
        "execution_time_ms": 3.0,
        "wall_clock_runtime_ms": 4.0,
        "row_count": 5,
        "sql_text": "select 1",
        "error_class": None,
        "error_message": None,
    }


def _write_raw_runs(
    tmpdir: str, scale_factor: str, rows: list[dict[str, object]]
) -> None:
    scale_dir = (
        Path(tmpdir) / "artifacts" / "raw" / f"sf_{scale_factor.replace('.', '_')}"
    )
    scale_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(scale_dir / "raw_runs.parquet")


def _write_plans(
    tmpdir: str, scale_factor: str, rows: list[dict[str, object] | str]
) -> None:
    scale_dir = (
        Path(tmpdir) / "artifacts" / "raw" / f"sf_{scale_factor.replace('.', '_')}"
    )
    scale_dir.mkdir(parents=True, exist_ok=True)
    contents: list[str] = []
    for row in rows:
        if isinstance(row, str):
            contents.append(row)
        else:
            contents.append(json.dumps(row))
    (scale_dir / "plans.jsonl").write_text("\n".join(contents) + "\n")


class PlanFeatureExtractionTests(unittest.TestCase):
    def test_extract_plan_features_counts_nodes_and_summaries(self) -> None:
        record = {
            "observation_id": "obs-1",
            "plan": {
                "Plan": {
                    "Node Type": "Aggregate",
                    "Plan Rows": 8,
                    "Plan Width": 16,
                    "Startup Cost": 10.0,
                    "Total Cost": 40.0,
                    "Plans": [
                        {
                            "Node Type": "Hash Join",
                            "Plan Rows": 20,
                            "Plan Width": 32,
                            "Startup Cost": 4.0,
                            "Total Cost": 30.0,
                            "Plans": [
                                {
                                    "Node Type": "Seq Scan",
                                    "Plan Rows": 100,
                                    "Plan Width": 12,
                                    "Startup Cost": 0.0,
                                    "Total Cost": 8.0,
                                },
                                {
                                    "Node Type": "Sort",
                                    "Plan Rows": 15,
                                    "Plan Width": 24,
                                    "Startup Cost": 1.0,
                                    "Total Cost": 6.0,
                                    "Plans": [
                                        {
                                            "Node Type": "Index Scan",
                                            "Plan Rows": 5,
                                            "Plan Width": 8,
                                            "Startup Cost": 0.5,
                                            "Total Cost": 2.0,
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            },
        }

        features = plan_features.extract_plan_features(record)

        self.assertEqual(features["plan_node_count"], 5)
        self.assertEqual(features["join_node_count"], 1)
        self.assertEqual(features["scan_node_count"], 2)
        self.assertEqual(features["aggregate_node_count"], 1)
        self.assertEqual(features["sort_node_count"], 1)
        self.assertEqual(features["plan_depth_max"], 4)
        self.assertEqual(features["planner_estimated_rows"], 8.0)
        self.assertEqual(features["planner_estimated_rows_sum"], 148.0)
        self.assertEqual(features["planner_estimated_rows_max"], 100.0)
        self.assertEqual(features["planner_total_cost"], 40.0)
        self.assertEqual(features["planner_total_cost_sum"], 86.0)
        self.assertEqual(features["planner_total_cost_max"], 40.0)
        self.assertEqual(features["node_type_aggregate_count"], 1)
        self.assertEqual(features["node_type_hash_join_count"], 1)
        self.assertEqual(features["node_type_seq_scan_count"], 1)
        self.assertEqual(features["node_type_index_scan_count"], 1)
        self.assertEqual(features["node_type_sort_count"], 1)
        self.assertEqual(features["other_node_count"], 0)

    def test_build_plan_feature_exclusion_row_records_parse_status(self) -> None:
        observation = {
            "observation_id": "obs-1",
            "query_instance_id": "q1-q1-p0000-sf-0.1",
            "template_id": "q1",
            "parameter_set_id": "q1-p0000",
            "scale_factor": 0.1,
        }

        exclusion = plan_features.build_plan_feature_exclusion_row(
            observation,
            plan_features.PlanFeatureError("bad plan"),
        )

        self.assertEqual(exclusion["feature_status"], "excluded")
        self.assertEqual(exclusion["parse_status"], "plan_parse_error")
        self.assertEqual(exclusion["error_class"], "PlanFeatureError")

    def test_featurize_query_plans_writes_features_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            _write_raw_runs(
                tmpdir,
                "0.1",
                [
                    _raw_runs_row(
                        observation_id="obs-1",
                        query_instance_id="q1-q1-p0000-sf-0.1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                    ),
                    _raw_runs_row(
                        observation_id="obs-2",
                        query_instance_id="q1-q1-p0000-sf-0.1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                    ),
                ],
            )
            _write_plans(
                tmpdir,
                "0.1",
                [
                    {
                        "observation_id": "obs-1",
                        "parameter_set_id": "q1-p0000",
                        "plan": {
                            "Plan": {
                                "Node Type": "Seq Scan",
                                "Plan Rows": 11,
                                "Plan Width": 22,
                                "Startup Cost": 0.0,
                                "Total Cost": 9.0,
                            }
                        },
                    },
                    {
                        "observation_id": "obs-2",
                        "parameter_set_id": "q1-p0000",
                        "plan": {"Plan": {"Node Type": "Seq Scan", "Plan Rows": 3}},
                    },
                ],
            )

            schema_dir = root_dir / "schemas"
            schema_dir.mkdir(parents=True, exist_ok=True)
            schema_dir.joinpath("plan_features.schema.json").write_text(
                Path("schemas/plan_features.schema.json").read_text()
            )

            with (
                patch.object(plan_features, "ROOT_DIR", root_dir),
                patch.object(
                    plan_features, "RAW_ARTIFACT_DIR", root_dir / "artifacts" / "raw"
                ),
                patch.object(
                    plan_features,
                    "FEATURE_ARTIFACT_DIR",
                    root_dir / "artifacts" / "features",
                ),
                patch.object(
                    plan_features,
                    "PLAN_FEATURES_PATH",
                    root_dir / "artifacts" / "features" / "plan_features.parquet",
                ),
                patch.object(
                    plan_features,
                    "PLAN_FEATURE_EXCLUSIONS_PATH",
                    root_dir
                    / "artifacts"
                    / "features"
                    / "plan_feature_exclusions.parquet",
                ),
                patch.object(
                    plan_features,
                    "PLAN_FEATURE_SCHEMA_PATH",
                    root_dir / "schemas" / "plan_features.schema.json",
                ),
            ):
                summary = plan_features.featurize_query_plans()

            self.assertEqual(summary["input_observations"], 2)
            self.assertEqual(summary["feature_rows"], 1)
            self.assertEqual(summary["exclusion_rows"], 1)

            features_df = pl.read_parquet(
                root_dir / "artifacts" / "features" / "plan_features.parquet"
            )
            exclusions_df = pl.read_parquet(
                root_dir / "artifacts" / "features" / "plan_feature_exclusions.parquet"
            )
            self.assertEqual(features_df.height, 1)
            self.assertEqual(exclusions_df.height, 1)
            feature_row = features_df.row(0, named=True)
            self.assertEqual(feature_row["observation_id"], "obs-1")
            self.assertFalse(feature_row["broadcast_to_modeling_grain"])
            self.assertEqual(feature_row["plan_node_count"], 1)
            self.assertEqual(feature_row["scan_node_count"], 1)
            self.assertEqual(
                exclusions_df.row(0, named=True)["parse_status"], "plan_parse_error"
            )
            self.assertEqual(
                exclusions_df.row(0, named=True)["observation_id"], "obs-2"
            )

    def test_load_successful_observations_fails_on_duplicate_observation_id(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            _write_raw_runs(
                tmpdir,
                "0.1",
                [
                    _raw_runs_row(
                        observation_id="obs-1",
                        query_instance_id="q1-q1-p0000-sf-0.1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                    ),
                    _raw_runs_row(
                        observation_id="obs-1",
                        query_instance_id="q2-q2-p0000-sf-0.1",
                        template_id="q2",
                        parameter_set_id="q2-p0000",
                        scale_factor=0.1,
                    ),
                ],
            )

            with patch.object(
                plan_features, "RAW_ARTIFACT_DIR", root_dir / "artifacts" / "raw"
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Conflicting successful raw observation rows",
                ):
                    plan_features.load_successful_observations()

    def test_featurize_query_plans_fails_when_plan_rows_do_not_cover_successes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            _write_raw_runs(
                tmpdir,
                "0.1",
                [
                    _raw_runs_row(
                        observation_id="obs-1",
                        query_instance_id="q1-q1-p0000-sf-0.1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                    ),
                    _raw_runs_row(
                        observation_id="obs-2",
                        query_instance_id="q2-q2-p0000-sf-0.1",
                        template_id="q2",
                        parameter_set_id="q2-p0000",
                        scale_factor=0.1,
                    ),
                ],
            )
            _write_plans(
                tmpdir,
                "0.1",
                [
                    {
                        "observation_id": "obs-1",
                        "parameter_set_id": "q1-p0000",
                        "plan": {
                            "Plan": {
                                "Node Type": "Seq Scan",
                                "Plan Rows": 11,
                                "Plan Width": 22,
                                "Startup Cost": 0.0,
                                "Total Cost": 9.0,
                            }
                        },
                    }
                ],
            )

            schema_dir = root_dir / "schemas"
            schema_dir.mkdir(parents=True, exist_ok=True)
            schema_dir.joinpath("plan_features.schema.json").write_text(
                Path("schemas/plan_features.schema.json").read_text()
            )

            with (
                patch.object(plan_features, "ROOT_DIR", root_dir),
                patch.object(
                    plan_features, "RAW_ARTIFACT_DIR", root_dir / "artifacts" / "raw"
                ),
                patch.object(
                    plan_features,
                    "FEATURE_ARTIFACT_DIR",
                    root_dir / "artifacts" / "features",
                ),
                patch.object(
                    plan_features,
                    "PLAN_FEATURES_PATH",
                    root_dir / "artifacts" / "features" / "plan_features.parquet",
                ),
                patch.object(
                    plan_features,
                    "PLAN_FEATURE_EXCLUSIONS_PATH",
                    root_dir
                    / "artifacts"
                    / "features"
                    / "plan_feature_exclusions.parquet",
                ),
                patch.object(
                    plan_features,
                    "PLAN_FEATURE_SCHEMA_PATH",
                    root_dir / "schemas" / "plan_features.schema.json",
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Plan artifact coverage mismatch before validation",
                ):
                    plan_features.featurize_query_plans()


if __name__ == "__main__":
    unittest.main()
