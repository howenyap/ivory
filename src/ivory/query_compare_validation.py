"""Validate exact ordered-output equivalence for query-comparison inputs."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ivory.config import load_config
from ivory.postgres import database_connection, project_postgres_config
from ivory.query_compare_benchmark import get_included_templates, load_benchmark

ROOT_DIR = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = ROOT_DIR / "query_compare" / "benchmark.json"
DEFAULT_OUTPUT_PATH = (
    ROOT_DIR
    / "query_compare"
    / "results"
    / "validation"
    / "query_compare_validation_sf_1.json"
)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class QueryExecutionResult:
    column_names: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    elapsed_ms: float


@dataclass(frozen=True)
class ComparisonSummary:
    template_id: str
    formulation_id: str
    formulation_type: str
    exact_match: bool
    baseline_order_stable: bool
    alternative_order_stable: bool
    baseline_row_count: int
    alternative_row_count: int
    baseline_elapsed_ms: float
    alternative_elapsed_ms: float
    mismatch_reason: str | None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ivory.query_compare_validation",
        description="Run exact ordered-output comparisons for query_compare inputs.",
    )
    parser.add_argument(
        "--benchmark",
        default=str(BENCHMARK_PATH),
        help="Path to the query_compare benchmark JSON artifact.",
    )
    parser.add_argument(
        "--database",
        default="tpch_sf_1",
        help="Database name to validate against. Defaults to tpch_sf_1.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to write the JSON validation summary.",
    )
    parser.add_argument(
        "--repeat-order-checks",
        type=int,
        default=3,
        help=(
            "Number of repeated executions for templates marked with an ordering "
            "caveat. Defaults to 3."
        ),
    )
    return parser


def _normalize_row(row: Any, column_names: tuple[str, ...]) -> tuple[Any, ...]:
    if isinstance(row, Mapping):
        return tuple(row[column_name] for column_name in column_names)
    return tuple(row)


def execute_query(*, database: str, sql_text: str) -> QueryExecutionResult:
    """Run a query and capture exact ordered output plus elapsed time."""
    config = load_config()
    settings = project_postgres_config(config)
    start = time.perf_counter()
    with database_connection(settings, database) as conn:
        cursor = conn.execute(sql_text)
        column_names = tuple(
            column.name for column in (cursor.description or ()) if column.name
        )
        rows = tuple(_normalize_row(row, column_names) for row in cursor.fetchall())
    elapsed_ms = (time.perf_counter() - start) * 1000
    return QueryExecutionResult(
        column_names=column_names,
        rows=rows,
        elapsed_ms=elapsed_ms,
    )


def compare_results(
    *,
    template_id: str,
    formulation_id: str,
    formulation_type: str,
    baseline_result: QueryExecutionResult,
    alternative_result: QueryExecutionResult,
    baseline_order_stable: bool = True,
    alternative_order_stable: bool = True,
) -> ComparisonSummary:
    """Return an exact ordered-output comparison summary."""
    mismatch_reason: str | None = None
    exact_match = True

    if not baseline_order_stable:
        exact_match = False
        mismatch_reason = "baseline_order_not_stable"
    elif not alternative_order_stable:
        exact_match = False
        mismatch_reason = "alternative_order_not_stable"
    elif baseline_result.column_names != alternative_result.column_names:
        exact_match = False
        mismatch_reason = "column_names"
    elif baseline_result.rows != alternative_result.rows:
        exact_match = False
        mismatch_reason = "ordered_rows"

    return ComparisonSummary(
        template_id=template_id,
        formulation_id=formulation_id,
        formulation_type=formulation_type,
        exact_match=exact_match,
        baseline_order_stable=baseline_order_stable,
        alternative_order_stable=alternative_order_stable,
        baseline_row_count=len(baseline_result.rows),
        alternative_row_count=len(alternative_result.rows),
        baseline_elapsed_ms=baseline_result.elapsed_ms,
        alternative_elapsed_ms=alternative_result.elapsed_ms,
        mismatch_reason=mismatch_reason,
    )


def is_order_stable(
    *,
    database: str,
    sql_text: str,
    reference_result: QueryExecutionResult,
    repeat_count: int,
) -> bool:
    """Return True when repeated executions keep the exact same ordered rows."""
    for _ in range(max(repeat_count - 1, 0)):
        repeated = execute_query(database=database, sql_text=sql_text)
        if (
            repeated.column_names != reference_result.column_names
            or repeated.rows != reference_result.rows
        ):
            return False
    return True


def validate_query_compare_benchmark(
    *,
    benchmark_path: Path,
    database: str,
    output_path: Path,
    repeat_order_checks: int,
) -> dict[str, Any]:
    """Run all benchmark comparisons and write a machine-readable summary."""
    benchmark = load_benchmark(benchmark_path=benchmark_path)
    comparisons: list[dict[str, Any]] = []

    for template in get_included_templates(benchmark):
        template_id = template["template_id"]
        baseline_result = execute_query(
            database=database,
            sql_text=template["baseline_sql"],
        )
        needs_order_stability_check = bool(
            template["baseline_suitability"].get("ordering_caveat")
        )
        baseline_order_stable = True
        if needs_order_stability_check:
            baseline_order_stable = is_order_stable(
                database=database,
                sql_text=template["baseline_sql"],
                reference_result=baseline_result,
                repeat_count=repeat_order_checks,
            )
        for alternative in template["accepted_formulations"]:
            alternative_result = execute_query(
                database=database,
                sql_text=alternative["sql"],
            )
            alternative_order_stable = True
            if needs_order_stability_check:
                alternative_order_stable = is_order_stable(
                    database=database,
                    sql_text=alternative["sql"],
                    reference_result=alternative_result,
                    repeat_count=repeat_order_checks,
                )
            summary = compare_results(
                template_id=template_id,
                formulation_id=alternative["formulation_id"],
                formulation_type=alternative["formulation_type"],
                baseline_result=baseline_result,
                alternative_result=alternative_result,
                baseline_order_stable=baseline_order_stable,
                alternative_order_stable=alternative_order_stable,
            )
            comparison = asdict(summary)
            comparison["rewrite_family"] = alternative.get("rewrite_family")
            comparison["structural_change"] = alternative.get("structural_change")
            comparison["selection_reason"] = alternative.get("selection_reason")
            comparison["sql_path"] = alternative.get("sql_path")
            comparisons.append(comparison)

    output = {
        "artifact_name": "query_compare_validation",
        "benchmark_path": _display_path(benchmark_path),
        "database": database,
        "screened_template_count": len(benchmark["templates"]),
        "included_template_count": len(get_included_templates(benchmark)),
        "comparison_count": len(comparisons),
        "all_exact_matches": all(item["exact_match"] for item in comparisons),
        "comparisons": comparisons,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    output = validate_query_compare_benchmark(
        benchmark_path=Path(args.benchmark),
        database=args.database,
        output_path=Path(args.output),
        repeat_order_checks=args.repeat_order_checks,
    )
    exact_matches = sum(1 for item in output["comparisons"] if item["exact_match"])
    print(
        "Query comparison validation complete: "
        f"database={output['database']} "
        f"exact_matches={exact_matches}/{output['comparison_count']} "
        f"output={args.output}"
    )
    return 0 if output["all_exact_matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
