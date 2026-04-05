from __future__ import annotations

import json
from pathlib import Path

import ivory.query_compare_validation as query_compare_validation
from ivory.query_compare_validation import (
    ComparisonSummary,
    QueryExecutionResult,
    _display_path,
    _normalize_row,
    compare_results,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT_DIR / "query_compare" / "benchmark.json"
SQL_DIR = ROOT_DIR / "query_compare" / "sql"


def test_query_compare_benchmark_has_expected_shape() -> None:
    benchmark = json.loads(BENCHMARK_PATH.read_text())

    assert benchmark["artifact_name"] == "query_compare_benchmark"
    assert benchmark["scope"] == "query_formulation_comparison_only"
    assert benchmark["defaults"]["scale_factor"] == 1.0
    assert benchmark["defaults"]["equivalence_standard"] == (
        "same columns, same values, same row multiplicities, and same row ordering "
        "for the same parameter instance and database state"
    )
    assert benchmark["defaults"]["completed_phases"] == [
        "template screening",
        "query formulation",
        "logical review",
        "exact output comparison including row order",
        "EXPLAIN (FORMAT JSON) collection",
        "estimator scoring",
    ]
    assert benchmark["defaults"]["next_phase_requirements"] == [
        "analyze-enabled runtime comparison",
        "repo-wide verification",
    ]

    templates = benchmark["templates"]
    assert {template["template_id"] for template in templates} == {
        f"q{index}" for index in range(1, 23)
    }
    assert {
        template["template_id"]
        for template in templates
        if template["template_status"] == "included"
    } == {"q2", "q5", "q7", "q8", "q9", "q11", "q13", "q15", "q16", "q17", "q19"}

    for template in templates:
        assert template["template_status"] in {
            "included",
            "excluded_after_screening",
            "attempted_but_dropped",
        }
        assert template["screening_rationale"].strip()
        assert template["rewrite_budget_target"]
        assert isinstance(template["accepted_rewrite_families"], list)
        assert isinstance(template["rejected_formulations"], list)
        assert template["docker_equivalence_validation"]["status"].strip()

        alternatives = template["accepted_formulations"]
        if template["template_status"] == "included":
            assert template["baseline_suitability"]["status"] in {
                "accepted",
                "accepted_with_ordering_caveat",
            }
            assert template["baseline_sql"].strip()
            assert template["baseline_sql_path"].startswith("query_compare/sql/")
            assert 1 <= len(alternatives) <= 3
            assert [alt["formulation_id"] for alt in alternatives] == [
                f"{template['template_id']}_alt_{index}"
                for index in range(1, len(alternatives) + 1)
            ]
            assert template["accepted_rewrite_families"] == [
                alt["rewrite_family"] for alt in alternatives
            ]
            for alternative in alternatives:
                assert alternative["logical_review_status"] == "accepted"
                assert alternative["rewrite_family"].strip()
                assert alternative["sql"].strip()
                assert alternative["sql_path"].startswith("query_compare/sql/")
                assert alternative["equivalence_rationale"].strip()
                assert alternative["structural_change"].strip()
                assert alternative["selection_reason"].strip()
                assert len(alternative["exclusion_guardrails"]) >= 1
        else:
            assert alternatives == []
            assert template["accepted_rewrite_families"] == []
            assert template["exclusion_reason"].strip()

        rejected_formulations = template["rejected_formulations"]
        assert len(rejected_formulations) >= 1
        for rejected in rejected_formulations:
            assert rejected["rewrite_family"].strip()
            assert rejected["rejection_reason"].strip()
            assert (
                rejected.get("equivalence_concern", "").strip()
                or rejected.get("planner_reason", "").strip()
            )


def test_sql_files_exist_for_all_bases_and_formulations() -> None:
    benchmark = json.loads(BENCHMARK_PATH.read_text())

    expected_files = {
        Path(template["baseline_sql_path"]).name
        for template in benchmark["templates"]
        if template["template_status"] == "included"
    }
    for template in benchmark["templates"]:
        if template["template_status"] != "included":
            continue
        for alternative in template["accepted_formulations"]:
            expected_files.add(Path(alternative["sql_path"]).name)

    actual_files = {path.name for path in SQL_DIR.iterdir() if path.is_file()}

    assert actual_files == expected_files

    for filename in expected_files:
        contents = (SQL_DIR / filename).read_text()
        assert contents.strip()
        assert contents.rstrip().endswith(";")


def test_sql_files_match_vetted_benchmark_queries_exactly() -> None:
    benchmark = json.loads(BENCHMARK_PATH.read_text())

    expected_sql_by_filename: dict[str, str] = {}
    for template in benchmark["templates"]:
        if template["template_status"] != "included":
            continue
        expected_sql_by_filename[Path(template["baseline_sql_path"]).name] = template[
            "baseline_sql"
        ]
        for alternative in template["accepted_formulations"]:
            expected_sql_by_filename[Path(alternative["sql_path"]).name] = alternative[
                "sql"
            ]

    for filename, expected_sql in expected_sql_by_filename.items():
        actual_sql = (SQL_DIR / filename).read_text()
        assert actual_sql == expected_sql


def test_compare_results_detects_exact_match_and_ordered_row_mismatch() -> None:
    baseline = QueryExecutionResult(
        column_names=("a", "b"),
        rows=((1, "x"), (2, "y")),
        elapsed_ms=1.0,
    )
    same = QueryExecutionResult(
        column_names=("a", "b"),
        rows=((1, "x"), (2, "y")),
        elapsed_ms=2.0,
    )
    reordered = QueryExecutionResult(
        column_names=("a", "b"),
        rows=((2, "y"), (1, "x")),
        elapsed_ms=3.0,
    )

    matched = compare_results(
        template_id="q9",
        formulation_id="q9_alt_1",
        formulation_type="filtered_part_island",
        baseline_result=baseline,
        alternative_result=same,
    )
    mismatched = compare_results(
        template_id="q9",
        formulation_id="q9_alt_2",
        formulation_type="profit_rows_derived_table",
        baseline_result=baseline,
        alternative_result=reordered,
    )

    assert matched == ComparisonSummary(
        template_id="q9",
        formulation_id="q9_alt_1",
        formulation_type="filtered_part_island",
        exact_match=True,
        baseline_order_stable=True,
        alternative_order_stable=True,
        baseline_row_count=2,
        alternative_row_count=2,
        baseline_elapsed_ms=1.0,
        alternative_elapsed_ms=2.0,
        mismatch_reason=None,
    )
    assert mismatched.exact_match is False
    assert mismatched.mismatch_reason == "ordered_rows"


def test_normalize_row_uses_column_order_for_mapping_rows() -> None:
    row = {"b": "y", "a": 2}

    assert _normalize_row(row, ("a", "b")) == (2, "y")


def test_display_path_handles_repo_relative_and_external_paths() -> None:
    repo_relative = ROOT_DIR / "query_compare" / "benchmark.json"
    external = Path("/tmp/outside-benchmark.json")

    assert _display_path(repo_relative) == "query_compare/benchmark.json"
    assert _display_path(external) == "/tmp/outside-benchmark.json"


def test_main_returns_nonzero_when_any_formulation_mismatches(
    monkeypatch, tmp_path: Path
) -> None:
    output_path = tmp_path / "validation.json"

    def fake_validate_benchmark(**_: object) -> dict[str, object]:
        return {
            "artifact_name": "query_compare_validation",
            "database": "tpch_sf_1",
            "comparison_count": 1,
            "all_exact_matches": False,
            "comparisons": [
                {
                    "template_id": "q9",
                    "formulation_id": "q9_alt_1",
                    "exact_match": False,
                }
            ],
        }

    monkeypatch.setattr(
        query_compare_validation,
        "validate_query_compare_benchmark",
        fake_validate_benchmark,
    )

    exit_code = query_compare_validation.main(
        ["--database", "tpch_sf_1", "--output", str(output_path)]
    )

    assert exit_code == 1
