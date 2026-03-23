"""Featurization-stage commands."""

from __future__ import annotations

import argparse

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


def _handle_featurize_sql(_: argparse.Namespace) -> int:
    summary = featurize_sql_queries()
    print(
        "SQL featurization complete: "
        f"query_instances={summary['input_query_instances']} "
        f"feature_rows={summary['feature_rows']} "
        f"exclusions={summary['exclusion_rows']}"
    )
    return 0
