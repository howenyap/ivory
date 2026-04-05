"""Evaluation-stage commands for phase 3b."""

from __future__ import annotations

import argparse


def register_evaluate_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the evaluate command tree."""
    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Run phase 3b evaluation: grouped splits, ablations, error analysis.",
        description="Evaluation commands for phase 3b.",
    )
    evaluate_subparsers = evaluate_parser.add_subparsers(
        dest="evaluate_command", metavar="evaluate-command"
    )

    grouped_parser = evaluate_subparsers.add_parser(
        "grouped",
        help="Run grouped-by-template evaluation.",
        description=(
            "Train on held-in templates, evaluate on held-out templates, "
            "emit grouped_metrics.json and grouped_split_manifest.json."
        ),
    )
    grouped_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the experiment seed.",
    )
    grouped_parser.set_defaults(handler=_handle_evaluate_grouped)

    ablations_parser = evaluate_subparsers.add_parser(
        "ablations",
        help="Run feature-family and scale-factor ablations.",
        description=(
            "Run SQL-only, plan-only, combined, scale-factor, and "
            "postgres-cost-proxy ablations. Emits ablations.json."
        ),
    )
    ablations_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the experiment seed.",
    )
    ablations_parser.set_defaults(handler=_handle_evaluate_ablations)

    error_analysis_parser = evaluate_subparsers.add_parser(
        "error-analysis",
        help="Generate per-observation error analysis.",
        description=(
            "Produce error_analysis.parquet with per-observation errors "
            "from the grouped test split. Requires grouped evaluation to have run first."
        ),
    )
    error_analysis_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the experiment seed.",
    )
    error_analysis_parser.set_defaults(handler=_handle_evaluate_error_analysis)


def _handle_evaluate_grouped(args: argparse.Namespace) -> int:
    from ivory.evaluation import run_grouped_evaluation

    summary = run_grouped_evaluation(seed=args.seed)
    print(
        f"Grouped evaluation complete: "
        f"folds={summary['folds']} "
        f"templates={summary['templates']} "
        f"split_hash={summary['split_hash'][:12]}..."
    )
    return 0


def _handle_evaluate_ablations(args: argparse.Namespace) -> int:
    from ivory.evaluation import run_ablations

    summary = run_ablations(seed=args.seed)
    print(f"Ablations complete: {summary['ablations_path']}")
    return 0


def _handle_evaluate_error_analysis(args: argparse.Namespace) -> int:
    from ivory.evaluation import run_error_analysis

    summary = run_error_analysis(seed=args.seed)
    print(
        f"Error analysis complete: "
        f"rows={summary['rows']} "
        f"path={summary['error_analysis_path']}"
    )
    return 0
