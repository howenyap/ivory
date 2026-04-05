"""Helpers for loading feasible-coverage query-compare benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_benchmark(*, benchmark_path: Path) -> dict[str, Any]:
    """Load the query-compare benchmark artifact."""
    return json.loads(benchmark_path.read_text())


def get_screened_templates(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every screened template recorded in the benchmark."""
    return list(benchmark["templates"])


def get_included_templates(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only templates accepted into the feasible-coverage benchmark."""
    return [
        template
        for template in get_screened_templates(benchmark)
        if str(template.get("template_status", "included")) == "included"
    ]
