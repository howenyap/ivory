"""Tests for CLI argument handling."""

from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

import ivory.cli as cli
from ivory.commands import collect as collect_commands


class CollectCliTests(unittest.TestCase):
    def test_collect_scale_positionals_become_scale_factor_args(self) -> None:
        captured: dict[str, object] = {}

        def fake_handle_collect(namespace: argparse.Namespace) -> int:
            captured["scale_factors"] = namespace.scale_factors
            captured["collect_command"] = namespace.collect_command
            return 0

        with patch.object(
            collect_commands, "_handle_collect", side_effect=fake_handle_collect
        ):
            result = cli.main(["collect", "1.0", "3.0"])

        self.assertEqual(result, 0)
        self.assertEqual(captured["scale_factors"], ["1.0", "3.0"])
        self.assertIsNone(captured["collect_command"])

    def test_collect_db_subcommand_remains_subcommand(self) -> None:
        captured: dict[str, object] = {}

        def fake_load_db(namespace: argparse.Namespace) -> int:
            captured["collect_command"] = namespace.collect_command
            return 0

        with patch.object(
            collect_commands, "_handle_load_db", side_effect=fake_load_db
        ):
            result = cli.main(["collect", "load-db"])

        self.assertEqual(result, 0)
        self.assertEqual(captured["collect_command"], "load-db")

    def test_collect_resume_before_scale_positional_is_preserved(self) -> None:
        captured: dict[str, object] = {}

        def fake_handle_collect(namespace: argparse.Namespace) -> int:
            captured["scale_factors"] = namespace.scale_factors
            captured["resume"] = namespace.resume
            return 0

        with patch.object(
            collect_commands, "_handle_collect", side_effect=fake_handle_collect
        ):
            result = cli.main(["collect", "--resume", "1.0"])

        self.assertEqual(result, 0)
        self.assertEqual(captured["scale_factors"], ["1.0"])
        self.assertTrue(captured["resume"])

    def test_collect_typo_subcommand_is_not_rewritten_as_scale_factor(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            cli.main(["collect", "lod-db"])

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
