"""Configuration loading and contract validation helpers for Ivory."""

from __future__ import annotations

import json
import tomllib
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
    "postgresql_version",
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
REQUIRED_ARTIFACT_CONTRACT_KEYS = (
    "modeling_grain",
    "artifacts",
    "keys",
    "status_fields",
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

    scale_factor_databases = experiment.get("scale_factor_databases")
    if not isinstance(scale_factor_databases, dict):
        errors.append("experiment.scale_factor_databases must be a table.")
    elif isinstance(scale_factors, list):
        expected_keys = {str(scale_factor) for scale_factor in scale_factors}
        actual_keys = set(scale_factor_databases)
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
