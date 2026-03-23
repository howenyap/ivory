"""Tests for interactive TPC-H cache handling in collect load-db."""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ivory.commands import collect
from ivory.config import PostgresConfig
from ivory.postgres import (
    prompt_for_cache_regeneration,
    scale_factor_cache_status,
    validate_cache_for_reuse,
)


def _settings(data_root: Path) -> PostgresConfig:
    return PostgresConfig(
        version="16",
        host="127.0.0.1",
        port=55432,
        user="ivory",
        password="ivory",
        admin_database="postgres",
        docker_compose_file=Path("docker-compose.yml"),
        docker_service_name="postgres",
        dbgen_service_name="tpch-dbgen",
        data_root=data_root,
        dbgen_image_tag="ivory/tpch-dbgen:phase-1a",
        dbgen_repo="https://github.com/electrum/tpch-dbgen.git",
        dbgen_commit="32f1c1b92d1664dba542e927d23d86ffa57aa253",
        scale_factor_databases={"0.1": "tpch_sf_0_1", "1.0": "tpch_sf_1"},
    )


class CacheStatusTests(unittest.TestCase):
    def test_cache_status_reports_no_tbl_files_for_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(Path(tmpdir))
            status = scale_factor_cache_status(settings, "0.1")
            self.assertFalse(status.has_any_tbl_files)
            self.assertFalse(status.is_complete)

    def test_cache_status_reports_tbl_files_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(Path(tmpdir))
            cache_dir = settings.data_root / "sf_0_1"
            cache_dir.mkdir(parents=True)
            (cache_dir / "region.tbl").write_text("1|AFRICA|\n")
            status = scale_factor_cache_status(settings, "0.1")
            self.assertTrue(status.has_any_tbl_files)
            self.assertIn(cache_dir / "region.tbl", status.existing_tbl_files)

    def test_reuse_validation_rejects_incomplete_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _settings(Path(tmpdir))
            cache_dir = settings.data_root / "sf_0_1"
            cache_dir.mkdir(parents=True)
            (cache_dir / "region.tbl").write_text("1|AFRICA|\n")
            status = scale_factor_cache_status(settings, "0.1")
            with self.assertRaisesRegex(ValueError, "missing nation.tbl"):
                validate_cache_for_reuse(status)


class CollectCommandTests(unittest.TestCase):
    def test_prompt_decline_reuses_existing_files(self) -> None:
        args = argparse.Namespace(config=None)
        config = {
            "experiment": {
                "scale_factors": [0.1],
                "tpch_scale_factors": [0.1],
            }
        }
        settings = _settings(Path("/tmp/tpch-data"))
        status = scale_factor_cache_status(settings, "0.1")
        complete_status = status.__class__(
            scale_factor="0.1",
            directory=Path("/tmp/tpch-data/sf_0_1"),
            existing_tbl_files=(Path("/tmp/tpch-data/sf_0_1/region.tbl"),),
            missing_expected_files=(),
        )
        with (
            patch.object(collect, "_load_runtime", return_value=(config, settings)),
            patch.object(collect, "start_postgres"),
            patch.object(
                collect,
                "scale_factor_directories",
                return_value={"0.1": Path("/tmp/tpch-data/sf_0_1")},
            ),
            patch.object(
                collect, "scale_factor_cache_status", return_value=complete_status
            ),
            patch.object(collect, "prompt_for_cache_regeneration", return_value=False),
            patch.object(collect, "validate_cache_for_reuse"),
            patch.object(collect, "generate_tpch_data") as generate_mock,
            patch.object(collect, "load_scale_factor_from_cache") as load_mock,
        ):
            result = collect._handle_load_db(args)
        self.assertEqual(result, 0)
        generate_mock.assert_not_called()
        load_mock.assert_called_once_with(settings, "0.1", complete_status.directory)

    def test_prompt_accept_regenerates_existing_files(self) -> None:
        args = argparse.Namespace(config=None)
        config = {
            "experiment": {
                "scale_factors": [0.1],
                "tpch_scale_factors": [0.1],
            }
        }
        settings = _settings(Path("/tmp/tpch-data"))
        status = scale_factor_cache_status(settings, "0.1")
        prompted_status = status.__class__(
            scale_factor="0.1",
            directory=Path("/tmp/tpch-data/sf_0_1"),
            existing_tbl_files=(Path("/tmp/tpch-data/sf_0_1/region.tbl"),),
            missing_expected_files=("nation.tbl",),
        )
        generated_dir = Path("/tmp/tpch-data/sf_0_1")
        with (
            patch.object(collect, "_load_runtime", return_value=(config, settings)),
            patch.object(collect, "start_postgres"),
            patch.object(
                collect, "scale_factor_directories", return_value={"0.1": generated_dir}
            ),
            patch.object(
                collect, "scale_factor_cache_status", return_value=prompted_status
            ),
            patch.object(collect, "prompt_for_cache_regeneration", return_value=True),
            patch.object(
                collect, "generate_tpch_data", return_value=generated_dir
            ) as generate_mock,
            patch.object(collect, "load_scale_factor_from_cache") as load_mock,
        ):
            result = collect._handle_load_db(args)
        self.assertEqual(result, 0)
        generate_mock.assert_called_once_with(settings, "0.1")
        load_mock.assert_called_once_with(settings, "0.1", generated_dir)

    def test_load_db_without_cache_generates_without_prompt(self) -> None:
        args = argparse.Namespace(config=None)
        config = {
            "experiment": {
                "scale_factors": [0.1],
                "tpch_scale_factors": [0.1],
            }
        }
        settings = _settings(Path("/tmp/tpch-data"))
        empty_status = scale_factor_cache_status(settings, "0.1")
        generated_dir = Path("/tmp/tpch-data/sf_0_1")
        with (
            patch.object(collect, "_load_runtime", return_value=(config, settings)),
            patch.object(collect, "start_postgres"),
            patch.object(
                collect, "scale_factor_directories", return_value={"0.1": generated_dir}
            ),
            patch.object(
                collect, "scale_factor_cache_status", return_value=empty_status
            ),
            patch.object(collect, "prompt_for_cache_regeneration") as prompt_mock,
            patch.object(
                collect, "generate_tpch_data", return_value=generated_dir
            ) as generate_mock,
            patch.object(collect, "load_scale_factor_from_cache"),
        ):
            result = collect._handle_load_db(args)
        self.assertEqual(result, 0)
        prompt_mock.assert_not_called()
        generate_mock.assert_called_once_with(settings, "0.1")

    def test_reload_db_always_regenerates_without_prompt(self) -> None:
        args = argparse.Namespace(config=None)
        config = {
            "experiment": {
                "scale_factors": [0.1],
                "tpch_scale_factors": [0.1],
                "scale_factor_databases": {"0.1": "tpch_sf_0_1"},
            }
        }
        settings = _settings(Path("/tmp/tpch-data"))
        generated_dir = Path("/tmp/tpch-data/sf_0_1")
        with (
            patch.object(collect, "_load_runtime", return_value=(config, settings)),
            patch.object(collect, "reset_postgres"),
            patch.object(collect, "start_postgres"),
            patch.object(
                collect, "scale_factor_directories", return_value={"0.1": generated_dir}
            ),
            patch.object(collect, "prompt_for_cache_regeneration") as prompt_mock,
            patch.object(
                collect, "generate_tpch_data", return_value=generated_dir
            ) as generate_mock,
            patch.object(collect, "load_scale_factor_from_cache") as load_mock,
        ):
            result = collect._handle_reload_db(args)
        self.assertEqual(result, 0)
        prompt_mock.assert_not_called()
        generate_mock.assert_called_once_with(settings, "0.1")
        load_mock.assert_called_once_with(settings, "0.1", generated_dir)

    def test_prompt_defaults_to_no_on_empty_input(self) -> None:
        cache_status = scale_factor_cache_status(
            _settings(Path("/tmp/tpch-data")), "0.1"
        )
        prompted_status = cache_status.__class__(
            scale_factor="0.1",
            directory=Path("/tmp/tpch-data/sf_0_1"),
            existing_tbl_files=(Path("/tmp/tpch-data/sf_0_1/region.tbl"),),
            missing_expected_files=(),
        )
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value=""),
        ):
            self.assertFalse(prompt_for_cache_regeneration(prompted_status))

    def test_prompt_reuses_cache_in_noninteractive_mode(self) -> None:
        cache_status = scale_factor_cache_status(
            _settings(Path("/tmp/tpch-data")), "0.1"
        )
        prompted_status = cache_status.__class__(
            scale_factor="0.1",
            directory=Path("/tmp/tpch-data/sf_0_1"),
            existing_tbl_files=(Path("/tmp/tpch-data/sf_0_1/region.tbl"),),
            missing_expected_files=(),
        )
        with patch("sys.stdin.isatty", return_value=False):
            self.assertFalse(prompt_for_cache_regeneration(prompted_status))
