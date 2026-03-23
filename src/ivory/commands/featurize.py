"""Featurization-stage commands."""

from __future__ import annotations

import argparse

from ivory.dataset_assembly import assemble_feature_dataset
from ivory.plan_features import featurize_query_plans
from ivory.sql_features import featurize_sql_queries


def register_featurize_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the featurize command tree."""
    featurize_parser = subparsers.add_parser(
        "featurize",
        help="Generate feature artifacts from collected raw inputs.",
        description="Feature extraction commands for Ivory.",
    )
    featurize_subparsers = featurize_parser.add_subparsers(
        dest="featurize_command", metavar="featurize-command"
    )

    sql_parser = featurize_subparsers.add_parser(
        "sql",
        help="Extract structural SQL features from successful raw query instances.",
        description="Build artifacts/features/sql_features.parquet for phase 2a.",
    )
    sql_parser.set_defaults(handler=_handle_featurize_sql)

    plan_parser = featurize_subparsers.add_parser(
        "plan",
        help="Extract structural plan features from successful raw observations.",
        description="Build artifacts/features/plan_features.parquet for phase 2b.",
    )
    plan_parser.set_defaults(handler=_handle_featurize_plan)

    assemble_parser = featurize_subparsers.add_parser(
        "assemble",
        help="Assemble the final observation-grain modeling dataset.",
        description="Build artifacts/features/features.parquet for phase 2c.",
    )
    assemble_parser.set_defaults(handler=_handle_featurize_assemble)


def _handle_featurize_sql(_: argparse.Namespace) -> int:
    summary = featurize_sql_queries()
    print(
        "SQL featurization complete: "
        f"query_instances={summary['input_query_instances']} "
        f"feature_rows={summary['feature_rows']} "
        f"exclusions={summary['exclusion_rows']}"
    )
    return 0


def _handle_featurize_plan(_: argparse.Namespace) -> int:
    summary = featurize_query_plans()
    print(
        "Plan featurization complete: "
        f"observations={summary['input_observations']} "
        f"feature_rows={summary['feature_rows']} "
        f"exclusions={summary['exclusion_rows']}"
    )
    return 0


def _handle_featurize_assemble(_: argparse.Namespace) -> int:
    summary = assemble_feature_dataset()
    print(
        "Dataset assembly complete: "
        f"successful_observations={summary['successful_observations']} "
        f"eligible_observations={summary['eligible_observations']} "
        f"feature_rows={summary['feature_rows']}"
    )
    return 0
