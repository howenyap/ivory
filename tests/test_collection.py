"""Tests for phase 1b raw collection helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ivory import collection
from ivory.collection import AttemptExecution, QueryInstance, ScaleArtifactPaths
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


def _artifact_paths(tmpdir: str, scale_factor: str = "0.1") -> ScaleArtifactPaths:
    scale_dir = Path(tmpdir) / "artifacts/raw" / f"sf_{scale_factor.replace('.', '_')}"
    return ScaleArtifactPaths(
        scale_factor=scale_factor,
        scale_dir=scale_dir,
        raw_runs_path=scale_dir / "raw_runs.parquet",
        plans_path=scale_dir / "plans.jsonl",
        exclusions_path=scale_dir / "exclusions.parquet",
        manifest_path=scale_dir / "collection_manifest.json",
        raw_runs_checkpoint_path=scale_dir / ".raw_runs.checkpoint.jsonl",
        plans_checkpoint_path=scale_dir / ".plans.checkpoint.jsonl",
        exclusions_checkpoint_path=scale_dir / ".exclusions.checkpoint.jsonl",
        state_path=scale_dir / ".collection_state.json",
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
            artifact_paths = _artifact_paths(tmpdir)
            with (
                patch.object(collection, "ROOT_DIR", Path(tmpdir)),
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
                    artifact_paths=artifact_paths,
                )

        self.assertIn("identifier_coverage", manifest)
        self.assertTrue(
            manifest["identifier_coverage"][
                "successful_observation_ids_match_plan_rows"
            ]
        )


class ResumeAndCheckpointTests(unittest.TestCase):
    def test_select_scales_rejects_unconfigured_scale_factors(self) -> None:
        config = {
            "experiment": {
                "scale_factors": [0.1, 1.0, 3.0],
                "tpch_scale_factors": [0.1, 1.0, 3.0],
            }
        }
        with self.assertRaisesRegex(ValueError, "Unconfigured scale factor"):
            collection._select_scales(config, None, ["5.0"])

    def test_load_compatible_scale_manifests_filters_by_requested_settings(
        self,
    ) -> None:
        config = {
            "experiment": {
                "scale_factors": [0.1, 1.0],
                "tpch_scale_factors": [0.1, 1.0],
                "runs_per_query": 3,
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "configs/experiment.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text("[experiment]\n")
            raw_root = Path(tmpdir) / "artifacts/raw"
            scale_one = _artifact_paths(tmpdir, "0.1")
            scale_two = _artifact_paths(tmpdir, "1.0")
            scale_one.scale_dir.mkdir(parents=True)
            scale_two.scale_dir.mkdir(parents=True)
            state_one = collection.build_collection_state(
                config=config,
                config_path=str(config_path),
                selected_scales=["0.1"],
                selected_templates=["q1"],
                timeout_ms=1000,
                retry_count=2,
                params_per_template=50,
            )
            state_two = collection.build_collection_state(
                config=config,
                config_path=str(config_path),
                selected_scales=["1.0"],
                selected_templates=["q1"],
                timeout_ms=1000,
                retry_count=2,
                params_per_template=5,
            )
            scale_one.manifest_path.write_text(
                json.dumps(
                    {
                        **state_one,
                        "collection_timestamp_utc": "now",
                        "code_revision": None,
                        "artifacts": {
                            "raw_runs": {"path": "a", "row_count": 1},
                            "plans": {"path": "b", "row_count": 1},
                            "exclusions": {"path": "c", "row_count": 0},
                            "collection_manifest": {"path": "d"},
                        },
                        "status_counts": {"success": 1, "excluded": 0},
                        "identifier_coverage": {
                            "successful_raw_rows": 1,
                            "plan_rows": 1,
                            "successful_observation_ids_are_unique": True,
                            "plan_observation_ids_are_unique": True,
                            "successful_observation_ids_match_plan_rows": True,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            scale_two.manifest_path.write_text(
                json.dumps(
                    {
                        **state_two,
                        "collection_timestamp_utc": "now",
                        "code_revision": None,
                        "artifacts": {
                            "raw_runs": {"path": "a", "row_count": 1},
                            "plans": {"path": "b", "row_count": 1},
                            "exclusions": {"path": "c", "row_count": 0},
                            "collection_manifest": {"path": "d"},
                        },
                        "status_counts": {"success": 1, "excluded": 0},
                        "identifier_coverage": {
                            "successful_raw_rows": 1,
                            "plan_rows": 1,
                            "successful_observation_ids_are_unique": True,
                            "plan_observation_ids_are_unique": True,
                            "successful_observation_ids_match_plan_rows": True,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )

            with (
                patch.object(collection, "ROOT_DIR", Path(tmpdir)),
                patch.object(collection, "RAW_ARTIFACT_DIR", raw_root),
            ):
                manifests = collection.load_compatible_scale_manifests(
                    config=config,
                    config_path=str(config_path),
                    selected_templates=["q1"],
                    timeout_ms=1000,
                    retry_count=2,
                    params_per_template=50,
                )

        self.assertEqual(
            [manifest["scale_factors_included"][0] for manifest in manifests],
            ["0.1"],
        )

    def test_terminal_run_ids_require_matching_plan_for_success(self) -> None:
        raw_rows = [
            {
                "run_id": "run-a",
                "status": "success",
                "observation_id": "obs-a",
                "run_attempt_id": "obs-a",
            },
            {
                "run_id": "run-b",
                "status": "success",
                "observation_id": "obs-b",
                "run_attempt_id": "obs-b",
            },
        ]
        plan_rows = [{"observation_id": "obs-a"}]
        exclusion_rows = [{"run_id": "run-c"}]
        run_ids = collection.terminal_run_ids(raw_rows, plan_rows, exclusion_rows)
        self.assertEqual(run_ids, {"run-a", "run-c"})

    def test_collect_query_attempts_resume_from_existing_failed_attempt(self) -> None:
        existing_attempt_rows = [
            {
                "run_id": "q1-q1-p0000-sf-0.1-run-01",
                "run_attempt_id": "q1-q1-p0000-sf-0.1-run-01-attempt-01",
                "attempt_number": 1,
                "status": "failed",
            }
        ]
        execution = AttemptExecution(
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
        )
        with patch.object(collection, "execute_query_instance", return_value=execution):
            result = collection.collect_query_attempts(
                settings=_settings(),
                query_instance=_query_instance(),
                run_index=0,
                retry_count=2,
                timeout_ms=1000,
                existing_attempt_rows=existing_attempt_rows,
            )

        self.assertEqual(len(result["raw_rows"]), 1)
        self.assertEqual(result["raw_rows"][0]["attempt_number"], 2)
        self.assertEqual(result["raw_rows"][0]["status"], "success")

    def test_record_generation_failure_produces_terminal_exclusion(self) -> None:
        query_key = collection.build_query_key(
            template_id="q1",
            scale_factor="0.1",
            parameter_index=0,
            seed=123,
        )
        rows, exclusion = collection.record_generation_failure(
            query_key=query_key,
            run_index=0,
            error=RuntimeError("qgen boom"),
            retry_count=2,
            existing_attempt_rows=[],
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["failure_reason"], "query_generation_failed")
        self.assertIsNotNone(exclusion)
        assert exclusion is not None
        self.assertEqual(exclusion["status"], "excluded")
        self.assertEqual(exclusion["failure_reason"], "query_generation_failed")

    def test_load_checkpoint_rows_discards_orphaned_success_and_plan_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_paths = _artifact_paths(tmpdir)
            artifact_paths.raw_runs_checkpoint_path.parent.mkdir(parents=True)
            artifact_paths.raw_runs_checkpoint_path.write_text(
                "\n".join(
                    [
                        '{"run_id":"run-a","run_attempt_id":"obs-a","observation_id":"obs-a","attempt_number":1,"status":"success"}',
                        '{"run_id":"run-b","run_attempt_id":"obs-b","observation_id":"obs-b","attempt_number":1,"status":"failed"}',
                    ]
                )
                + "\n"
            )
            artifact_paths.plans_checkpoint_path.write_text(
                "\n".join(
                    [
                        '{"observation_id":"obs-a"}',
                        '{"observation_id":"obs-z"}',
                    ]
                )
                + "\n"
            )
            artifact_paths.exclusions_checkpoint_path.write_text("")

            raw_rows, plan_rows, exclusion_rows = collection.load_checkpoint_rows(
                artifact_paths
            )

        self.assertEqual(
            [row["observation_id"] for row in raw_rows],
            ["obs-a", "obs-b"],
        )
        self.assertEqual([row["observation_id"] for row in plan_rows], ["obs-a"])
        self.assertEqual(exclusion_rows, [])

    def test_load_checkpoint_rows_drops_success_without_matching_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_paths = _artifact_paths(tmpdir)
            artifact_paths.raw_runs_checkpoint_path.parent.mkdir(parents=True)
            artifact_paths.raw_runs_checkpoint_path.write_text(
                '{"run_id":"run-a","run_attempt_id":"obs-a","observation_id":"obs-a","attempt_number":1,"status":"success"}\n'
            )
            artifact_paths.plans_checkpoint_path.write_text("")
            artifact_paths.exclusions_checkpoint_path.write_text("")

            raw_rows, plan_rows, exclusion_rows = collection.load_checkpoint_rows(
                artifact_paths
            )

        self.assertEqual(raw_rows, [])
        self.assertEqual(plan_rows, [])
        self.assertEqual(exclusion_rows, [])

    def test_initialize_collection_state_clears_visible_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_paths = _artifact_paths(tmpdir)
            artifact_paths.scale_dir.mkdir(parents=True)
            for path in [
                artifact_paths.raw_runs_path,
                artifact_paths.plans_path,
                artifact_paths.exclusions_path,
                artifact_paths.manifest_path,
                artifact_paths.state_path,
                artifact_paths.raw_runs_checkpoint_path,
                artifact_paths.plans_checkpoint_path,
                artifact_paths.exclusions_checkpoint_path,
            ]:
                path.write_text("stale\n")

            state = {"retry_count": 2}
            collection.initialize_collection_state(state, artifact_paths)

            self.assertFalse(artifact_paths.raw_runs_path.exists())
            self.assertFalse(artifact_paths.plans_path.exists())
            self.assertFalse(artifact_paths.exclusions_path.exists())
            self.assertFalse(artifact_paths.manifest_path.exists())
            self.assertTrue(artifact_paths.state_path.exists())
            self.assertEqual(
                artifact_paths.state_path.read_text(),
                '{\n  "retry_count": 2\n}\n',
            )

    def test_cleanup_all_scale_artifact_dirs_removes_stale_scale_directories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_root = Path(tmpdir) / "artifacts/raw"
            stale_one = raw_root / "sf_0_1"
            stale_two = raw_root / "sf_1_0"
            stale_one.mkdir(parents=True)
            stale_two.mkdir(parents=True)
            (stale_one / "raw_runs.parquet").write_text("stale\n")
            (stale_two / "plans.jsonl").write_text("stale\n")

            with patch.object(collection, "RAW_ARTIFACT_DIR", raw_root):
                collection.cleanup_all_scale_artifact_dirs()

            self.assertFalse(stale_one.exists())
            self.assertFalse(stale_two.exists())

    def test_validate_materialized_manifest_rejects_mismatched_resume_settings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_paths = _artifact_paths(tmpdir)
            artifact_paths.scale_dir.mkdir(parents=True)
            expected_state = {
                "config_path": "/tmp/experiment.toml",
                "config_hash_sha256": "expected",
                "scale_factors_included": ["0.1"],
                "templates_included": ["q1"],
                "timeout_ms": 1000,
                "retry_count": 2,
                "runs_per_query": 3,
                "parameter_sets_per_template": 1,
            }
            artifact_paths.manifest_path.write_text(
                "{"
                '"config_path":"/tmp/experiment.toml",'
                '"config_hash_sha256":"different",'
                '"scale_factors_included":["0.1"],'
                '"templates_included":["q1"],'
                '"timeout_ms":1000,'
                '"retry_count":2,'
                '"runs_per_query":3,'
                '"parameter_sets_per_template":1'
                "}\n"
            )

            with self.assertRaisesRegex(ValueError, "Materialized scale artifacts"):
                collection.validate_materialized_manifest(
                    expected_state,
                    artifact_paths,
                )

    def test_validate_materialized_manifest_rejects_missing_materialized_files(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_paths = _artifact_paths(tmpdir)
            artifact_paths.scale_dir.mkdir(parents=True)
            expected_state = {
                "config_path": "/tmp/experiment.toml",
                "config_hash_sha256": "expected",
                "scale_factors_included": ["0.1"],
                "templates_included": ["q1"],
                "timeout_ms": 1000,
                "retry_count": 2,
                "runs_per_query": 3,
                "parameter_sets_per_template": 1,
            }
            artifact_paths.manifest_path.write_text(
                "{"
                '"config_path":"/tmp/experiment.toml",'
                '"config_hash_sha256":"expected",'
                '"scale_factors_included":["0.1"],'
                '"templates_included":["q1"],'
                '"timeout_ms":1000,'
                '"retry_count":2,'
                '"runs_per_query":3,'
                '"parameter_sets_per_template":1,'
                '"artifacts":{'
                '"raw_runs":{"path":"raw","row_count":1},'
                '"plans":{"path":"plans","row_count":1},'
                '"exclusions":{"path":"exclusions","row_count":0},'
                '"collection_manifest":{"path":"manifest"}'
                "},"
                '"status_counts":{"success":1,"excluded":0},'
                '"identifier_coverage":{'
                '"successful_raw_rows":1,'
                '"plan_rows":1,'
                '"successful_observation_ids_are_unique":true,'
                '"plan_observation_ids_are_unique":true,'
                '"successful_observation_ids_match_plan_rows":true'
                "}"
                "}\n"
            )

            with self.assertRaisesRegex(ValueError, "Missing files"):
                collection.validate_materialized_manifest(
                    expected_state,
                    artifact_paths,
                )


if __name__ == "__main__":
    unittest.main()
