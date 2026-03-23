"""Tests for phase 2c dataset assembly."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

from ivory import dataset_assembly


def _raw_row(
    *,
    observation_id: str,
    run_attempt_id: str,
    query_instance_id: str,
    template_id: str,
    parameter_set_id: str,
    scale_factor: float,
    planner_total_cost: float,
    planning_time_ms: float,
    execution_time_ms: float,
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "run_attempt_id": run_attempt_id,
        "run_id": f"{query_instance_id}-run",
        "run_number": 1,
        "query_instance_id": query_instance_id,
        "template_id": template_id,
        "parameter_set_id": parameter_set_id,
        "scale_factor": scale_factor,
        "attempt_index": 0,
        "attempt_number": 1,
        "is_retry": False,
        "status": "success",
        "run_status": "succeeded",
        "failure_reason": None,
        "include_in_modeling": True,
        "is_excluded": False,
        "exclusion_stage": None,
        "exclusion_reason": None,
        "planner_total_cost": planner_total_cost,
        "planning_time_ms": planning_time_ms,
        "execution_time_ms": execution_time_ms,
        "wall_clock_runtime_ms": 4.0,
        "row_count": 1,
        "sql_text": "select 1",
        "error_class": None,
        "error_message": None,
    }


class DatasetAssemblyTests(unittest.TestCase):
    def test_assemble_feature_dataset_builds_observation_grain_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            raw_dir = root_dir / "artifacts" / "raw" / "sf_0_1"
            feature_dir = root_dir / "artifacts" / "features"
            schema_dir = root_dir / "schemas"
            raw_dir.mkdir(parents=True)
            feature_dir.mkdir(parents=True)
            schema_dir.mkdir(parents=True)

            pl.DataFrame(
                [
                    _raw_row(
                        observation_id="obs-1",
                        run_attempt_id="obs-1",
                        query_instance_id="q-1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                        planner_total_cost=11.0,
                        planning_time_ms=10.0,
                        execution_time_ms=12.0,
                    ),
                    _raw_row(
                        observation_id="obs-2",
                        run_attempt_id="obs-2",
                        query_instance_id="q-1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                        planner_total_cost=21.0,
                        planning_time_ms=20.0,
                        execution_time_ms=22.0,
                    ),
                ]
            ).write_parquet(raw_dir / "raw_runs.parquet")

            pl.DataFrame(
                [
                    {
                        "query_instance_id": "q-1",
                        "template_id": "q1",
                        "parameter_set_id": "q1-p0000",
                        "scale_factor": 0.1,
                        "broadcast_to_modeling_grain": True,
                        "feature_status": "available",
                        "aggregation_present": False,
                        "selected_column_count": 1,
                        "table_count": 1,
                        "join_count": 0,
                        "predicate_count": 0,
                        "group_by_count": 0,
                        "order_by_count": 0,
                        "limit_count": 0,
                        "subquery_count": 0,
                    }
                ]
            ).write_parquet(feature_dir / "sql_features.parquet")
            pl.DataFrame(
                [],
                schema={
                    "query_instance_id": pl.String,
                    "template_id": pl.String,
                    "parameter_set_id": pl.String,
                    "scale_factor": pl.Float64,
                    "broadcast_to_modeling_grain": pl.Boolean,
                    "feature_status": pl.String,
                    "parse_status": pl.String,
                    "error_class": pl.String,
                    "error_message": pl.String,
                },
            ).write_parquet(feature_dir / "sql_feature_exclusions.parquet")

            pl.DataFrame(
                [
                    {
                        "observation_id": "obs-1",
                        "query_instance_id": "q-1",
                        "template_id": "q1",
                        "parameter_set_id": "q1-p0000",
                        "scale_factor": 0.1,
                        "broadcast_to_modeling_grain": False,
                        "feature_status": "available",
                        "plan_node_count": 3,
                        "join_node_count": 0,
                        "scan_node_count": 1,
                        "aggregate_node_count": 0,
                        "sort_node_count": 0,
                        "plan_depth_max": 2,
                        "planner_estimated_rows": 1.0,
                        "planner_estimated_rows_sum": 3.0,
                        "planner_estimated_rows_max": 2.0,
                        "planner_estimated_width": 4.0,
                        "planner_estimated_width_sum": 12.0,
                        "planner_estimated_width_max": 4.0,
                        "planner_startup_cost": 1.0,
                        "planner_startup_cost_sum": 2.0,
                        "planner_startup_cost_max": 1.0,
                        "planner_total_cost": 11.0,
                        "planner_total_cost_sum": 15.0,
                        "planner_total_cost_max": 11.0,
                        "node_type_aggregate_count": 0,
                        "node_type_bitmap_heap_scan_count": 0,
                        "node_type_bitmap_index_scan_count": 0,
                        "node_type_cte_scan_count": 0,
                        "node_type_gather_count": 0,
                        "node_type_gather_merge_count": 0,
                        "node_type_hash_count": 0,
                        "node_type_hash_join_count": 0,
                        "node_type_index_only_scan_count": 0,
                        "node_type_index_scan_count": 0,
                        "node_type_limit_count": 0,
                        "node_type_nested_loop_count": 0,
                        "node_type_seq_scan_count": 1,
                        "node_type_sort_count": 0,
                        "other_node_count": 0,
                    },
                    {
                        "observation_id": "obs-2",
                        "query_instance_id": "q-1",
                        "template_id": "q1",
                        "parameter_set_id": "q1-p0000",
                        "scale_factor": 0.1,
                        "broadcast_to_modeling_grain": False,
                        "feature_status": "available",
                        "plan_node_count": 4,
                        "join_node_count": 1,
                        "scan_node_count": 1,
                        "aggregate_node_count": 0,
                        "sort_node_count": 1,
                        "plan_depth_max": 2,
                        "planner_estimated_rows": 2.0,
                        "planner_estimated_rows_sum": 4.0,
                        "planner_estimated_rows_max": 2.0,
                        "planner_estimated_width": 5.0,
                        "planner_estimated_width_sum": 15.0,
                        "planner_estimated_width_max": 5.0,
                        "planner_startup_cost": 2.0,
                        "planner_startup_cost_sum": 4.0,
                        "planner_startup_cost_max": 2.0,
                        "planner_total_cost": 21.0,
                        "planner_total_cost_sum": 25.0,
                        "planner_total_cost_max": 21.0,
                        "node_type_aggregate_count": 0,
                        "node_type_bitmap_heap_scan_count": 0,
                        "node_type_bitmap_index_scan_count": 0,
                        "node_type_cte_scan_count": 0,
                        "node_type_gather_count": 0,
                        "node_type_gather_merge_count": 0,
                        "node_type_hash_count": 0,
                        "node_type_hash_join_count": 1,
                        "node_type_index_only_scan_count": 0,
                        "node_type_index_scan_count": 0,
                        "node_type_limit_count": 0,
                        "node_type_nested_loop_count": 0,
                        "node_type_seq_scan_count": 1,
                        "node_type_sort_count": 1,
                        "other_node_count": 0,
                    },
                ]
            ).write_parquet(feature_dir / "plan_features.parquet")
            pl.DataFrame(
                [],
                schema={
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
                },
            ).write_parquet(feature_dir / "plan_feature_exclusions.parquet")

            schema_dir.joinpath("features.schema.json").write_text(
                Path("schemas/features.schema.json").read_text()
            )

            with (
                patch.object(dataset_assembly, "ROOT_DIR", root_dir),
                patch.object(
                    dataset_assembly, "RAW_ARTIFACT_DIR", root_dir / "artifacts" / "raw"
                ),
                patch.object(
                    dataset_assembly,
                    "FEATURE_ARTIFACT_DIR",
                    root_dir / "artifacts" / "features",
                ),
                patch.object(
                    dataset_assembly,
                    "SQL_FEATURES_PATH",
                    root_dir / "artifacts" / "features" / "sql_features.parquet",
                ),
                patch.object(
                    dataset_assembly,
                    "SQL_FEATURE_EXCLUSIONS_PATH",
                    root_dir
                    / "artifacts"
                    / "features"
                    / "sql_feature_exclusions.parquet",
                ),
                patch.object(
                    dataset_assembly,
                    "PLAN_FEATURES_PATH",
                    root_dir / "artifacts" / "features" / "plan_features.parquet",
                ),
                patch.object(
                    dataset_assembly,
                    "PLAN_FEATURE_EXCLUSIONS_PATH",
                    root_dir
                    / "artifacts"
                    / "features"
                    / "plan_feature_exclusions.parquet",
                ),
                patch.object(
                    dataset_assembly,
                    "FEATURES_PATH",
                    root_dir / "artifacts" / "features" / "features.parquet",
                ),
                patch.object(
                    dataset_assembly,
                    "FEATURES_SCHEMA_PATH",
                    root_dir / "schemas" / "features.schema.json",
                ),
            ):
                summary = dataset_assembly.assemble_feature_dataset()

            self.assertEqual(summary["feature_rows"], 2)
            result = pl.read_parquet(
                root_dir / "artifacts" / "features" / "features.parquet"
            )
            self.assertEqual(result.height, 2)
            self.assertEqual(result.row(0, named=True)["sql_features_broadcast"], True)
            self.assertEqual(
                result.row(0, named=True)["plan_features_broadcast"], False
            )
            self.assertEqual(
                result.row(0, named=True)["targets"]["planner_total_cost"], 11.0
            )
            self.assertEqual(
                result.row(0, named=True)["targets"]["planning_time_ms"], 10.0
            )
            self.assertEqual(
                result.row(1, named=True)["plan_features"]["join_node_count"], 1
            )
            self.assertEqual(
                result.row(0, named=True)["null_indicator_columns"],
                [],
            )
            self.assertEqual(
                result.schema["null_indicator_columns"], pl.List(pl.String)
            )

    def test_assemble_feature_dataset_drops_explicit_feature_exclusions(self) -> None:
        successful_observations = pl.DataFrame(
            [
                {"observation_id": "obs-1", "query_instance_id": "q-1"},
                {"observation_id": "obs-2", "query_instance_id": "q-2"},
                {"observation_id": "obs-3", "query_instance_id": "q-3"},
            ]
        )
        sql_feature_exclusions = pl.DataFrame([{"query_instance_id": "q-2"}])
        plan_feature_exclusions = pl.DataFrame([{"observation_id": "obs-3"}])

        eligible = dataset_assembly.apply_feature_exclusions(
            successful_observations=successful_observations,
            sql_feature_exclusions=sql_feature_exclusions,
            plan_feature_exclusions=plan_feature_exclusions,
        )

        self.assertEqual(eligible["observation_id"].to_list(), ["obs-1"])


if __name__ == "__main__":
    unittest.main()
