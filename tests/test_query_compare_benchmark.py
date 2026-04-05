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
        "query formulation",
        "logical review",
    ]
    assert benchmark["defaults"]["next_phase_requirements"] == [
        "exact output comparison including row order",
        "EXPLAIN (FORMAT JSON) collection",
        "estimator scoring",
    ]

    templates = benchmark["templates"]
    assert [template["template_id"] for template in templates] == ["q3", "q5", "q10"]
    assert [template["query_instance_id"] for template in templates] == [
        "q3-q3-p0000-sf-1.0",
        "q5-q5-p0000-sf-1.0",
        "q10-q10-p0000-sf-1.0",
    ]
    assert [template["parameter_set_id"] for template in templates] == [
        "q3-p0000",
        "q5-p0000",
        "q10-p0000",
    ]

    for template in templates:
        assert template["baseline_suitability"]["status"] in {
            "accepted",
            "accepted_with_ordering_caveat",
        }
        assert template["baseline_sql"].strip()

        alternatives = template["accepted_formulations"]
        assert len(alternatives) == 3
        assert [alt["formulation_id"] for alt in alternatives] == [
            f"{template['template_id']}_alt_1",
            f"{template['template_id']}_alt_2",
            f"{template['template_id']}_alt_3",
        ]
        for alternative in alternatives:
            assert alternative["logical_review_status"] == "accepted"
            assert alternative["sql"].strip()
            assert alternative["equivalence_rationale"].strip()
            assert alternative["risk_note"].strip()
            assert len(alternative["equivalence_rationale"]) <= 240
            assert len(alternative["risk_note"]) <= 160

        rejected_formulation_ideas = template["rejected_formulation_ideas"]
        assert len(rejected_formulation_ideas) >= 3
        for rejected in rejected_formulation_ideas:
            assert rejected["idea"].strip()
            assert rejected["reason"].strip()
            assert len(rejected["reason"]) <= 120


def test_sql_files_exist_for_all_bases_and_formulations() -> None:
    expected_files = {
        "q3_base.sql",
        "q3_formulation_1_explicit_inner_join.sql",
        "q3_formulation_2_single_table_filter_ctes.sql",
        "q3_formulation_3_lineitem_preaggregation_cte.sql",
        "q5_base.sql",
        "q5_formulation_1_explicit_inner_join.sql",
        "q5_formulation_2_orders_filter_cte.sql",
        "q5_formulation_3_asia_dimension_cte.sql",
        "q10_base.sql",
        "q10_formulation_1_explicit_inner_join.sql",
        "q10_formulation_2_filtered_orders_and_lineitem_ctes.sql",
        "q10_formulation_3_join_first_cte_then_aggregate.sql",
    }
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
        template_id = template["template_id"]
        expected_sql_by_filename[f"{template_id}_base.sql"] = template["baseline_sql"]
        for index, alternative in enumerate(
            template["accepted_formulations"], start=1
        ):
            suffix = alternative["formulation_type"]
            expected_sql_by_filename[
                f"{template_id}_formulation_{index}_{suffix}.sql"
            ] = alternative["sql"]

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
        template_id="q3",
        formulation_id="q3_alt_1",
        formulation_type="explicit_inner_join",
        baseline_result=baseline,
        alternative_result=same,
    )
    mismatched = compare_results(
        template_id="q3",
        formulation_id="q3_alt_2",
        formulation_type="single_table_filter_ctes",
        baseline_result=baseline,
        alternative_result=reordered,
    )

    assert matched == ComparisonSummary(
        template_id="q3",
        formulation_id="q3_alt_1",
        formulation_type="explicit_inner_join",
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
                    "template_id": "q3",
                    "formulation_id": "q3_alt_1",
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
