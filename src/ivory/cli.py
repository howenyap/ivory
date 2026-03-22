"""Command line interface for Ivory."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ivory.commands import COMMAND_NAMES


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ivory",
        description="Ivory experiment pipeline bootstrap CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    for command_name in COMMAND_NAMES:
        command_parser = subparsers.add_parser(
            command_name,
            help=f"Placeholder command for the {command_name} stage.",
            description=f"{command_name} is not implemented in phase 0a.",
        )
        command_parser.set_defaults(handler=_make_placeholder_handler(command_name))

    return parser


def _make_placeholder_handler(command_name: str):
    def _handler(_: argparse.Namespace) -> int:
        raise SystemExit(f"{command_name} is not implemented in phase 0a bootstrap.")

    return _handler


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
