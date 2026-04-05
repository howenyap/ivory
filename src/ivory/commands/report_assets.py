"""Report asset generation commands for phase 4a."""

from __future__ import annotations

import argparse


def register_report_assets_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the report-assets command tree."""
    report_parser = subparsers.add_parser(
        "report-assets",
        help="Generate figures and tables for the paper.",
        description="Report asset generation commands for phase 4a.",
    )
    report_subparsers = report_parser.add_subparsers(
        dest="report_assets_command", metavar="report-assets-command"
    )

    build_parser = report_subparsers.add_parser(
        "build",
        help="Generate all figures and tables from frozen evaluation artifacts.",
        description=(
            "Reads from artifacts/models/ and artifacts/evaluation/, "
            "writes figures and tables to artifacts/report/."
        ),
    )
    build_parser.set_defaults(handler=_handle_build)

    verify_parser = report_subparsers.add_parser(
        "verify",
        help="Verify all expected report assets exist.",
        description="Check that all expected figures and tables have been generated.",
    )
    verify_parser.set_defaults(handler=_handle_verify)

    full_rerun_parser = report_subparsers.add_parser(
        "full-rerun-check",
        help="Write full_rerun_manifest.json recording stage completion.",
        description=(
            "Checks sentinel artifacts for each pipeline stage and writes "
            "artifacts/report/full_rerun_manifest.json."
        ),
    )
    full_rerun_parser.set_defaults(handler=_handle_full_rerun_check)


def _handle_build(args: argparse.Namespace) -> int:
    from ivory.report_assets import build_report_assets

    summary = build_report_assets()
    print(
        f"Report assets built: "
        f"{len(summary['figures'])} figures, "
        f"{len(summary['tables'])} tables"
    )
    print(f"  figures -> {summary['figures_dir']}")
    print(f"  tables  -> {summary['tables_dir']}")
    return 0


def _handle_verify(args: argparse.Namespace) -> int:
    from ivory.report_assets import verify_report_assets

    missing = verify_report_assets()
    if missing:
        print("Missing report assets:")
        for path in missing:
            print(f"  - {path}")
        return 1
    print("All expected report assets present.")
    return 0


def _handle_full_rerun_check(args: argparse.Namespace) -> int:
    from ivory.report_assets import write_full_rerun_manifest

    manifest = write_full_rerun_manifest()
    for stage, status in manifest["stages"].items():
        print(f"  {stage}: {status}")
    all_complete = all(v == "completed" for v in manifest["stages"].values())
    if not all_complete:
        print("Warning: some stages are not complete.")
        return 1
    print("Full rerun manifest written.")
    return 0
