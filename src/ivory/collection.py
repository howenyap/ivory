"""Query generation and raw collection helpers for phase 1b."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
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
MANIFEST_PATH = RAW_ARTIFACT_DIR / "collection_manifest.json"
TPCH_TEMPLATE_IDS = tuple(f"q{query_id}" for query_id in range(1, 23))
DEFAULT_PARAMETER_SETS_PER_TEMPLATE = 50
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
LOG_COLORS = {
    "info": "\033[36m",
    "success": "\033[32m",
    "warning": "\033[33m",
    "error": "\033[31m",
}
LOG_RESET = "\033[0m"


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


@dataclass(frozen=True)
class QueryKey:
    template_id: str
    template_number: int
    parameter_set_id: str
    query_instance_id: str
    scale_factor: str
    parameter_index: int
    qgen_seed: int


@dataclass(frozen=True)
class ScaleArtifactPaths:
    scale_factor: str
    scale_dir: Path
    raw_runs_path: Path
    plans_path: Path
    exclusions_path: Path
    manifest_path: Path
    raw_runs_checkpoint_path: Path
    plans_checkpoint_path: Path
    exclusions_checkpoint_path: Path
    state_path: Path


def log_progress(message: str, *, level: str = "info") -> None:
    """Print a flushed progress line for long-running collection work."""
    prefix = f"[{level.upper()}]"
    if _supports_color():
        color = LOG_COLORS.get(level, "")
        prefix = f"{color}{prefix}{LOG_RESET}"
    print(f"{prefix} {message}", flush=True)


def _supports_color() -> bool:
    """Return whether stdout likely supports ANSI color output."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def format_progress(current: int, total: int) -> str:
    """Format a compact progress counter with percent complete."""
    return f"{current}/{total} ({(current / total) * 100:5.1f}%)"


def format_query_label(
    *,
    template_id: str,
    scale_factor: str,
    parameter_index: int,
    parameter_count: int,
) -> str:
    """Format a compact query-instance label for logging."""
    return (
        f"{template_id} sf={scale_factor} param={parameter_index + 1}/{parameter_count}"
    )


def scale_factor_directory_name(scale_factor: str) -> str:
    """Return the stable raw-artifact directory name for one scale factor."""
    return f"sf_{scale_factor.replace('.', '_')}"


def scale_artifact_paths(scale_factor: str) -> ScaleArtifactPaths:
    """Return the raw artifact paths for one scale factor."""
    scale_dir = RAW_ARTIFACT_DIR / scale_factor_directory_name(scale_factor)
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


def collect_raw_artifacts(
    config: dict[str, Any],
    settings: PostgresConfig,
    *,
    config_path: str | None = None,
    limit_templates: int | None = None,
    limit_params: int | None = None,
    limit_scales: int | None = None,
    requested_scales: list[str] | None = None,
    timeout_ms: int | None = None,
    params_per_template: int = DEFAULT_PARAMETER_SETS_PER_TEMPLATE,
    resume: bool = False,
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

    selected_scales = _select_scales(config, limit_scales, requested_scales)
    selected_templates = _select_templates(limit_templates)
    parameter_count = limit_params if limit_params is not None else params_per_template
    RAW_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    total_query_instances = (
        len(selected_scales) * len(selected_templates) * parameter_count
    )
    total_runs = total_query_instances * runs_per_query
    scale_total_runs = len(selected_templates) * parameter_count * runs_per_query
    log_progress(
        "collection start | "
        f"scales={len(selected_scales)} templates={len(selected_templates)} "
        f"params={parameter_count} runs={runs_per_query} "
        f"instances={total_query_instances} logical_runs={total_runs} "
        f"resume={'yes' if resume else 'no'} timeout_ms={effective_timeout_ms}",
        level="info",
    )
    if not resume:
        if requested_scales is None and limit_scales is None:
            cleanup_all_scale_artifact_dirs()
        cleanup_aggregate_manifest()

    completed_runs_total = 0
    scale_manifests: list[dict[str, Any]] = []
    for scale_factor in selected_scales:
        artifact_paths = scale_artifact_paths(scale_factor)
        state = build_collection_state(
            config=config,
            config_path=config_path,
            selected_scales=[scale_factor],
            selected_templates=selected_templates,
            timeout_ms=effective_timeout_ms,
            retry_count=retry_count,
            params_per_template=parameter_count,
        )
        if resume and artifact_paths.state_path.exists():
            validate_resume_state(state, artifact_paths)
            raw_rows, plan_rows, exclusion_rows = load_checkpoint_rows(artifact_paths)
        elif resume and artifact_paths.manifest_path.exists():
            validate_materialized_manifest(state, artifact_paths)
            raw_rows, plan_rows, exclusion_rows = load_materialized_rows(artifact_paths)
        elif (
            not resume
            and artifact_paths.manifest_path.exists()
            and materialized_manifest_matches_state(state, artifact_paths)
        ):
            raw_rows, plan_rows, exclusion_rows = load_materialized_rows(artifact_paths)
            completed_run_ids = terminal_run_ids(raw_rows, plan_rows, exclusion_rows)
            completed_runs_total += len(completed_run_ids)
            log_progress(
                f"already collected | sf={scale_factor}",
                level="success",
            )
            scale_manifests.append(json.loads(artifact_paths.manifest_path.read_text()))
            continue
        else:
            initialize_collection_state(state, artifact_paths)
            raw_rows = []
            plan_rows = []
            exclusion_rows = []

        existing_attempts_by_run = group_attempt_rows_by_run(raw_rows)
        completed_run_ids = terminal_run_ids(raw_rows, plan_rows, exclusion_rows)
        completed_runs_total += len(completed_run_ids)
        if completed_run_ids:
            completed_scale_progress = format_progress(
                len(completed_run_ids), scale_total_runs
            )
            log_progress(
                "resume state | "
                f"scale={scale_factor} "
                f"completed={completed_scale_progress}",
                level="warning",
            )
        if len(completed_run_ids) == scale_total_runs:
            log_progress(
                f"scale complete | sf={scale_factor}",
                level="success",
            )
            scale_manifests.append(
                build_collection_manifest(
                    config=config,
                    config_path=config_path,
                    selected_scales=[scale_factor],
                    selected_templates=selected_templates,
                    timeout_ms=effective_timeout_ms,
                    retry_count=retry_count,
                    params_per_template=parameter_count,
                    raw_rows=raw_rows,
                    plan_rows=plan_rows,
                    exclusion_rows=exclusion_rows,
                    artifact_paths=artifact_paths,
                )
            )
            continue

        log_progress(f"scale start | sf={scale_factor}", level="info")
        for template_id in selected_templates:
            for parameter_index in range(parameter_count):
                query_key = build_query_key(
                    template_id=template_id,
                    scale_factor=scale_factor,
                    parameter_index=parameter_index,
                    seed=seed,
                )
                query_instance_completed_runs = sum(
                    1
                    for run_index in range(runs_per_query)
                    if build_run_id(query_key.query_instance_id, run_index)
                    in completed_run_ids
                )
                if query_instance_completed_runs == runs_per_query:
                    query_label = format_query_label(
                        template_id=template_id,
                        scale_factor=scale_factor,
                        parameter_index=parameter_index,
                        parameter_count=parameter_count,
                    )
                    log_progress(
                        "skip instance | "
                        f"{query_label} | "
                        "completed="
                        f"{format_progress(completed_runs_total, total_runs)}",
                        level="warning",
                    )
                    continue
                query_label = format_query_label(
                    template_id=template_id,
                    scale_factor=scale_factor,
                    parameter_index=parameter_index,
                    parameter_count=parameter_count,
                )
                log_progress(
                    f"instance | {query_label}",
                    level="info",
                )
                try:
                    query_instance = build_query_instance(
                        settings=settings,
                        query_key=query_key,
                    )
                except Exception as exc:
                    log_progress(
                        f"qgen failed | {query_label} | {type(exc).__name__}: {exc}",
                        level="error",
                    )
                    for run_index in range(runs_per_query):
                        run_id = build_run_id(query_key.query_instance_id, run_index)
                        if run_id in completed_run_ids:
                            continue
                        existing_attempt_rows = existing_attempts_by_run.get(run_id, [])
                        failure_rows, exclusion_row = record_generation_failure(
                            query_key=query_key,
                            run_index=run_index,
                            error=exc,
                            retry_count=retry_count,
                            existing_attempt_rows=existing_attempt_rows,
                        )
                        if failure_rows:
                            raw_rows.extend(failure_rows)
                            append_jsonl_rows(
                                artifact_paths.raw_runs_checkpoint_path,
                                failure_rows,
                            )
                            existing_attempts_by_run[run_id] = (
                                existing_attempt_rows + failure_rows
                            )
                        if exclusion_row is not None:
                            exclusion_rows.append(exclusion_row)
                            append_jsonl_rows(
                                artifact_paths.exclusions_checkpoint_path,
                                [exclusion_row],
                            )
                            completed_run_ids.add(run_id)
                            completed_runs_total += 1
                            completed_progress = format_progress(
                                completed_runs_total, total_runs
                            )
                            log_progress(
                                "excluded | "
                                f"{query_key.template_id} sf={query_key.scale_factor} "
                                "param="
                                f"{query_key.parameter_index + 1}/{parameter_count} "
                                f"run={run_index + 1}/{runs_per_query} "
                                f"| completed={completed_progress}",
                                level="error",
                            )
                        materialize_collection_artifacts(
                            config=config,
                            config_path=config_path,
                            selected_scales=[scale_factor],
                            selected_templates=selected_templates,
                            timeout_ms=effective_timeout_ms,
                            retry_count=retry_count,
                            params_per_template=parameter_count,
                            raw_rows=raw_rows,
                            plan_rows=plan_rows,
                            exclusion_rows=exclusion_rows,
                            artifact_paths=artifact_paths,
                        )
                    continue
                for run_index in range(runs_per_query):
                    run_id = build_run_id(query_instance.query_instance_id, run_index)
                    if run_id in completed_run_ids:
                        continue
                    log_progress(
                        "run | "
                        f"{format_progress(completed_runs_total + 1, total_runs)} "
                        f"| {template_id} sf={scale_factor} "
                        f"param={parameter_index + 1}/{parameter_count} "
                        f"run={run_index + 1}/{runs_per_query}",
                        level="info",
                    )
                    attempts = collect_query_attempts(
                        settings=settings,
                        query_instance=query_instance,
                        run_index=run_index,
                        retry_count=retry_count,
                        timeout_ms=effective_timeout_ms,
                        existing_attempt_rows=existing_attempts_by_run.get(run_id, []),
                    )
                    new_raw_rows = attempts["raw_rows"]
                    new_plan_rows = attempts["plan_rows"]
                    if new_raw_rows:
                        raw_rows.extend(new_raw_rows)
                        append_jsonl_rows(
                            artifact_paths.raw_runs_checkpoint_path,
                            new_raw_rows,
                        )
                        existing_attempts_by_run[run_id] = (
                            existing_attempts_by_run.get(run_id, []) + new_raw_rows
                        )
                    if new_plan_rows:
                        plan_rows.extend(new_plan_rows)
                        append_jsonl_rows(
                            artifact_paths.plans_checkpoint_path,
                            new_plan_rows,
                        )
                    if attempts["exclusion_row"] is not None:
                        exclusion_row = attempts["exclusion_row"]
                        exclusion_rows.append(exclusion_row)
                        append_jsonl_rows(
                            artifact_paths.exclusions_checkpoint_path,
                            [exclusion_row],
                        )
                        completed_run_ids.add(run_id)
                        completed_runs_total += 1
                        completed_progress = format_progress(
                            completed_runs_total, total_runs
                        )
                        log_progress(
                            "excluded | "
                            f"{template_id} sf={scale_factor} "
                            f"param={parameter_index + 1}/{parameter_count} "
                            f"run={run_index + 1}/{runs_per_query} "
                            f"| reason={exclusion_row['failure_reason']} "
                            f"| completed={completed_progress}",
                            level="error",
                        )
                    elif new_plan_rows:
                        completed_run_ids.add(run_id)
                        completed_runs_total += 1
                        execution_row = new_raw_rows[-1]
                        completed_progress = format_progress(
                            completed_runs_total, total_runs
                        )
                        log_progress(
                            "ok | "
                            f"{template_id} sf={scale_factor} "
                            f"param={parameter_index + 1}/{parameter_count} "
                            f"run={run_index + 1}/{runs_per_query} "
                            f"| exec_ms={execution_row['execution_time_ms']:.3f} "
                            f"| completed={completed_progress}",
                            level="success",
                        )
                    materialize_collection_artifacts(
                        config=config,
                        config_path=config_path,
                        selected_scales=[scale_factor],
                        selected_templates=selected_templates,
                        timeout_ms=effective_timeout_ms,
                        retry_count=retry_count,
                        params_per_template=parameter_count,
                        raw_rows=raw_rows,
                        plan_rows=plan_rows,
                        exclusion_rows=exclusion_rows,
                        artifact_paths=artifact_paths,
                    )
        scale_manifest = materialize_collection_artifacts(
            config=config,
            config_path=config_path,
            selected_scales=[scale_factor],
            selected_templates=selected_templates,
            timeout_ms=effective_timeout_ms,
            retry_count=retry_count,
            params_per_template=parameter_count,
            raw_rows=raw_rows,
            plan_rows=plan_rows,
            exclusion_rows=exclusion_rows,
            artifact_paths=artifact_paths,
        )
        cleanup_checkpoint_files(artifact_paths)
        scale_manifests.append(scale_manifest)

    compatible_scale_manifests = load_compatible_scale_manifests(
        config=config,
        config_path=config_path,
        selected_templates=selected_templates,
        timeout_ms=effective_timeout_ms,
        retry_count=retry_count,
        params_per_template=parameter_count,
    )
    manifest = build_aggregate_collection_manifest(
        config=config,
        config_path=config_path,
        selected_scales=[
            manifest["scale_factors_included"][0]
            for manifest in compatible_scale_manifests
        ],
        selected_templates=selected_templates,
        timeout_ms=effective_timeout_ms,
        retry_count=retry_count,
        params_per_template=parameter_count,
        scale_manifests=compatible_scale_manifests,
    )
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    log_progress(
        "collection finished | "
        f"completed={format_progress(completed_runs_total, total_runs)}",
        level="success",
    )
    return manifest


def collect_query_attempts(
    *,
    settings: PostgresConfig,
    query_instance: QueryInstance,
    run_index: int,
    retry_count: int,
    timeout_ms: int,
    existing_attempt_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Collect all attempts for one observation run."""
    raw_rows: list[dict[str, Any]] = []
    plan_rows: list[dict[str, Any]] = []
    exclusion_row: dict[str, Any] | None = None
    max_attempts = retry_count + 1
    existing_attempt_rows = existing_attempt_rows or []
    final_attempt: dict[str, Any] | None = (
        existing_attempt_rows[-1] if existing_attempt_rows else None
    )

    if existing_attempt_rows and len(existing_attempt_rows) >= max_attempts:
        assert final_attempt is not None
        exclusion_row = build_exclusion_row(final_attempt)
        return {
            "raw_rows": raw_rows,
            "plan_rows": plan_rows,
            "exclusion_row": exclusion_row,
        }

    for attempt_number in range(len(existing_attempt_rows) + 1, max_attempts + 1):
        if attempt_number > 1:
            log_progress(
                "retry | "
                f"{query_instance.template_id} sf={query_instance.scale_factor} "
                f"param={query_instance.parameter_index + 1} "
                f"run={run_index + 1} "
                f"attempt={attempt_number}/{max_attempts}",
                level="warning",
            )
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
        if execution.status != "success":
            log_progress(
                "attempt failed | "
                f"{query_instance.template_id} sf={query_instance.scale_factor} "
                f"param={query_instance.parameter_index + 1} "
                f"run={run_index + 1} "
                f"attempt={attempt_number}/{max_attempts} "
                f"| status={execution.status} "
                f"| reason={execution.failure_reason or 'unknown'}",
                level="error" if execution.status == "failed" else "warning",
            )
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


def build_query_key(
    *,
    template_id: str,
    scale_factor: str,
    parameter_index: int,
    seed: int,
) -> QueryKey:
    """Build deterministic query identifiers before SQL generation."""
    template_number = template_id_to_number(template_id)
    qgen_seed = parameter_seed(seed, template_number, parameter_index)
    parameter_set_id = f"{template_id}-p{parameter_index:04d}"
    query_instance_id = f"{template_id}-{parameter_set_id}-sf-{scale_factor}"
    return QueryKey(
        template_id=template_id,
        template_number=template_number,
        parameter_set_id=parameter_set_id,
        query_instance_id=query_instance_id,
        scale_factor=scale_factor,
        parameter_index=parameter_index,
        qgen_seed=qgen_seed,
    )


def build_query_instance(
    *,
    settings: PostgresConfig,
    query_key: QueryKey,
) -> QueryInstance:
    """Build a deterministic query instance for one template and scale factor."""
    raw_sql = generate_tpch_query_sql(
        settings=settings,
        template_number=query_key.template_number,
        scale_factor=query_key.scale_factor,
        qgen_seed=query_key.qgen_seed,
    )
    sql_text = normalize_qgen_sql(raw_sql, query_key.template_number)
    return QueryInstance(
        template_id=query_key.template_id,
        parameter_set_id=query_key.parameter_set_id,
        query_instance_id=query_key.query_instance_id,
        scale_factor=query_key.scale_factor,
        parameter_index=query_key.parameter_index,
        qgen_seed=query_key.qgen_seed,
        sql_text=sql_text,
    )


def template_id_to_number(template_id: str) -> int:
    """Return the numeric query id for a `qN` template id."""
    return int(template_id.removeprefix("q"))


def parameter_seed(base_seed: int, template_number: int, parameter_index: int) -> int:
    """Derive a deterministic qgen seed for one parameter set."""
    return base_seed + (template_number * 10000) + parameter_index


def build_run_id(query_instance_id: str, run_index: int) -> str:
    """Build the stable identifier for a logical run before retries."""
    return f"{query_instance_id}-run-{run_index + 1:02d}"


def run_id_from_attempt_row(row: dict[str, Any]) -> str:
    """Return the logical run id for a raw attempt or exclusion row."""
    run_id = row.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id
    run_attempt_id = str(row["run_attempt_id"])
    return run_attempt_id.rsplit("-attempt-", 1)[0]


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
    run_number = run_index + 1
    run_id = build_run_id(query_instance.query_instance_id, run_index)
    run_attempt_id = f"{run_id}-attempt-{attempt_number:02d}"
    return {
        "observation_id": run_attempt_id,
        "run_attempt_id": run_attempt_id,
        "run_id": run_id,
        "run_number": run_number,
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
                "run_id",
                "run_number",
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


def build_generation_failure_row(
    *,
    query_key: QueryKey,
    run_index: int,
    attempt_number: int,
    error: Exception,
) -> dict[str, Any]:
    """Build a failed raw row for query generation failures."""
    run_number = run_index + 1
    run_id = build_run_id(query_key.query_instance_id, run_index)
    run_attempt_id = f"{run_id}-attempt-{attempt_number:02d}"
    return {
        "observation_id": run_attempt_id,
        "run_attempt_id": run_attempt_id,
        "run_id": run_id,
        "run_number": run_number,
        "query_instance_id": query_key.query_instance_id,
        "template_id": query_key.template_id,
        "parameter_set_id": query_key.parameter_set_id,
        "scale_factor": float(query_key.scale_factor),
        "attempt_index": attempt_number - 1,
        "attempt_number": attempt_number,
        "is_retry": attempt_number > 1,
        "status": "failed",
        "run_status": STATUS_TO_RUN_STATUS["failed"],
        "failure_reason": "query_generation_failed",
        "include_in_modeling": False,
        "is_excluded": False,
        "exclusion_stage": None,
        "exclusion_reason": None,
        "planner_total_cost": None,
        "planning_time_ms": None,
        "execution_time_ms": None,
        "wall_clock_runtime_ms": 0.0,
        "row_count": None,
        "sql_text": "",
        "error_class": error.__class__.__name__,
        "error_message": str(error),
    }


def record_generation_failure(
    *,
    query_key: QueryKey,
    run_index: int,
    error: Exception,
    retry_count: int,
    existing_attempt_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Record one terminal exclusion for query generation failure."""
    max_attempts = retry_count + 1
    if existing_attempt_rows and len(existing_attempt_rows) >= max_attempts:
        return [], build_exclusion_row(existing_attempt_rows[-1])

    new_attempt_rows = [
        build_generation_failure_row(
            query_key=query_key,
            run_index=run_index,
            attempt_number=attempt_number,
            error=error,
        )
        for attempt_number in range(len(existing_attempt_rows) + 1, max_attempts + 1)
    ]
    exclusion_row = (
        build_exclusion_row(new_attempt_rows[-1]) if new_attempt_rows else None
    )
    return new_attempt_rows, exclusion_row


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
    artifact_paths: ScaleArtifactPaths,
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
                "path": str(artifact_paths.raw_runs_path.relative_to(ROOT_DIR)),
                "row_count": len(raw_rows),
            },
            "plans": {
                "path": str(artifact_paths.plans_path.relative_to(ROOT_DIR)),
                "row_count": len(plan_rows),
            },
            "exclusions": {
                "path": str(artifact_paths.exclusions_path.relative_to(ROOT_DIR)),
                "row_count": len(exclusion_rows),
            },
            "collection_manifest": {
                "path": str(artifact_paths.manifest_path.relative_to(ROOT_DIR)),
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


def build_aggregate_collection_manifest(
    *,
    config: dict[str, Any],
    config_path: str | None,
    selected_scales: list[str],
    selected_templates: list[str],
    timeout_ms: int,
    retry_count: int,
    params_per_template: int,
    scale_manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the top-level manifest that indexes all per-scale raw artifacts."""
    successful_raw_rows = sum(
        manifest["identifier_coverage"]["successful_raw_rows"]
        for manifest in scale_manifests
    )
    plan_rows = sum(
        manifest["identifier_coverage"]["plan_rows"] for manifest in scale_manifests
    )
    raw_row_count = sum(
        manifest["artifacts"]["raw_runs"]["row_count"] for manifest in scale_manifests
    )
    exclusion_row_count = sum(
        manifest["artifacts"]["exclusions"]["row_count"] for manifest in scale_manifests
    )
    status_totals: dict[str, int] = {}
    for manifest in scale_manifests:
        for status, count in manifest["status_counts"].items():
            status_totals[status] = status_totals.get(status, 0) + int(count)
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
            "raw_runs": {"row_count": raw_row_count},
            "plans": {"row_count": plan_rows},
            "exclusions": {"row_count": exclusion_row_count},
            "collection_manifest": {"path": str(MANIFEST_PATH.relative_to(ROOT_DIR))},
        },
        "scale_factor_artifacts": {
            manifest["scale_factors_included"][0]: manifest["artifacts"]
            for manifest in scale_manifests
        },
        "status_counts": status_totals,
        "identifier_coverage": {
            "successful_raw_rows": successful_raw_rows,
            "plan_rows": plan_rows,
            "successful_observation_ids_are_unique": all(
                manifest["identifier_coverage"]["successful_observation_ids_are_unique"]
                for manifest in scale_manifests
            ),
            "plan_observation_ids_are_unique": all(
                manifest["identifier_coverage"]["plan_observation_ids_are_unique"]
                for manifest in scale_manifests
            ),
            "successful_observation_ids_match_plan_rows": all(
                manifest["identifier_coverage"][
                    "successful_observation_ids_match_plan_rows"
                ]
                for manifest in scale_manifests
            ),
        },
    }


def build_collection_state(
    *,
    config: dict[str, Any],
    config_path: str | None,
    selected_scales: list[str],
    selected_templates: list[str],
    timeout_ms: int,
    retry_count: int,
    params_per_template: int,
) -> dict[str, Any]:
    """Build resume metadata for one collection run."""
    return {
        "config_path": str((ROOT_DIR / (config_path or DEFAULT_CONFIG_PATH)).resolve()),
        "config_hash_sha256": config_hash(config_path),
        "scale_factors_included": selected_scales,
        "templates_included": selected_templates,
        "timeout_ms": timeout_ms,
        "retry_count": retry_count,
        "runs_per_query": int(config["experiment"]["runs_per_query"]),
        "parameter_sets_per_template": params_per_template,
    }


def validate_resume_state(
    expected_state: dict[str, Any], artifact_paths: ScaleArtifactPaths
) -> None:
    """Validate that checkpoint state matches the requested resume configuration."""
    if not artifact_paths.state_path.exists():
        raise FileNotFoundError(
            "Cannot resume collection: missing checkpoint state file "
            f"{artifact_paths.state_path}."
        )
    actual_state = json.loads(artifact_paths.state_path.read_text())
    if actual_state != expected_state:
        raise ValueError(
            "Cannot resume collection with different settings. "
            "Checkpoint state does not match the requested config, limits, or timeout."
        )


def initialize_collection_state(
    state: dict[str, Any], artifact_paths: ScaleArtifactPaths
) -> None:
    """Start a fresh collection run by resetting checkpoint files."""
    cleanup_checkpoint_files(artifact_paths)
    cleanup_materialized_artifacts(artifact_paths)
    artifact_paths.scale_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths.state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n"
    )


def cleanup_checkpoint_files(artifact_paths: ScaleArtifactPaths) -> None:
    """Remove checkpoint files after a successful collection run."""
    for path in (
        artifact_paths.raw_runs_checkpoint_path,
        artifact_paths.plans_checkpoint_path,
        artifact_paths.exclusions_checkpoint_path,
        artifact_paths.state_path,
    ):
        path.unlink(missing_ok=True)


def cleanup_materialized_artifacts(artifact_paths: ScaleArtifactPaths) -> None:
    """Remove visible raw artifacts before starting a fresh collection run."""
    for path in (
        artifact_paths.raw_runs_path,
        artifact_paths.plans_path,
        artifact_paths.exclusions_path,
        artifact_paths.manifest_path,
    ):
        path.unlink(missing_ok=True)


def cleanup_aggregate_manifest() -> None:
    """Remove the top-level aggregate manifest before a fresh run."""
    MANIFEST_PATH.unlink(missing_ok=True)


def cleanup_all_scale_artifact_dirs() -> None:
    """Remove every per-scale raw artifact directory before a fresh run."""
    for scale_dir in RAW_ARTIFACT_DIR.glob("sf_*"):
        if not scale_dir.is_dir():
            continue
        for path in scale_dir.iterdir():
            path.unlink(missing_ok=True)
        scale_dir.rmdir()


def config_hash(config_path: str | None) -> str:
    """Return the SHA256 hash of the active config file."""
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    config_bytes = (ROOT_DIR / path).resolve().read_bytes()
    return hashlib.sha256(config_bytes).hexdigest()


def load_checkpoint_rows(
    artifact_paths: ScaleArtifactPaths,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load checkpointed raw, plan, and exclusion rows."""
    raw_rows = load_jsonl_rows(artifact_paths.raw_runs_checkpoint_path)
    plan_rows = load_jsonl_rows(artifact_paths.plans_checkpoint_path)
    exclusion_rows = load_jsonl_rows(artifact_paths.exclusions_checkpoint_path)
    raw_rows, plan_rows = reconcile_checkpoint_rows(raw_rows, plan_rows, exclusion_rows)
    return raw_rows, plan_rows, exclusion_rows


def load_materialized_rows(
    artifact_paths: ScaleArtifactPaths,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load already-materialized rows for a completed per-scale collection."""
    raw_rows = (
        pl.read_parquet(artifact_paths.raw_runs_path).to_dicts()
        if artifact_paths.raw_runs_path.exists()
        else []
    )
    plan_rows = load_jsonl_rows(artifact_paths.plans_path)
    exclusion_rows = (
        pl.read_parquet(artifact_paths.exclusions_path).to_dicts()
        if artifact_paths.exclusions_path.exists()
        else []
    )
    return raw_rows, plan_rows, exclusion_rows


def validate_materialized_manifest(
    expected_state: dict[str, Any], artifact_paths: ScaleArtifactPaths
) -> None:
    """Validate that completed per-scale artifacts match the requested settings."""
    if not artifact_paths.manifest_path.exists():
        raise FileNotFoundError(
            "Cannot resume collection: missing per-scale manifest "
            f"{artifact_paths.manifest_path}."
        )
    manifest = json.loads(artifact_paths.manifest_path.read_text())
    actual_state = {
        "config_path": manifest["config_path"],
        "config_hash_sha256": manifest["config_hash_sha256"],
        "scale_factors_included": manifest["scale_factors_included"],
        "templates_included": manifest["templates_included"],
        "timeout_ms": manifest["timeout_ms"],
        "retry_count": manifest["retry_count"],
        "runs_per_query": manifest["runs_per_query"],
        "parameter_sets_per_template": manifest["parameter_sets_per_template"],
    }
    if actual_state != expected_state:
        raise ValueError(
            "Cannot resume collection with different settings. "
            "Materialized scale artifacts do not match the requested config, "
            "limits, or timeout."
        )
    required_paths = (
        artifact_paths.raw_runs_path,
        artifact_paths.plans_path,
        artifact_paths.exclusions_path,
    )
    missing_paths = [str(path) for path in required_paths if not path.exists()]
    if missing_paths:
        raise ValueError(
            "Cannot resume collection: materialized scale artifacts are incomplete. "
            f"Missing files: {', '.join(missing_paths)}."
        )

    raw_rows, plan_rows, exclusion_rows = load_materialized_rows(artifact_paths)
    if len(raw_rows) != int(manifest["artifacts"]["raw_runs"]["row_count"]):
        raise ValueError(
            "Cannot resume collection: materialized raw row count does not match "
            "the per-scale manifest."
        )
    if len(plan_rows) != int(manifest["artifacts"]["plans"]["row_count"]):
        raise ValueError(
            "Cannot resume collection: materialized plan row count does not match "
            "the per-scale manifest."
        )
    if len(exclusion_rows) != int(manifest["artifacts"]["exclusions"]["row_count"]):
        raise ValueError(
            "Cannot resume collection: materialized exclusion row count does not "
            "match the per-scale manifest."
        )
    successful_observation_ids = {
        row["observation_id"] for row in raw_rows if row["status"] == "success"
    }
    plan_observation_ids = {row["observation_id"] for row in plan_rows}
    if successful_observation_ids != plan_observation_ids:
        raise ValueError(
            "Cannot resume collection: materialized successful observations do not "
            "match materialized plan rows."
        )


def materialized_manifest_matches_state(
    expected_state: dict[str, Any], artifact_paths: ScaleArtifactPaths
) -> bool:
    """Return whether a completed per-scale manifest matches the requested settings."""
    try:
        validate_materialized_manifest(expected_state, artifact_paths)
    except FileNotFoundError, ValueError:
        return False
    return True


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    """Load JSONL rows from a checkpoint file when it exists."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def append_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Append checkpoint rows to a JSONL file."""
    if not rows:
        return
    with path.open("a", encoding="utf-8") as output_file:
        for row in rows:
            output_file.write(json.dumps(row, sort_keys=True) + "\n")


def reconcile_checkpoint_rows(
    raw_rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    exclusion_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop checkpoint rows that cannot form a consistent resumable state."""
    exclusion_run_ids = {run_id_from_attempt_row(row) for row in exclusion_rows}
    valid_raw_rows = [
        row for row in raw_rows if run_id_from_attempt_row(row) not in exclusion_run_ids
    ]

    success_observation_ids = {
        row["observation_id"] for row in valid_raw_rows if row["status"] == "success"
    }
    valid_plan_rows = [
        row for row in plan_rows if row["observation_id"] in success_observation_ids
    ]
    valid_plan_observation_ids = {row["observation_id"] for row in valid_plan_rows}
    reconciled_raw_rows = [
        row
        for row in valid_raw_rows
        if row["status"] != "success"
        or row["observation_id"] in valid_plan_observation_ids
    ]
    return reconciled_raw_rows, valid_plan_rows


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


def group_attempt_rows_by_run(
    raw_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group checkpointed attempt rows by logical run id."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in raw_rows:
        run_id = run_id_from_attempt_row(row)
        grouped.setdefault(run_id, []).append(row)
    for run_rows in grouped.values():
        run_rows.sort(key=lambda row: int(row["attempt_number"]))
    return grouped


def terminal_run_ids(
    raw_rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    exclusion_rows: list[dict[str, Any]],
) -> set[str]:
    """Return run ids that already reached a terminal success or exclusion state."""
    plan_observation_ids = {row["observation_id"] for row in plan_rows}
    run_ids = {
        run_id_from_attempt_row(row)
        for row in raw_rows
        if row["status"] == "success" and row["observation_id"] in plan_observation_ids
    }
    run_ids.update(run_id_from_attempt_row(row) for row in exclusion_rows)
    return run_ids


def status_counts(
    raw_rows: list[dict[str, Any]], exclusion_rows: list[dict[str, Any]]
) -> dict[str, int]:
    """Aggregate row counts by status across raw attempts and exclusions."""
    counts: dict[str, int] = {}
    for row in raw_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    counts["excluded"] = len(exclusion_rows)
    return counts


def _select_scales(
    config: dict[str, Any],
    limit_scales: int | None,
    requested_scales: list[str] | None = None,
) -> list[str]:
    scale_factors = experiment_scale_factors(config)
    if requested_scales is not None:
        invalid_scales = [
            scale_factor
            for scale_factor in requested_scales
            if scale_factor not in scale_factors
        ]
        if invalid_scales:
            configured = ", ".join(scale_factors)
            invalid = ", ".join(invalid_scales)
            raise ValueError(
                "Unconfigured scale factor(s): "
                f"{invalid}. Configured scale factors: {configured}."
            )
        return requested_scales
    if limit_scales is not None:
        return scale_factors[:limit_scales]
    return scale_factors


def load_compatible_scale_manifests(
    *,
    config: dict[str, Any],
    config_path: str | None,
    selected_templates: list[str],
    timeout_ms: int,
    retry_count: int,
    params_per_template: int,
) -> list[dict[str, Any]]:
    """Load per-scale manifests that match the active collection settings."""
    manifests: list[dict[str, Any]] = []
    for scale_factor in experiment_scale_factors(config):
        artifact_paths = scale_artifact_paths(scale_factor)
        if not artifact_paths.manifest_path.exists():
            continue
        expected_state = build_collection_state(
            config=config,
            config_path=config_path,
            selected_scales=[scale_factor],
            selected_templates=selected_templates,
            timeout_ms=timeout_ms,
            retry_count=retry_count,
            params_per_template=params_per_template,
        )
        if materialized_manifest_matches_state(expected_state, artifact_paths):
            manifests.append(json.loads(artifact_paths.manifest_path.read_text()))
    return manifests


def _select_templates(limit_templates: int | None) -> list[str]:
    templates = list(TPCH_TEMPLATE_IDS)
    if limit_templates is not None:
        return templates[:limit_templates]
    return templates


def materialize_collection_artifacts(
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
    artifact_paths: ScaleArtifactPaths,
) -> dict[str, Any]:
    """Write parquet/json artifacts and the manifest from in-memory rows."""
    artifact_paths.scale_dir.mkdir(parents=True, exist_ok=True)
    raw_frame = _raw_runs_frame(raw_rows)
    exclusion_frame = _exclusions_frame(exclusion_rows)
    raw_frame.write_parquet(artifact_paths.raw_runs_path)
    exclusion_frame.write_parquet(artifact_paths.exclusions_path)
    _write_plans(plan_rows, artifact_paths.plans_path)
    manifest = build_collection_manifest(
        config=config,
        config_path=config_path,
        selected_scales=selected_scales,
        selected_templates=selected_templates,
        timeout_ms=timeout_ms,
        retry_count=retry_count,
        params_per_template=params_per_template,
        raw_rows=raw_rows,
        plan_rows=plan_rows,
        exclusion_rows=exclusion_rows,
        artifact_paths=artifact_paths,
    )
    artifact_paths.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _raw_runs_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    schema = {
        "observation_id": pl.String,
        "run_attempt_id": pl.String,
        "run_id": pl.String,
        "run_number": pl.Int64,
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
        "run_id": pl.String,
        "run_number": pl.Int64,
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


def _write_plans(plan_rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as plan_file:
        for row in plan_rows:
            plan_file.write(json.dumps(row, sort_keys=True) + "\n")
