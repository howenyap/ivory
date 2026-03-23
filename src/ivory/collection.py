"""Query generation and raw collection helpers for phase 1b."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from psycopg.errors import QueryCanceled

from ivory.config import DEFAULT_CONFIG_PATH, PostgresConfig, experiment_scale_factors
from ivory.postgres import compose_args, database_connection

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "raw"
RAW_RUNS_PATH = RAW_ARTIFACT_DIR / "raw_runs.parquet"
PLANS_PATH = RAW_ARTIFACT_DIR / "plans.jsonl"
MANIFEST_PATH = RAW_ARTIFACT_DIR / "collection_manifest.json"
EXCLUSIONS_PATH = RAW_ARTIFACT_DIR / "exclusions.parquet"
TPCH_TEMPLATE_IDS = tuple(f"q{query_id}" for query_id in range(1, 23))
DEFAULT_PARAMETER_SETS_PER_TEMPLATE = 10
STATUS_TO_RUN_STATUS = {
    "success": "succeeded",
    "failed": "failed",
    "timed_out": "timed_out",
    "excluded": "excluded",
}
Q15_PATTERN = re.compile(
    r"create\s+view\s+revenue0\s*\(supplier_no,\s*total_revenue\)\s+as\s*"
    r"(?P<cte>.*?)"
    r"(?P<select>select\s+s_suppkey,.*?)(?:drop\s+view\s+revenue0;\s*)?$",
    re.IGNORECASE | re.DOTALL,
)
INTERVAL_PATTERN = re.compile(
    r"interval\s+'(?P<value>[^']+)'\s+(?P<unit>day|month|year)\s*(?:\(\d+\))?",
    re.IGNORECASE,
)
LIMIT_PATTERN = re.compile(r"limit\s+(?P<limit>-?\d+)\s*;", re.IGNORECASE)


@dataclass(frozen=True)
class QueryInstance:
    template_id: str
    parameter_set_id: str
    query_instance_id: str
    scale_factor: str
    parameter_index: int
    qgen_seed: int
    sql_text: str


@dataclass(frozen=True)
class AttemptExecution:
    status: str
    planner_total_cost: float | None
    planning_time_ms: float | None
    execution_time_ms: float | None
    wall_clock_runtime_ms: float
    row_count: int | None
    plan_document: dict[str, Any] | None
    error_class: str | None
    error_message: str | None
    failure_reason: str | None


def collect_raw_artifacts(
    config: dict[str, Any],
    settings: PostgresConfig,
    *,
    config_path: str | None = None,
    limit_templates: int | None = None,
    limit_params: int | None = None,
    limit_scales: int | None = None,
    timeout_ms: int | None = None,
    params_per_template: int = DEFAULT_PARAMETER_SETS_PER_TEMPLATE,
) -> dict[str, Any]:
    """Run the phase 1b collection workflow and persist raw artifacts."""
    seed = int(config["experiment"]["seed"])
    retry_count = int(config["experiment"]["retry_count"])
    runs_per_query = int(config["experiment"]["runs_per_query"])
    configured_timeout_ms = int(
        float(config["experiment"]["query_timeout_seconds"]) * 1000
    )
    effective_timeout_ms = (
        timeout_ms if timeout_ms is not None else configured_timeout_ms
    )

    selected_scales = _select_scales(config, limit_scales)
    selected_templates = _select_templates(limit_templates)
    parameter_count = limit_params if limit_params is not None else params_per_template

    raw_rows: list[dict[str, Any]] = []
    plan_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []

    for scale_factor in selected_scales:
        for template_id in selected_templates:
            for parameter_index in range(parameter_count):
                query_instance = build_query_instance(
                    settings=settings,
                    template_id=template_id,
                    scale_factor=scale_factor,
                    parameter_index=parameter_index,
                    seed=seed,
                )
                for run_index in range(runs_per_query):
                    attempts = collect_query_attempts(
                        settings=settings,
                        query_instance=query_instance,
                        run_index=run_index,
                        retry_count=retry_count,
                        timeout_ms=effective_timeout_ms,
                    )
                    raw_rows.extend(attempts["raw_rows"])
                    plan_rows.extend(attempts["plan_rows"])
                    if attempts["exclusion_row"] is not None:
                        exclusion_rows.append(attempts["exclusion_row"])

    RAW_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    raw_frame = _raw_runs_frame(raw_rows)
    exclusion_frame = _exclusions_frame(exclusion_rows)
    raw_frame.write_parquet(RAW_RUNS_PATH)
    exclusion_frame.write_parquet(EXCLUSIONS_PATH)
    _write_plans(plan_rows)

    manifest = build_collection_manifest(
        config=config,
        config_path=config_path,
        selected_scales=selected_scales,
        selected_templates=selected_templates,
        timeout_ms=effective_timeout_ms,
        retry_count=retry_count,
        params_per_template=parameter_count,
        raw_rows=raw_rows,
        plan_rows=plan_rows,
        exclusion_rows=exclusion_rows,
    )
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def collect_query_attempts(
    *,
    settings: PostgresConfig,
    query_instance: QueryInstance,
    run_index: int,
    retry_count: int,
    timeout_ms: int,
) -> dict[str, Any]:
    """Collect all attempts for one observation run."""
    raw_rows: list[dict[str, Any]] = []
    plan_rows: list[dict[str, Any]] = []
    exclusion_row: dict[str, Any] | None = None
    max_attempts = retry_count + 1
    final_attempt: dict[str, Any] | None = None

    for attempt_number in range(1, max_attempts + 1):
        execution = execute_query_instance(
            settings=settings,
            query_instance=query_instance,
            timeout_ms=timeout_ms,
        )
        attempt_row = build_attempt_row(
            query_instance=query_instance,
            run_index=run_index,
            attempt_number=attempt_number,
            execution=execution,
        )
        raw_rows.append(attempt_row)
        final_attempt = attempt_row
        if execution.status == "success":
            plan_rows.append(
                {
                    "observation_id": attempt_row["observation_id"],
                    "run_attempt_id": attempt_row["run_attempt_id"],
                    "query_instance_id": query_instance.query_instance_id,
                    "template_id": query_instance.template_id,
                    "parameter_set_id": query_instance.parameter_set_id,
                    "scale_factor": float(query_instance.scale_factor),
                    "plan": execution.plan_document,
                }
            )
            break
    else:
        assert final_attempt is not None
        exclusion_row = build_exclusion_row(final_attempt)

    return {
        "raw_rows": raw_rows,
        "plan_rows": plan_rows,
        "exclusion_row": exclusion_row,
    }


def build_query_instance(
    *,
    settings: PostgresConfig,
    template_id: str,
    scale_factor: str,
    parameter_index: int,
    seed: int,
) -> QueryInstance:
    """Build a deterministic query instance for one template and scale factor."""
    template_number = template_id_to_number(template_id)
    qgen_seed = parameter_seed(seed, template_number, parameter_index)
    parameter_set_id = f"{template_id}-p{parameter_index:04d}"
    query_instance_id = f"{template_id}-{parameter_set_id}-sf-{scale_factor}"
    raw_sql = generate_tpch_query_sql(
        settings=settings,
        template_number=template_number,
        scale_factor=scale_factor,
        qgen_seed=qgen_seed,
    )
    sql_text = normalize_qgen_sql(raw_sql, template_number)
    return QueryInstance(
        template_id=template_id,
        parameter_set_id=parameter_set_id,
        query_instance_id=query_instance_id,
        scale_factor=scale_factor,
        parameter_index=parameter_index,
        qgen_seed=qgen_seed,
        sql_text=sql_text,
    )


def template_id_to_number(template_id: str) -> int:
    """Return the numeric query id for a `qN` template id."""
    return int(template_id.removeprefix("q"))


def parameter_seed(base_seed: int, template_number: int, parameter_index: int) -> int:
    """Derive a deterministic qgen seed for one parameter set."""
    return base_seed + (template_number * 10000) + parameter_index


def generate_tpch_query_sql(
    *,
    settings: PostgresConfig,
    template_number: int,
    scale_factor: str,
    qgen_seed: int,
) -> str:
    """Generate one TPC-H SQL statement through qgen inside the pinned image."""
    command = (
        "cd /opt/tpch-dbgen "
        "&& DSS_QUERY=queries ./qgen "
        f"-s {scale_factor} -r {qgen_seed} {template_number}"
    )
    result = subprocess.run(
        [
            *compose_args(settings),
            "run",
            "--rm",
            settings.dbgen_service_name,
            command,
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"qgen failed for query {template_number} at scale {scale_factor}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def normalize_qgen_sql(sql_text: str, template_number: int) -> str:
    """Normalize qgen SQL output into a PostgreSQL-compatible statement."""
    cleaned_lines: list[str] = []
    limit: int | None = None
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("-- using "):
            continue
        limit_match = LIMIT_PATTERN.fullmatch(stripped)
        if limit_match is not None:
            candidate_limit = int(limit_match.group("limit"))
            if candidate_limit > 0:
                limit = candidate_limit
            continue
        cleaned_lines.append(line)

    normalized = "\n".join(cleaned_lines).strip()
    normalized = INTERVAL_PATTERN.sub(
        lambda match: (
            f"interval '{match.group('value')} {match.group('unit').lower()}'"
        ),
        normalized,
    )
    if template_number == 15 and "create view revenue0" in normalized.lower():
        normalized = rewrite_query_15(normalized)
    if limit is not None:
        normalized = append_limit_clause(normalized, limit)
    return normalized.rstrip("; \n") + ";\n"


def rewrite_query_15(sql_text: str) -> str:
    """Rewrite TPC-H query 15 into a single PostgreSQL statement."""
    match = Q15_PATTERN.search(sql_text)
    if match is None:
        raise ValueError("Could not rewrite TPC-H query 15 into a single statement.")
    cte_sql = match.group("cte").strip().rstrip(";")
    select_sql = match.group("select").strip().rstrip(";")
    return (
        f"with revenue0 (supplier_no, total_revenue) as (\n{cte_sql}\n)\n\n{select_sql}"
    )


def append_limit_clause(sql_text: str, limit: int) -> str:
    """Append a LIMIT clause to the final statement."""
    stripped = sql_text.rstrip()
    if stripped.endswith(";"):
        stripped = stripped[:-1]
    return f"{stripped}\nlimit {limit}"


def execute_query_instance(
    *,
    settings: PostgresConfig,
    query_instance: QueryInstance,
    timeout_ms: int,
) -> AttemptExecution:
    """Execute one query instance and return raw collection details."""
    database = settings.scale_factor_databases[query_instance.scale_factor]
    start = time.perf_counter()
    try:
        with database_connection(settings, database) as conn:
            conn.execute(f"SET statement_timeout = '{timeout_ms}ms'")
            row = conn.execute(
                f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query_instance.sql_text}"
            ).fetchone()
        wall_clock_runtime_ms = (time.perf_counter() - start) * 1000
        plan_document = row["QUERY PLAN"][0]
        root_plan = plan_document["Plan"]
        row_count = root_plan.get("Actual Rows")
        return AttemptExecution(
            status="success",
            planner_total_cost=float(root_plan["Total Cost"]),
            planning_time_ms=float(plan_document["Planning Time"]),
            execution_time_ms=float(plan_document["Execution Time"]),
            wall_clock_runtime_ms=wall_clock_runtime_ms,
            row_count=int(row_count) if row_count is not None else None,
            plan_document=plan_document,
            error_class=None,
            error_message=None,
            failure_reason=None,
        )
    except QueryCanceled as exc:
        return AttemptExecution(
            status="timed_out",
            planner_total_cost=None,
            planning_time_ms=None,
            execution_time_ms=None,
            wall_clock_runtime_ms=(time.perf_counter() - start) * 1000,
            row_count=None,
            plan_document=None,
            error_class=exc.__class__.__name__,
            error_message=str(exc),
            failure_reason="statement_timeout",
        )
    except Exception as exc:  # pragma: no cover - exercised through integration
        return AttemptExecution(
            status="failed",
            planner_total_cost=None,
            planning_time_ms=None,
            execution_time_ms=None,
            wall_clock_runtime_ms=(time.perf_counter() - start) * 1000,
            row_count=None,
            plan_document=None,
            error_class=exc.__class__.__name__,
            error_message=str(exc),
            failure_reason="execution_error",
        )


def build_attempt_row(
    *,
    query_instance: QueryInstance,
    run_index: int,
    attempt_number: int,
    execution: AttemptExecution,
) -> dict[str, Any]:
    """Build the raw row for one query attempt."""
    run_attempt_id = (
        f"{query_instance.query_instance_id}-run-{run_index + 1:02d}"
        f"-attempt-{attempt_number:02d}"
    )
    return {
        "observation_id": run_attempt_id,
        "run_attempt_id": run_attempt_id,
        "query_instance_id": query_instance.query_instance_id,
        "template_id": query_instance.template_id,
        "parameter_set_id": query_instance.parameter_set_id,
        "scale_factor": float(query_instance.scale_factor),
        "attempt_index": attempt_number - 1,
        "attempt_number": attempt_number,
        "is_retry": attempt_number > 1,
        "status": execution.status,
        "run_status": STATUS_TO_RUN_STATUS[execution.status],
        "failure_reason": execution.failure_reason,
        "include_in_modeling": execution.status == "success",
        "is_excluded": False,
        "exclusion_stage": None,
        "exclusion_reason": None,
        "planner_total_cost": execution.planner_total_cost,
        "planning_time_ms": execution.planning_time_ms,
        "execution_time_ms": execution.execution_time_ms,
        "wall_clock_runtime_ms": execution.wall_clock_runtime_ms,
        "row_count": execution.row_count,
        "sql_text": query_instance.sql_text,
        "error_class": execution.error_class,
        "error_message": execution.error_message,
    }


def build_exclusion_row(final_attempt_row: dict[str, Any]) -> dict[str, Any]:
    """Build the exclusion row for a query instance that never succeeded."""
    return {
        **{
            key: final_attempt_row[key]
            for key in (
                "query_instance_id",
                "template_id",
                "parameter_set_id",
                "scale_factor",
                "sql_text",
            )
        },
        "status": "excluded",
        "run_status": STATUS_TO_RUN_STATUS["excluded"],
        "failure_reason": final_attempt_row["failure_reason"],
        "attempt_number": final_attempt_row["attempt_number"],
        "attempt_index": final_attempt_row["attempt_index"],
        "is_retry": final_attempt_row["is_retry"],
        "include_in_modeling": False,
        "is_excluded": True,
        "exclusion_stage": "collection",
        "exclusion_reason": final_attempt_row["failure_reason"] or "collection_failure",
        "planner_total_cost": None,
        "planning_time_ms": None,
        "execution_time_ms": None,
        "wall_clock_runtime_ms": final_attempt_row["wall_clock_runtime_ms"],
        "row_count": None,
        "error_class": final_attempt_row["error_class"],
        "error_message": final_attempt_row["error_message"],
    }


def build_collection_manifest(
    *,
    config: dict[str, Any],
    config_path: str | None,
    selected_scales: list[str],
    selected_templates: list[str],
    timeout_ms: int,
    retry_count: int,
    params_per_template: int,
    raw_rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    exclusion_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the collection manifest for raw artifacts."""
    successful_observation_ids = [
        row["observation_id"] for row in raw_rows if row["status"] == "success"
    ]
    plan_observation_ids = [row["observation_id"] for row in plan_rows]
    return {
        "collection_timestamp_utc": datetime.now(UTC).isoformat(),
        "config_path": str((ROOT_DIR / (config_path or DEFAULT_CONFIG_PATH)).resolve()),
        "config_hash_sha256": config_hash(config_path),
        "scale_factors_included": selected_scales,
        "templates_included": selected_templates,
        "timeout_ms": timeout_ms,
        "retry_count": retry_count,
        "runs_per_query": int(config["experiment"]["runs_per_query"]),
        "parameter_sets_per_template": params_per_template,
        "code_revision": git_revision(),
        "artifacts": {
            "raw_runs": {
                "path": str(RAW_RUNS_PATH.relative_to(ROOT_DIR)),
                "row_count": len(raw_rows),
            },
            "plans": {
                "path": str(PLANS_PATH.relative_to(ROOT_DIR)),
                "row_count": len(plan_rows),
            },
            "exclusions": {
                "path": str(EXCLUSIONS_PATH.relative_to(ROOT_DIR)),
                "row_count": len(exclusion_rows),
            },
        },
        "status_counts": status_counts(raw_rows, exclusion_rows),
        "identifier_coverage": {
            "successful_raw_rows": len(successful_observation_ids),
            "plan_rows": len(plan_observation_ids),
            "successful_observation_ids_are_unique": len(successful_observation_ids)
            == len(set(successful_observation_ids)),
            "plan_observation_ids_are_unique": len(plan_observation_ids)
            == len(set(plan_observation_ids)),
            "successful_observation_ids_match_plan_rows": set(
                successful_observation_ids
            )
            == set(plan_observation_ids),
        },
    }


def config_hash(config_path: str | None) -> str:
    """Return the SHA256 hash of the active config file."""
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    config_bytes = (ROOT_DIR / path).resolve().read_bytes()
    return hashlib.sha256(config_bytes).hexdigest()


def git_revision() -> str | None:
    """Return the current git revision when available."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def status_counts(
    raw_rows: list[dict[str, Any]], exclusion_rows: list[dict[str, Any]]
) -> dict[str, int]:
    """Aggregate row counts by status across raw attempts and exclusions."""
    counts: dict[str, int] = {}
    for row in raw_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    counts["excluded"] = len(exclusion_rows)
    return counts


def _select_scales(config: dict[str, Any], limit_scales: int | None) -> list[str]:
    scale_factors = experiment_scale_factors(config)
    if limit_scales is not None:
        return scale_factors[:limit_scales]
    return scale_factors


def _select_templates(limit_templates: int | None) -> list[str]:
    templates = list(TPCH_TEMPLATE_IDS)
    if limit_templates is not None:
        return templates[:limit_templates]
    return templates


def _raw_runs_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    schema = {
        "observation_id": pl.String,
        "run_attempt_id": pl.String,
        "query_instance_id": pl.String,
        "template_id": pl.String,
        "parameter_set_id": pl.String,
        "scale_factor": pl.Float64,
        "attempt_index": pl.Int64,
        "attempt_number": pl.Int64,
        "is_retry": pl.Boolean,
        "status": pl.String,
        "run_status": pl.String,
        "failure_reason": pl.String,
        "include_in_modeling": pl.Boolean,
        "is_excluded": pl.Boolean,
        "exclusion_stage": pl.String,
        "exclusion_reason": pl.String,
        "planner_total_cost": pl.Float64,
        "planning_time_ms": pl.Float64,
        "execution_time_ms": pl.Float64,
        "wall_clock_runtime_ms": pl.Float64,
        "row_count": pl.Int64,
        "sql_text": pl.String,
        "error_class": pl.String,
        "error_message": pl.String,
    }
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema, strict=False)


def _exclusions_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    schema = {
        "query_instance_id": pl.String,
        "template_id": pl.String,
        "parameter_set_id": pl.String,
        "scale_factor": pl.Float64,
        "status": pl.String,
        "run_status": pl.String,
        "failure_reason": pl.String,
        "attempt_number": pl.Int64,
        "attempt_index": pl.Int64,
        "is_retry": pl.Boolean,
        "include_in_modeling": pl.Boolean,
        "is_excluded": pl.Boolean,
        "exclusion_stage": pl.String,
        "exclusion_reason": pl.String,
        "planner_total_cost": pl.Float64,
        "planning_time_ms": pl.Float64,
        "execution_time_ms": pl.Float64,
        "wall_clock_runtime_ms": pl.Float64,
        "row_count": pl.Int64,
        "sql_text": pl.String,
        "error_class": pl.String,
        "error_message": pl.String,
    }
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema, strict=False)


def _write_plans(plan_rows: list[dict[str, Any]]) -> None:
    with PLANS_PATH.open("w", encoding="utf-8") as plan_file:
        for row in plan_rows:
            plan_file.write(json.dumps(row, sort_keys=True) + "\n")
