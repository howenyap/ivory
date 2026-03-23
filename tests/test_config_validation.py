"""Tests for the phase 0b experiment contract validation."""

from __future__ import annotations

import unittest

from ivory.config import (
    compose_contract_values,
    load_config,
    postgres_config,
    schema_reference_paths,
    validate_config,
)


class ValidateConfigTests(unittest.TestCase):
    def test_validate_config_succeeds_for_default_contract(self) -> None:
        self.assertEqual(validate_config(), [])

    def test_schema_reference_paths_match_phase_contract(self) -> None:
        self.assertEqual(len(schema_reference_paths()), 7)

    def test_postgres_mapping_matches_experiment_mapping(self) -> None:
        config = load_config()
        self.assertEqual(
            config["experiment"]["scale_factor_databases"],
            config["postgres"]["scale_factor_databases"],
        )

    def test_postgres_config_uses_frozen_database_targets(self) -> None:
        settings = postgres_config(load_config())
        self.assertEqual(
            settings.scale_factor_databases["10.0"],
            "tpch_sf_10",
        )

    def test_docker_compose_pins_match_postgres_contract(self) -> None:
        config = load_config()
        compose_values = compose_contract_values()
        postgres = config["postgres"]
        self.assertEqual(compose_values["postgres_version"], postgres["version"])
        self.assertEqual(compose_values["dbgen_repo"], postgres["dbgen_repo"])
        self.assertEqual(compose_values["dbgen_commit"], postgres["dbgen_commit"])
        self.assertEqual(compose_values["dbgen_image_tag"], postgres["dbgen_image_tag"])


if __name__ == "__main__":
    unittest.main()
