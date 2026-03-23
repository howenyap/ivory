"""Configuration loading and contract validation helpers for Ivory."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("configs/experiment.toml")
SCHEMA_DIR = Path("schemas")
SCHEMA_PATHS = (
    SCHEMA_DIR / "artifact_contract.json",
    SCHEMA_DIR / "raw_runs.schema.json",
    SCHEMA_DIR / "sql_features.schema.json",
    SCHEMA_DIR / "plan_features.schema.json",
    SCHEMA_DIR / "features.schema.json",
    SCHEMA_DIR / "baseline_metrics.schema.json",
    SCHEMA_DIR / "grouped_metrics.schema.json",
)
REQUIRED_EXPERIMENT_KEYS = (
    "tpch_scale_factors",
    "scale_factor_databases",
    "query_timeout_seconds",
    "retry_count",
    "runs_per_query",
    "primary_timing_label_policy",
    "seed",
    "split_modes",
    "modeling_grain",
    "final_null_handling_policy",
    "required_metrics",
)
REQUIRED_SPLIT_MODES = ("baseline", "grouped")
REQUIRED_METRIC_GROUPS = ("baseline", "grouped")
REQUIRED_TARGETS = ("planner_total_cost", "execution_time_ms")
REQUIRED_POSTGRES_KEYS = (
    "version",
    "host",
    "port",
    "user",
    "password",
    "admin_database",
    "docker_compose_file",
    "docker_service_name",
    "dbgen_service_name",
    "data_root",
    "dbgen_image_tag",
    "dbgen_repo",
    "dbgen_commit",
    "scale_factor_databases",
)
REQUIRED_ARTIFACT_CONTRACT_KEYS = (
    "modeling_grain",
    "artifacts",
    "keys",
    "status_fields",
)
COMPOSE_POSTGRES_IMAGE_PATTERN = re.compile(r"image:\s*postgres:(?P<version>[^\s]+)")
COMPOSE_DBGEN_REPO_PATTERN = re.compile(r"TPCH_DBGEN_REPO:\s*(?P<repo>\S+)")
COMPOSE_DBGEN_COMMIT_PATTERN = re.compile(r"TPCH_DBGEN_COMMIT:\s*(?P<commit>\S+)")
COMPOSE_DBGEN_IMAGE_PATTERN = re.compile(r"image:\s*(?P<image>ivory/tpch-dbgen:[^\s]+)")


@dataclass(frozen=True)
class PostgresConfig:
    version: str
    host: str
    port: int
    user: str
    password: str
    admin_database: str
    docker_compose_file: Path
    docker_service_name: str
    dbgen_service_name: str
    data_root: Path
    dbgen_image_tag: str
    dbgen_repo: str
    dbgen_commit: str
    scale_factor_databases: dict[str, str]


def normalize_scale_factor_key(scale_factor: float | str) -> str:
    """Normalize scale factors to the canonical string keys used in config."""
    return f"{float(scale_factor):.1f}"


def experiment_scale_factors(config: dict[str, Any]) -> list[str]:
    """Return canonical scale-factor keys from the experiment contract."""
    experiment = config["experiment"]
    raw_scale_factors = experiment.get(
        "scale_factors", experiment["tpch_scale_factors"]
    )
    return [
        normalize_scale_factor_key(scale_factor) for scale_factor in raw_scale_factors
    ]


def postgres_config(config: dict[str, Any]) -> PostgresConfig:
    """Parse the PostgreSQL environment config from the experiment contract."""
    postgres = config["postgres"]
    return PostgresConfig(
        version=str(postgres["version"]),
        host=str(postgres["host"]),
        port=int(postgres["port"]),
        user=str(postgres["user"]),
        password=str(postgres["password"]),
        admin_database=str(postgres["admin_database"]),
        docker_compose_file=Path(str(postgres["docker_compose_file"])),
        docker_service_name=str(postgres["docker_service_name"]),
        dbgen_service_name=str(postgres["dbgen_service_name"]),
        data_root=Path(str(postgres["data_root"])),
        dbgen_image_tag=str(postgres["dbgen_image_tag"]),
        dbgen_repo=str(postgres["dbgen_repo"]),
        dbgen_commit=str(postgres["dbgen_commit"]),
        scale_factor_databases={
            normalize_scale_factor_key(key): str(value)
            for key, value in dict(postgres["scale_factor_databases"]).items()
        },
    )


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load the experiment configuration from TOML."""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            "Create configs/experiment.toml in a later phase."
        )

    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)


def load_schema(path: str | Path) -> dict[str, Any]:
    """Load a JSON contract file."""
    schema_path = Path(path)
    return json.loads(schema_path.read_text())


def schema_reference_paths() -> tuple[Path, ...]:
    """Return the canonical machine-readable contract paths."""
    return SCHEMA_PATHS


def compose_contract_values(path: str | Path = "docker-compose.yml") -> dict[str, str]:
    """Extract the pinned Docker Compose values that must match experiment config."""
    compose_path = Path(path)
    text = compose_path.read_text()

    postgres_match = COMPOSE_POSTGRES_IMAGE_PATTERN.search(text)
    repo_match = COMPOSE_DBGEN_REPO_PATTERN.search(text)
    commit_match = COMPOSE_DBGEN_COMMIT_PATTERN.search(text)
    image_matches = COMPOSE_DBGEN_IMAGE_PATTERN.findall(text)

    if (
        postgres_match is None
        or repo_match is None
        or commit_match is None
        or len(image_matches) < 1
    ):
        raise ValueError(
            f"Could not extract required pinned values from {compose_path}."
        )

    dbgen_image = image_matches[-1]
    return {
        "postgres_version": postgres_match.group("version"),
        "dbgen_repo": repo_match.group("repo"),
        "dbgen_commit": commit_match.group("commit"),
        "dbgen_image_tag": dbgen_image,
    }


def validate_config(path: str | None = None) -> list[str]:
    """Validate the experiment contract configuration and schema references."""
    errors: list[str] = []
    config = load_config(path)
    experiment = config.get("experiment")
    if not isinstance(experiment, dict):
        return ["Missing required [experiment] table."]

    for key in REQUIRED_EXPERIMENT_KEYS:
        if key not in experiment:
            errors.append(f"Missing required experiment key: {key}")

    scale_factors = experiment.get("tpch_scale_factors")
    if not isinstance(scale_factors, list) or not scale_factors:
        errors.append("experiment.tpch_scale_factors must be a non-empty list.")
        expected_scale_factor_keys: set[str] = set()
    else:
        expected_scale_factor_keys = {
            normalize_scale_factor_key(scale_factor) for scale_factor in scale_factors
        }

    scale_factors_alias = experiment.get("scale_factors")
    if not isinstance(scale_factors_alias, list) or not scale_factors_alias:
        errors.append("experiment.scale_factors must be a non-empty list.")
    elif (
        expected_scale_factor_keys
        and {
            normalize_scale_factor_key(scale_factor)
            for scale_factor in scale_factors_alias
        }
        != expected_scale_factor_keys
    ):
        errors.append(
            "experiment.scale_factors must match experiment.tpch_scale_factors exactly."
        )

    scale_factor_databases = experiment.get("scale_factor_databases")
    if not isinstance(scale_factor_databases, dict):
        errors.append("experiment.scale_factor_databases must be a table.")
    elif expected_scale_factor_keys:
        actual_keys = {
            normalize_scale_factor_key(scale_factor)
            for scale_factor in scale_factor_databases
        }
        expected_keys = expected_scale_factor_keys
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        if missing:
            errors.append(
                "experiment.scale_factor_databases is missing mappings for: "
                + ", ".join(missing)
            )
        if extra:
            errors.append(
                "experiment.scale_factor_databases has unexpected mappings for: "
                + ", ".join(extra)
            )

    split_modes = experiment.get("split_modes")
    if not isinstance(split_modes, dict):
        errors.append("experiment.split_modes must be a table.")
    else:
        for key in REQUIRED_SPLIT_MODES:
            if key not in split_modes:
                errors.append(f"experiment.split_modes must define {key}.")

    required_metrics = experiment.get("required_metrics")
    if not isinstance(required_metrics, dict):
        errors.append("experiment.required_metrics must be a table.")
    else:
        for group in REQUIRED_METRIC_GROUPS:
            metrics = required_metrics.get(group)
            if not isinstance(metrics, list) or not metrics:
                errors.append(
                    f"experiment.required_metrics.{group} must be a non-empty list."
                )
                continue
            for target in REQUIRED_TARGETS:
                if target not in metrics:
                    errors.append(
                        f"experiment.required_metrics.{group} must include {target}."
                    )

    postgres = config.get("postgres")
    if not isinstance(postgres, dict):
        errors.append("Missing required [postgres] table.")
    else:
        for key in REQUIRED_POSTGRES_KEYS:
            if key not in postgres:
                errors.append(f"Missing required postgres key: {key}")

        postgres_scale_factor_databases = postgres.get("scale_factor_databases")
        if not isinstance(postgres_scale_factor_databases, dict):
            errors.append("postgres.scale_factor_databases must be a table.")
        elif expected_scale_factor_keys:
            postgres_keys = {
                normalize_scale_factor_key(scale_factor)
                for scale_factor in postgres_scale_factor_databases
            }
            missing = sorted(expected_scale_factor_keys - postgres_keys)
            extra = sorted(postgres_keys - expected_scale_factor_keys)
            if missing:
                errors.append(
                    "postgres.scale_factor_databases is missing mappings for: "
                    + ", ".join(missing)
                )
            if extra:
                errors.append(
                    "postgres.scale_factor_databases has unexpected mappings for: "
                    + ", ".join(extra)
                )
            experiment_mapping = {
                normalize_scale_factor_key(scale_factor): database
                for scale_factor, database in dict(scale_factor_databases or {}).items()
            }
            postgres_mapping = {
                normalize_scale_factor_key(scale_factor): database
                for scale_factor, database in postgres_scale_factor_databases.items()
            }
            if experiment_mapping != postgres_mapping:
                errors.append(
                    "postgres.scale_factor_databases must match "
                    "experiment.scale_factor_databases."
                )

        compose_path = Path(
            str(postgres.get("docker_compose_file", "docker-compose.yml"))
        )
        if not compose_path.exists():
            errors.append(f"Missing docker compose file: {compose_path}")
        else:
            try:
                compose_values = compose_contract_values(compose_path)
            except ValueError as exc:
                errors.append(str(exc))
            else:
                if compose_values["postgres_version"] != str(postgres.get("version")):
                    errors.append(
                        "docker-compose.yml postgres image version must match "
                        "postgres.version."
                    )
                if compose_values["dbgen_repo"] != str(postgres.get("dbgen_repo")):
                    errors.append(
                        "docker-compose.yml TPCH_DBGEN_REPO must match "
                        "postgres.dbgen_repo."
                    )
                if compose_values["dbgen_commit"] != str(postgres.get("dbgen_commit")):
                    errors.append(
                        "docker-compose.yml TPCH_DBGEN_COMMIT must match "
                        "postgres.dbgen_commit."
                    )
                if compose_values["dbgen_image_tag"] != str(
                    postgres.get("dbgen_image_tag")
                ):
                    errors.append(
                        "docker-compose.yml tpch-dbgen image tag must match "
                        "postgres.dbgen_image_tag."
                    )

    if experiment.get("modeling_grain") != "successful_observation":
        errors.append("experiment.modeling_grain must be successful_observation.")

    for schema_path in schema_reference_paths():
        if not schema_path.exists():
            errors.append(f"Missing schema file: {schema_path}")
            continue
        try:
            contract = load_schema(schema_path)
        except json.JSONDecodeError as exc:
            errors.append(f"{schema_path} is not valid JSON: {exc}")
            continue

        if schema_path.name == "artifact_contract.json":
            for key in REQUIRED_ARTIFACT_CONTRACT_KEYS:
                if key not in contract:
                    errors.append(f"{schema_path} is missing required key: {key}")

    return errors
