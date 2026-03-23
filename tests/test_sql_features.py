"""Tests for phase 2a SQL structural feature extraction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl
from sqlglot import parse_one
from sqlglot.errors import ParseError

from ivory import sql_features


def _raw_runs_row(
    *,
    query_instance_id: str,
    template_id: str,
    parameter_set_id: str,
    scale_factor: float,
    sql_text: str,
    status: str = "success",
) -> dict[str, object]:
    return {
        "observation_id": f"{query_instance_id}-obs-1",
        "run_attempt_id": f"{query_instance_id}-attempt-1",
        "run_id": f"{query_instance_id}-run-1",
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
        "planner_total_cost": 1.0,
        "planning_time_ms": 2.0,
        "execution_time_ms": 3.0,
        "wall_clock_runtime_ms": 4.0,
        "row_count": 5,
        "sql_text": sql_text,
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


class SqlFeatureExtractionTests(unittest.TestCase):
    def test_extract_sql_features_counts_structural_nodes(self) -> None:
        parsed = parse_one(
            """
            with recent_orders as (
                select o_custkey, o_orderkey
                from orders
                where o_totalprice > 100
            )
            select c_custkey, sum(l_extendedprice)
            from customer
            join orders on c_custkey = o_custkey
            join lineitem on o_orderkey = l_orderkey
            where c_nationkey = 1
              and exists (
                  select 1
                  from recent_orders
                  where recent_orders.o_custkey = customer.c_custkey
              )
            group by c_custkey
            order by c_custkey
            limit 10
            """,
            read="postgres",
        )

        features = sql_features.extract_sql_features(parsed)

        self.assertTrue(features["aggregation_present"])
        self.assertEqual(features["selected_column_count"], 2)
        self.assertEqual(features["table_count"], 4)
        self.assertEqual(features["join_count"], 2)
        self.assertEqual(features["predicate_count"], 6)
        self.assertEqual(features["group_by_count"], 1)
        self.assertEqual(features["order_by_count"], 1)
        self.assertEqual(features["limit_count"], 1)
        self.assertEqual(features["subquery_count"], 1)

    def test_build_sql_feature_exclusion_row_records_parse_status(self) -> None:
        query_instance = {
            "query_instance_id": "q1-q1-p0000-sf-0.1",
            "template_id": "q1",
            "parameter_set_id": "q1-p0000",
            "scale_factor": 0.1,
        }
        error = ParseError("Expected table name")

        exclusion = sql_features.build_sql_feature_exclusion_row(query_instance, error)

        self.assertEqual(exclusion["feature_status"], "excluded")
        self.assertEqual(exclusion["parse_status"], "parse_error")
        self.assertEqual(exclusion["error_class"], "ParseError")

    def test_featurize_sql_queries_writes_features_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            raw_sql = "select * from orders where o_orderkey = 1"
            _write_raw_runs(
                tmpdir,
                "0.1",
                [
                    _raw_runs_row(
                        query_instance_id="q1-q1-p0000-sf-0.1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                        sql_text=raw_sql,
                    ),
                    _raw_runs_row(
                        query_instance_id="q1-q1-p0000-sf-0.1",
                        template_id="q1",
                        parameter_set_id="q1-p0000",
                        scale_factor=0.1,
                        sql_text=raw_sql,
                    ),
                    _raw_runs_row(
                        query_instance_id="q2-q2-p0000-sf-0.1",
                        template_id="q2",
                        parameter_set_id="q2-p0000",
                        scale_factor=0.1,
                        sql_text="select from",
                    ),
                ],
            )

            schema_dir = root_dir / "schemas"
            schema_dir.mkdir(parents=True, exist_ok=True)
            schema_dir.joinpath("sql_features.schema.json").write_text(
                Path("schemas/sql_features.schema.json").read_text()
            )

            with (
                patch.object(sql_features, "ROOT_DIR", root_dir),
                patch.object(
                    sql_features, "RAW_ARTIFACT_DIR", root_dir / "artifacts" / "raw"
                ),
                patch.object(
                    sql_features,
                    "FEATURE_ARTIFACT_DIR",
                    root_dir / "artifacts" / "features",
                ),
                patch.object(
                    sql_features,
                    "SQL_FEATURES_PATH",
                    root_dir / "artifacts" / "features" / "sql_features.parquet",
                ),
                patch.object(
                    sql_features,
                    "SQL_FEATURE_EXCLUSIONS_PATH",
                    root_dir
                    / "artifacts"
                    / "features"
                    / "sql_feature_exclusions.parquet",
                ),
                patch.object(
                    sql_features,
                    "SQL_FEATURE_SCHEMA_PATH",
                    root_dir / "schemas" / "sql_features.schema.json",
                ),
            ):
                summary = sql_features.featurize_sql_queries()

            self.assertEqual(summary["input_query_instances"], 2)
            self.assertEqual(summary["feature_rows"], 1)
            self.assertEqual(summary["exclusion_rows"], 1)

            features_df = pl.read_parquet(
                root_dir / "artifacts" / "features" / "sql_features.parquet"
            )
            exclusions_df = pl.read_parquet(
                root_dir / "artifacts" / "features" / "sql_feature_exclusions.parquet"
            )
            self.assertEqual(features_df.height, 1)
            self.assertEqual(exclusions_df.height, 1)
            feature_row = features_df.row(0, named=True)
            self.assertEqual(feature_row["feature_status"], "available")
            self.assertFalse(feature_row["aggregation_present"])
            self.assertEqual(feature_row["selected_column_count"], 1)
            self.assertEqual(
                exclusions_df.row(0, named=True)["parse_status"], "parse_error"
            )


if __name__ == "__main__":
    unittest.main()
