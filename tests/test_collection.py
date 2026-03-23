"""Tests for phase 1b raw collection helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ivory import collection
from ivory.collection import AttemptExecution, QueryInstance
from ivory.config import PostgresConfig


def _settings() -> PostgresConfig:
    return PostgresConfig(
        version="16",
        host="127.0.0.1",
        port=55432,
        user="ivory",
        password="ivory",
        admin_database="postgres",
        docker_compose_file=Path("docker-compose.yml"),
        docker_service_name="postgres",
        dbgen_service_name="tpch-dbgen",
        data_root=Path("/tmp/tpch-data"),
        dbgen_image_tag="ivory/tpch-dbgen:phase-1a",
        dbgen_repo="https://github.com/electrum/tpch-dbgen.git",
        dbgen_commit="32f1c1b92d1664dba542e927d23d86ffa57aa253",
        scale_factor_databases={"0.1": "tpch_sf_0_1"},
    )


def _query_instance() -> QueryInstance:
    return QueryInstance(
        template_id="q1",
        parameter_set_id="q1-p0000",
        query_instance_id="q1-q1-p0000-sf-0.1",
        scale_factor="0.1",
        parameter_index=0,
        qgen_seed=123,
        sql_text="select 1;\n",
    )


class NormalizeQgenSqlTests(unittest.TestCase):
    def test_normalize_qgen_sql_converts_intervals_and_ignores_negative_limit(
        self,
    ) -> None:
        sql_text = """
-- using 123 as a seed to the RNG

select
    *
from lineitem
where l_shipdate <= date '1998-12-01' - interval '70' day (3)
;
limit -1;
"""
        normalized = collection.normalize_qgen_sql(sql_text, template_number=1)
        self.assertIn("interval '70 day'", normalized)
        self.assertNotIn("-- using", normalized)
        self.assertNotIn("limit -1", normalized.lower())

    def test_normalize_qgen_sql_preserves_postgres_limit(self) -> None:
        sql_text = """
select
    s_name
from supplier
;
limit 100;
"""
        normalized = collection.normalize_qgen_sql(sql_text, template_number=21)
        self.assertIn("limit 100;", normalized.lower())

    def test_rewrite_query_15_uses_single_statement_cte(self) -> None:
        sql_text = """
create view revenue0 (supplier_no, total_revenue) as
    select
        l_suppkey,
        sum(l_extendedprice * (1 - l_discount))
    from
        lineitem
    where
        l_shipdate >= date '1993-09-01'
    group by
        l_suppkey;

select
    s_suppkey,
    s_name
from
    supplier,
    revenue0
where
    s_suppkey = supplier_no;

drop view revenue0;
"""
        rewritten = collection.rewrite_query_15(sql_text)
        self.assertTrue(rewritten.lower().startswith("with revenue0"))
        self.assertNotIn("create view", rewritten.lower())
        self.assertNotIn("drop view", rewritten.lower())


class CollectQueryAttemptsTests(unittest.TestCase):
    def test_collect_query_attempts_retries_until_success(self) -> None:
        execution_results = [
            AttemptExecution(
                status="failed",
                planner_total_cost=None,
                planning_time_ms=None,
                execution_time_ms=None,
                wall_clock_runtime_ms=1.0,
                row_count=None,
                plan_document=None,
                error_class="RuntimeError",
                error_message="boom",
                failure_reason="execution_error",
            ),
            AttemptExecution(
                status="success",
                planner_total_cost=1.0,
                planning_time_ms=2.0,
                execution_time_ms=3.0,
                wall_clock_runtime_ms=4.0,
                row_count=5,
                plan_document={"Plan": {"Total Cost": 1.0}},
                error_class=None,
                error_message=None,
                failure_reason=None,
            ),
        ]
        with patch.object(
            collection,
            "execute_query_instance",
            side_effect=execution_results,
        ):
            result = collection.collect_query_attempts(
                settings=_settings(),
                query_instance=_query_instance(),
                run_index=0,
                retry_count=2,
                timeout_ms=1000,
            )

        self.assertEqual(len(result["raw_rows"]), 2)
        self.assertEqual(result["raw_rows"][0]["status"], "failed")
        self.assertEqual(result["raw_rows"][1]["status"], "success")
        self.assertTrue(result["raw_rows"][1]["is_retry"])
        self.assertEqual(len(result["plan_rows"]), 1)
        self.assertIsNone(result["exclusion_row"])

    def test_collect_query_attempts_emits_exclusion_after_exhausted_retries(
        self,
    ) -> None:
        execution = AttemptExecution(
            status="timed_out",
            planner_total_cost=None,
            planning_time_ms=None,
            execution_time_ms=None,
            wall_clock_runtime_ms=1.0,
            row_count=None,
            plan_document=None,
            error_class="QueryCanceled",
            error_message="canceling statement due to statement timeout",
            failure_reason="statement_timeout",
        )
        with patch.object(
            collection, "execute_query_instance", side_effect=[execution, execution]
        ):
            result = collection.collect_query_attempts(
                settings=_settings(),
                query_instance=_query_instance(),
                run_index=0,
                retry_count=1,
                timeout_ms=1,
            )

        self.assertEqual(len(result["raw_rows"]), 2)
        self.assertEqual(result["raw_rows"][-1]["status"], "timed_out")
        self.assertEqual(result["exclusion_row"]["status"], "excluded")
        self.assertTrue(result["exclusion_row"]["is_excluded"])


class ManifestTests(unittest.TestCase):
    def test_build_collection_manifest_reports_identifier_coverage(self) -> None:
        config = {
            "experiment": {
                "runs_per_query": 3,
            }
        }
        raw_rows = [
            {"observation_id": "obs-1", "status": "success"},
            {"observation_id": "obs-2", "status": "failed"},
        ]
        plan_rows = [{"observation_id": "obs-1"}]
        exclusions = [{"status": "excluded"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "experiment.toml"
            config_path.write_text("[experiment]\n")
            raw_runs_path = Path(tmpdir) / "artifacts/raw/raw_runs.parquet"
            plans_path = Path(tmpdir) / "artifacts/raw/plans.jsonl"
            exclusions_path = Path(tmpdir) / "artifacts/raw/exclusions.parquet"
            with (
                patch.object(collection, "ROOT_DIR", Path(tmpdir)),
                patch.object(collection, "RAW_RUNS_PATH", raw_runs_path),
                patch.object(collection, "PLANS_PATH", plans_path),
                patch.object(collection, "EXCLUSIONS_PATH", exclusions_path),
            ):
                manifest = collection.build_collection_manifest(
                    config=config,
                    config_path=str(config_path),
                    selected_scales=["0.1"],
                    selected_templates=["q1"],
                    timeout_ms=1000,
                    retry_count=2,
                    params_per_template=1,
                    raw_rows=raw_rows,
                    plan_rows=plan_rows,
                    exclusion_rows=exclusions,
                )

        self.assertIn("identifier_coverage", manifest)
        self.assertTrue(
            manifest["identifier_coverage"][
                "successful_observation_ids_match_plan_rows"
            ]
        )


if __name__ == "__main__":
    unittest.main()
