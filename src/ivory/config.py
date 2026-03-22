"""Configuration loading helpers for Ivory."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("configs/experiment.toml")


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
