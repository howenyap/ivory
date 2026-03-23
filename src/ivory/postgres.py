"""PostgreSQL and TPC-H environment management helpers."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from psycopg import connect, sql
from psycopg.rows import dict_row

from ivory.config import (
    PostgresConfig,
    experiment_scale_factors,
    normalize_scale_factor_key,
    postgres_config,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT_DIR / "sql"
POSTGRES_CONTAINER_DATA_ROOT = Path("/tpch-data")
TPCH_TABLES = (
    "region",
    "nation",
    "supplier",
    "customer",
    "part",
    "partsupp",
    "orders",
    "lineitem",
)
COPY_ORDER = TPCH_TABLES


@dataclass(frozen=True)
class SmokeQueryResult:
    database: str
    joined_rows: int
    revenue: float


@dataclass(frozen=True)
class ScaleFactorCacheStatus:
    scale_factor: str
    directory: Path
    existing_tbl_files: tuple[Path, ...]
    missing_expected_files: tuple[str, ...]

    @property
    def has_any_tbl_files(self) -> bool:
        """Return True when any generated .tbl file exists for this scale factor."""
        return bool(self.existing_tbl_files)

    @property
    def is_complete(self) -> bool:
        """Return True when every expected TPC-H table file exists."""
        return not self.missing_expected_files


def project_postgres_config(config: dict[str, Any]) -> PostgresConfig:
    """Return an absolute-path PostgreSQL config suitable for local execution."""
    settings = postgres_config(config)
    return PostgresConfig(
        version=settings.version,
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        admin_database=settings.admin_database,
        docker_compose_file=(ROOT_DIR / settings.docker_compose_file).resolve(),
        docker_service_name=settings.docker_service_name,
        dbgen_service_name=settings.dbgen_service_name,
        data_root=(ROOT_DIR / settings.data_root).resolve(),
        dbgen_image_tag=settings.dbgen_image_tag,
        dbgen_repo=settings.dbgen_repo,
        dbgen_commit=settings.dbgen_commit,
        scale_factor_databases=settings.scale_factor_databases,
    )


def scale_factor_directory_name(scale_factor: str) -> str:
    """Return the on-disk directory slug for a configured scale factor."""
    return f"sf_{scale_factor.replace('.', '_')}"


def scale_factor_directories(settings: PostgresConfig) -> dict[str, Path]:
    """Return the generated flat-file directory for each configured scale factor."""
    return {
        scale_factor: settings.data_root / scale_factor_directory_name(scale_factor)
        for scale_factor in settings.scale_factor_databases
    }


def compose_args(settings: PostgresConfig) -> list[str]:
    """Return the base docker compose invocation for this project."""
    return ["docker", "compose", "-f", str(settings.docker_compose_file)]


def run_command(
    args: list[str],
    cwd: Path | None = None,
) -> None:
    """Run a subprocess and raise if it fails."""
    subprocess.run(args, cwd=cwd or ROOT_DIR, check=True)


def start_postgres(settings: PostgresConfig) -> None:
    """Start the project-managed PostgreSQL container and wait for connectivity."""
    settings.data_root.mkdir(parents=True, exist_ok=True)
    run_command([*compose_args(settings), "up", "-d", settings.docker_service_name])
    wait_for_postgres(settings)


def stop_postgres(settings: PostgresConfig) -> None:
    """Stop the project-managed PostgreSQL container."""
    run_command([*compose_args(settings), "stop", settings.docker_service_name])


def reset_postgres(settings: PostgresConfig) -> None:
    """Destroy the project-managed PostgreSQL container state."""
    run_command([*compose_args(settings), "down", "-v", "--remove-orphans"])


def regenerate_data_dir(path: Path) -> None:
    """Replace a generated TPC-H flat-file directory."""
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def expected_table_files() -> tuple[str, ...]:
    """Return the expected .tbl filenames for a TPC-H cache directory."""
    return tuple(f"{table}.tbl" for table in TPCH_TABLES)


def scale_factor_cache_status(
    settings: PostgresConfig, scale_factor: str
) -> ScaleFactorCacheStatus:
    """Inspect the local flat-file cache for one configured scale factor."""
    directory = settings.data_root / scale_factor_directory_name(scale_factor)
    existing_tbl_files = (
        tuple(sorted(directory.glob("*.tbl"))) if directory.exists() else ()
    )
    missing_expected_files = tuple(
        filename
        for filename in expected_table_files()
        if not (directory / filename).exists()
    )
    return ScaleFactorCacheStatus(
        scale_factor=scale_factor,
        directory=directory,
        existing_tbl_files=existing_tbl_files,
        missing_expected_files=missing_expected_files,
    )


def validate_cache_for_reuse(cache_status: ScaleFactorCacheStatus) -> None:
    """Fail fast when a cached scale factor is incomplete."""
    if cache_status.missing_expected_files:
        missing = ", ".join(cache_status.missing_expected_files)
        raise ValueError(
            "Cannot reuse cached TPC-H files for scale factor "
            f"{cache_status.scale_factor} "
            f"in {cache_status.directory}: missing {missing}"
        )


def generate_tpch_data(settings: PostgresConfig, scale_factor: str) -> Path:
    """Generate TPC-H flat files for one configured scale factor."""
    target_dir = settings.data_root / scale_factor_directory_name(scale_factor)
    container_target_dir = POSTGRES_CONTAINER_DATA_ROOT / scale_factor_directory_name(
        scale_factor
    )
    regenerate_data_dir(target_dir)
    command = (
        f"mkdir -p {container_target_dir} "
        f"&& cd {container_target_dir} "
        f"&& dbgen -b /opt/tpch-dbgen/dists.dss -s {scale_factor} -f"
    )
    run_command(
        [*compose_args(settings), "run", "--rm", settings.dbgen_service_name, command]
    )
    return target_dir


def expected_row_counts(scale_factor: str) -> dict[str, int]:
    """Return expected exact TPC-H row counts for the configured scale factor."""
    scale = Decimal(scale_factor)
    return {
        "region": 5,
        "nation": 25,
        "supplier": int(Decimal("10000") * scale),
        "customer": int(Decimal("150000") * scale),
        "part": int(Decimal("200000") * scale),
        "partsupp": int(Decimal("800000") * scale),
        "orders": int(Decimal("1500000") * scale),
    }


def prompt_for_cache_regeneration(cache_status: ScaleFactorCacheStatus) -> bool:
    """Prompt before deleting cached .tbl files for one scale factor."""
    prompt = (
        f"Scale factor {cache_status.scale_factor} already has cached .tbl files in "
        f"{cache_status.directory}. Regenerating will delete the existing files. "
        "Regenerate now? [y/N]: "
    )
    if not sys.stdin.isatty():
        print(
            "Non-interactive input detected for scale factor "
            f"{cache_status.scale_factor}; "
            f"reusing cached .tbl files in {cache_status.directory}. "
            "Use `collect reload-db` to force regeneration."
        )
        return False
    try:
        response = input(prompt).strip().lower()
    except EOFError:
        print(
            "No interactive confirmation available for scale factor "
            f"{cache_status.scale_factor}; "
            f"reusing cached .tbl files in {cache_status.directory}. "
            "Use `collect reload-db` to force regeneration."
        )
        return False
    return response in {"y", "yes"}


def wait_for_postgres(settings: PostgresConfig, timeout_seconds: int = 120) -> None:
    """Block until PostgreSQL accepts connections."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with admin_connection(settings):
                return
        except Exception:
            time.sleep(2)
    raise TimeoutError("PostgreSQL did not become ready within the expected time.")


def admin_connection(settings: PostgresConfig):
    """Return an autocommit connection to the admin database."""
    return connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        dbname=settings.admin_database,
        autocommit=True,
        row_factory=cast(Any, dict_row),
    )


def database_connection(settings: PostgresConfig, database: str):
    """Return a connection to a scale-factor database."""
    return connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        dbname=database,
        autocommit=True,
        row_factory=cast(Any, dict_row),
    )


def recreate_database(settings: PostgresConfig, database: str) -> None:
    """Drop and recreate a target benchmark database."""
    with admin_connection(settings) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) "
            "FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (database,),
        )
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database))
        )
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))


def read_sql_file(path: Path) -> str:
    """Read a SQL file relative to the project SQL directory."""
    return path.read_text()


def create_tpch_schema(settings: PostgresConfig, database: str) -> None:
    """Create the TPC-H schema for a freshly created benchmark database."""
    with database_connection(settings, database) as conn:
        conn.execute(read_sql_file(SQL_DIR / "tpch_schema.sql"))


def apply_post_load_sql(settings: PostgresConfig, database: str) -> None:
    """Apply constraints, indexes, and statistics after bulk loading."""
    with database_connection(settings, database) as conn:
        conn.execute(read_sql_file(SQL_DIR / "tpch_constraints.sql"))
        conn.execute(read_sql_file(SQL_DIR / "tpch_indexes.sql"))


def load_table_from_program(
    settings: PostgresConfig, database: str, table: str, data_file: Path
) -> None:
    """Load one generated TPC-H flat file into PostgreSQL via COPY FROM PROGRAM."""
    container_path = POSTGRES_CONTAINER_DATA_ROOT / data_file.relative_to(
        settings.data_root
    )
    program = f"sed -e 's/|$//' {container_path}"
    query = sql.SQL("COPY {} FROM PROGRAM {} WITH (FORMAT csv, DELIMITER '|')").format(
        sql.Identifier(table), sql.Literal(program)
    )
    with database_connection(settings, database) as conn:
        conn.execute(query)


def load_scale_factor(settings: PostgresConfig, scale_factor: str) -> None:
    """Regenerate and load a configured scale-factor database."""
    data_dir = generate_tpch_data(settings, scale_factor)
    load_scale_factor_from_cache(settings, scale_factor, data_dir)


def load_scale_factor_from_cache(
    settings: PostgresConfig, scale_factor: str, data_dir: Path
) -> None:
    """Load a configured scale-factor database from an existing flat-file cache."""
    database = settings.scale_factor_databases[scale_factor]
    recreate_database(settings, database)
    create_tpch_schema(settings, database)
    for table in COPY_ORDER:
        load_table_from_program(settings, database, table, data_dir / f"{table}.tbl")
    apply_post_load_sql(settings, database)


def load_all_scale_factors(config: dict[str, Any], regenerate: bool = True) -> None:
    """Start PostgreSQL and load every configured scale-factor database."""
    settings = project_postgres_config(config)
    start_postgres(settings)
    for scale_factor in experiment_scale_factors(config):
        normalized_scale_factor = normalize_scale_factor_key(scale_factor)
        if regenerate:
            load_scale_factor(settings, normalized_scale_factor)
            continue
        cache_status = scale_factor_cache_status(settings, normalized_scale_factor)
        validate_cache_for_reuse(cache_status)
        load_scale_factor_from_cache(
            settings, normalized_scale_factor, cache_status.directory
        )


def table_counts(settings: PostgresConfig, database: str) -> dict[str, int]:
    """Return exact row counts for all required TPC-H tables."""
    counts: dict[str, int] = {}
    with database_connection(settings, database) as conn:
        for table in TPCH_TABLES:
            counts[table] = int(
                conn.execute(
                    sql.SQL("SELECT COUNT(*) AS count FROM {}").format(
                        sql.Identifier(table)
                    )
                ).fetchone()["count"]
            )
    return counts


def table_presence(settings: PostgresConfig, database: str) -> set[str]:
    """Return the set of required TPC-H tables present in a target database."""
    with database_connection(settings, database) as conn:
        rows = conn.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            """
        ).fetchall()
    return {str(row["tablename"]) for row in rows}


def run_smoke_query(settings: PostgresConfig, database: str) -> SmokeQueryResult:
    """Execute a simple benchmark-style join query."""
    with database_connection(settings, database) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS joined_rows,
                COALESCE(
                    SUM(l.l_extendedprice * (1 - l.l_discount)),
                    0
                )::double precision AS revenue
            FROM customer AS c
            JOIN orders AS o ON o.o_custkey = c.c_custkey
            JOIN lineitem AS l ON l.l_orderkey = o.o_orderkey
            WHERE c.c_custkey <= 1000
            """
        ).fetchone()
    return SmokeQueryResult(
        database=database,
        joined_rows=int(row["joined_rows"]),
        revenue=float(row["revenue"]),
    )
