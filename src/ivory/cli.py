"""Command line interface for Ivory."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence

from ivory.commands import COMMAND_NAMES
from ivory.commands.collect import COLLECT_DB_COMMANDS, register_collect_subparser
from ivory.commands.featurize import register_featurize_subparser
from ivory.config import validate_config

SCALE_FACTOR_TOKEN_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ivory",
        description="Ivory experiment pipeline bootstrap CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    register_collect_subparser(subparsers)
    register_featurize_subparser(subparsers)

    for command_name in COMMAND_NAMES:
        if command_name in {"collect", "featurize"}:
            continue
        command_parser = subparsers.add_parser(
            command_name,
            help=f"Placeholder command for the {command_name} stage.",
            description=f"{command_name} is not implemented in phase 0a.",
        )
        command_parser.set_defaults(handler=_make_placeholder_handler(command_name))

    validate_parser = subparsers.add_parser(
        "validate-config",
        help="Validate the experiment contract configuration and schema references.",
        description="Validate the machine-readable experiment contract for phase 0b.",
    )
    validate_parser.add_argument(
        "--config",
        default=None,
        help="Path to a TOML experiment config. Defaults to configs/experiment.toml.",
    )
    validate_parser.set_defaults(handler=_handle_validate_config)

    return parser


def _make_placeholder_handler(command_name: str):
    def _handler(_: argparse.Namespace) -> int:
        raise SystemExit(f"{command_name} is not implemented in phase 0a bootstrap.")

    return _handler


def _handle_validate_config(args: argparse.Namespace) -> int:
    errors = validate_config(args.config)
    if errors:
        for error in errors:
            print(f"- {error}")
        return 1

    print("Experiment contract validation succeeded.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    normalized_argv = normalize_collect_argv(
        list(argv) if argv is not None else list(sys.argv[1:])
    )
    args = parser.parse_args(normalized_argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return handler(args)


def normalize_collect_argv(argv: list[str]) -> list[str]:
    """Rewrite `collect 1.0` into `collect --scale-factor 1.0`."""
    if not argv or argv[0] != "collect":
        return argv

    normalized = [argv[0]]
    option_with_value = {
        "--config",
        "--limit-templates",
        "--limit-params",
        "--limit-scales",
        "--timeout-ms",
        "--scale-factor",
    }
    index = 1
    while index < len(argv):
        token = argv[index]
        if token in option_with_value:
            normalized.append(token)
            index += 1
            if index < len(argv):
                normalized.append(argv[index])
            index += 1
            continue
        if token.startswith("-"):
            normalized.append(token)
            index += 1
            continue
        if token in COLLECT_DB_COMMANDS:
            normalized.extend(argv[index:])
            break
        if not SCALE_FACTOR_TOKEN_PATTERN.fullmatch(token):
            normalized.extend(argv[index:])
            break
        normalized.extend(["--scale-factor", token])
        index += 1
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
