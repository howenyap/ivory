"""Collect-stage commands for PostgreSQL setup and raw collection."""

from __future__ import annotations

import argparse
from typing import Any

from ivory.collection import (
    DEFAULT_PARAMETER_SETS_PER_TEMPLATE,
    collect_raw_artifacts,
)
from ivory.config import experiment_scale_factors, load_config
from ivory.postgres import (
    TPCH_TABLES,
    expected_row_counts,
    generate_tpch_data,
    load_scale_factor_from_cache,
    project_postgres_config,
    prompt_for_cache_regeneration,
    reset_postgres,
    run_smoke_query,
    scale_factor_cache_status,
    scale_factor_directories,
    start_postgres,
    stop_postgres,
    table_counts,
    table_presence,
    validate_cache_for_reuse,
)

COLLECT_DB_COMMANDS = (
    "start-db",
    "stop-db",
    "reset-db",
    "load-db",
    "reload-db",
    "db-health",
    "db-row-counts",
    "db-smoke-query",
)


def register_collect_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the collect command tree."""
    collect_parser = subparsers.add_parser(
        "collect",
        help="Run raw collection or manage the PostgreSQL benchmark environment.",
        description="Project-managed raw collection plus PostgreSQL setup commands.",
    )
    collect_parser.add_argument(
        "--config",
        default=None,
        help="Path to a TOML experiment config. Defaults to configs/experiment.toml.",
    )
    collect_parser.add_argument(
        "--limit-templates",
        type=int,
        default=None,
        help="Limit collection to the first N TPC-H templates.",
    )
    collect_parser.add_argument(
        "--limit-params",
        type=int,
        default=None,
        help=(
            "Limit collection to the first N parameter sets per template. "
            f"Without this flag, full collection uses "
            f"{DEFAULT_PARAMETER_SETS_PER_TEMPLATE} parameter sets per template."
        ),
    )
    collect_parser.add_argument(
        "--limit-scales",
        type=int,
        default=None,
        help="Limit collection to the first N configured scale factors.",
    )
    collect_parser.add_argument(
        "--timeout-ms",
        type=int,
        default=None,
        help="Override the query statement timeout in milliseconds.",
    )
    collect_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previously interrupted collection run from checkpoint data.",
    )
    collect_parser.add_argument(
        "--scale-factor",
        dest="scale_factors",
        action="append",
        default=None,
        help=(
            "Collect only the specified configured scale factor. "
            "Repeat to collect multiple specific scale factors."
        ),
    )
    collect_parser.set_defaults(handler=_handle_collect)
    collect_subparsers = collect_parser.add_subparsers(
        dest="collect_command", metavar="collect-command"
    )

    for name, help_text, handler in (
        (
            "start-db",
            "Start the project-managed PostgreSQL container.",
            _handle_start_db,
        ),
        ("stop-db", "Stop the project-managed PostgreSQL container.", _handle_stop_db),
        ("reset-db", "Remove the local PostgreSQL container state.", _handle_reset_db),
        (
            "load-db",
            "Generate and load TPC-H data for every configured scale factor.",
            _handle_load_db,
        ),
        (
            "reload-db",
            "Reset PostgreSQL and reload every configured TPC-H scale factor.",
            _handle_reload_db,
        ),
        (
            "db-health",
            "Check connectivity and table presence for every configured database.",
            _handle_db_health,
        ),
        (
            "db-row-counts",
            "Print row counts for every loaded TPC-H table.",
            _handle_db_row_counts,
        ),
        (
            "db-smoke-query",
            "Run a simple join query against every configured database.",
            _handle_db_smoke_query,
        ),
    ):
        parser = collect_subparsers.add_parser(
            name, help=help_text, description=help_text
        )
        parser.add_argument(
            "--config",
            default=None,
            help=(
                "Path to a TOML experiment config. Defaults to configs/experiment.toml."
            ),
        )
        parser.set_defaults(handler=handler)


def _load_runtime(args: argparse.Namespace) -> tuple[dict[str, Any], Any]:
    config = load_config(args.config)
    settings = project_postgres_config(config)
    return config, settings


def _handle_collect(args: argparse.Namespace) -> int:
    config, settings = _load_runtime(args)
    if args.scale_factors is not None and args.limit_scales is not None:
        raise SystemExit(
            "Use either explicit scale factors or --limit-scales, not both."
        )
    try:
        manifest = collect_raw_artifacts(
            config,
            settings,
            config_path=args.config,
            limit_templates=args.limit_templates,
            limit_params=args.limit_params,
            limit_scales=args.limit_scales,
            requested_scales=args.scale_factors,
            timeout_ms=args.timeout_ms,
            resume=args.resume,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    raw_rows = manifest["artifacts"]["raw_runs"]["row_count"]
    plan_rows = manifest["artifacts"]["plans"]["row_count"]
    exclusion_rows = manifest["artifacts"]["exclusions"]["row_count"]
    print(
        "Collection complete: "
        f"raw_rows={raw_rows} plan_rows={plan_rows} exclusions={exclusion_rows}"
    )
    return 0


def _handle_start_db(args: argparse.Namespace) -> int:
    _, settings = _load_runtime(args)
    start_postgres(settings)
    print("PostgreSQL container is running.")
    return 0


def _handle_stop_db(args: argparse.Namespace) -> int:
    _, settings = _load_runtime(args)
    stop_postgres(settings)
    print("PostgreSQL container stopped.")
    return 0


def _handle_reset_db(args: argparse.Namespace) -> int:
    _, settings = _load_runtime(args)
    reset_postgres(settings)
    print("PostgreSQL container state removed.")
    return 0


def _handle_load_db(args: argparse.Namespace) -> int:
    config, settings = _load_runtime(args)
    start_postgres(settings)
    data_directories = scale_factor_directories(settings)
    for scale_factor in experiment_scale_factors(config):
        print(
            f"Loading scale factor {scale_factor} into "
            f"{settings.scale_factor_databases[scale_factor]} "
            f"from {data_directories[scale_factor]}"
        )
    for scale_factor in experiment_scale_factors(config):
        cache_status = scale_factor_cache_status(settings, scale_factor)
        if cache_status.has_any_tbl_files:
            should_regenerate = prompt_for_cache_regeneration(cache_status)
            if should_regenerate:
                data_dir = generate_tpch_data(settings, scale_factor)
            else:
                validate_cache_for_reuse(cache_status)
                data_dir = cache_status.directory
        else:
            data_dir = generate_tpch_data(settings, scale_factor)

        load_scale_factor_from_cache(settings, scale_factor, data_dir)
    print("All configured TPC-H scale factors were loaded successfully.")
    return 0


def _handle_reload_db(args: argparse.Namespace) -> int:
    config, settings = _load_runtime(args)
    reset_postgres(settings)
    start_postgres(settings)
    for scale_factor in experiment_scale_factors(config):
        print(
            f"Reloading scale factor {scale_factor} into "
            f"{settings.scale_factor_databases[scale_factor]} "
            f"from {scale_factor_directories(settings)[scale_factor]}"
        )
        data_dir = generate_tpch_data(settings, scale_factor)
        load_scale_factor_from_cache(settings, scale_factor, data_dir)
    print("All configured TPC-H scale factors were reloaded successfully.")
    return 0


def _handle_db_health(args: argparse.Namespace) -> int:
    config, settings = _load_runtime(args)
    missing_any = False
    for scale_factor in experiment_scale_factors(config):
        database = settings.scale_factor_databases[scale_factor]
        present_tables = table_presence(settings, database)
        missing_tables = [table for table in TPCH_TABLES if table not in present_tables]
        if missing_tables:
            missing_any = True
            print(
                f"{scale_factor} {database} missing tables: "
                + ", ".join(missing_tables)
            )
            continue
        print(f"{scale_factor} {database} healthy")
    return 1 if missing_any else 0


def _handle_db_row_counts(args: argparse.Namespace) -> int:
    config, settings = _load_runtime(args)
    failures = False
    for scale_factor in experiment_scale_factors(config):
        database = settings.scale_factor_databases[scale_factor]
        counts = table_counts(settings, database)
        expected_counts = expected_row_counts(scale_factor)
        if any(
            counts[table] != expected for table, expected in expected_counts.items()
        ):
            failures = True
        if counts["lineitem"] <= counts["orders"]:
            failures = True
        counts_text = ", ".join(f"{table}={counts[table]}" for table in TPCH_TABLES)
        print(f"{scale_factor} {database} {counts_text}")
    return 1 if failures else 0


def _handle_db_smoke_query(args: argparse.Namespace) -> int:
    config, settings = _load_runtime(args)
    failures = False
    for scale_factor in experiment_scale_factors(config):
        database = settings.scale_factor_databases[scale_factor]
        result = run_smoke_query(settings, database)
        if result.joined_rows <= 0:
            failures = True
        print(
            f"{scale_factor} {database} joined_rows={result.joined_rows} "
            f"revenue={result.revenue:.2f}"
        )
    return 1 if failures else 0
