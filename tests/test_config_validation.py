"""Tests for the phase 0b experiment contract validation."""

from __future__ import annotations

import unittest

from ivory.config import schema_reference_paths, validate_config


class ValidateConfigTests(unittest.TestCase):
    def test_validate_config_succeeds_for_default_contract(self) -> None:
        self.assertEqual(validate_config(), [])

    def test_schema_reference_paths_match_phase_contract(self) -> None:
        self.assertEqual(len(schema_reference_paths()), 7)


if __name__ == "__main__":
    unittest.main()
