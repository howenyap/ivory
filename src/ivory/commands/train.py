"""Training-stage commands."""

from __future__ import annotations

import argparse

from ivory.baseline_modeling import train_baseline_models


def register_train_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the train command tree."""
    train_parser = subparsers.add_parser(
        "train",
        help="Train Ivory modeling baselines.",
        description="Model training commands for Ivory.",
    )
    train_subparsers = train_parser.add_subparsers(
        dest="train_command", metavar="train-command"
    )

    baseline_parser = train_subparsers.add_parser(
        "baseline",
        help="Train the phase 3a baseline regressors.",
        description="Build baseline model artifacts for phase 3a.",
    )
    baseline_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the experiment seed for deterministic split/training.",
    )
    baseline_parser.add_argument(
        "--scale-factor",
        type=float,
        default=None,
        help="Optionally restrict training to a single scale factor.",
    )
    baseline_parser.set_defaults(handler=_handle_train_baseline)


def _handle_train_baseline(args: argparse.Namespace) -> int:
    summary = train_baseline_models(seed=args.seed, scale_factor=args.scale_factor)
    print(
        "Baseline training complete: "
        f"rows={summary['rows']} "
        f"train={summary['train_rows']} "
        f"validation={summary['validation_rows']} "
        f"test={summary['test_rows']}"
    )
    return 0
