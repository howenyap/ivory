"""Metrics validation commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ivory.baseline_modeling import validate_metrics_artifact


def register_validate_metrics_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the validate-metrics command tree."""
    validate_parser = subparsers.add_parser(
        "validate-metrics",
        help="Validate structured metrics artifacts against a JSON schema.",
        description="Metrics artifact validation commands for Ivory.",
    )
    validate_subparsers = validate_parser.add_subparsers(
        dest="validate_metrics_command", metavar="validate-metrics-command"
    )

    baseline_parser = validate_subparsers.add_parser(
        "baseline",
        help="Validate the baseline metrics artifact.",
        description="Validate artifacts/models/baseline_metrics.json.",
    )
    baseline_parser.add_argument(
        "--schema",
        required=True,
        help="Path to the JSON schema to validate against.",
    )
    baseline_parser.add_argument(
        "--artifact",
        required=True,
        help="Path to the metrics artifact JSON file.",
    )
    baseline_parser.set_defaults(handler=_handle_validate_baseline_metrics)


def _handle_validate_baseline_metrics(args: argparse.Namespace) -> int:
    artifact = json.loads(Path(args.artifact).read_text())
    validate_metrics_artifact(artifact=artifact, schema_path=args.schema)
    print("Metrics validation succeeded.")
    return 0
