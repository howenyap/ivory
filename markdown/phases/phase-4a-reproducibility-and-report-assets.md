# Phase 4a: Reproducibility and Report Assets

## Codex Prompt Contract

Implement reproducibility and report-asset generation only. Do not write the paper in this phase. Before stopping, prove both reproducibility modes separately: asset regeneration from frozen artifacts and full rerun from raw inputs or documented prerequisites.

## Objective

Package the project so the project supports two distinct reproducibility guarantees: regenerating report assets from frozen experiment artifacts, and rerunning the full experimental pipeline from raw collection inputs. This phase focuses on operational reproducibility and report-asset generation, not on paper writing itself.

## Inputs / Dependencies

- [`phase-2c-feature-dataset-assembly.md`](./phase-2c-feature-dataset-assembly.md) is complete.
- [`phase-3a-baseline-modeling.md`](./phase-3a-baseline-modeling.md) is complete.
- [`phase-3b-evaluation-ablations-error-analysis.md`](./phase-3b-evaluation-ablations-error-analysis.md) is complete.
- Final metric and evaluation artifacts exist.

## Implementation Steps

1. Add one canonical asset-regeneration command that rebuilds figures and tables from saved metric and evaluation artifacts only.
2. Add one canonical full-rerun command or documented command sequence that:
   - syncs dependencies
   - validates config
   - verifies collection prerequisites or rebuilds them explicitly
   - rebuilds features
   - reruns training and evaluation
   - regenerates figures and tables
   - writes `artifacts/report/full_rerun_manifest.json` recording completion of `collect`, `featurize`, `train`, `evaluate`, and `report_assets`
3. Create report-asset generation commands that write to:
   - `artifacts/report/figures/`
   - `artifacts/report/tables/`
4. Add a reproducibility runbook documenting:
   - environment assumptions
   - required services
   - expected runtime for asset regeneration
   - expected runtime for full rerun
   - where outputs are written
5. Ensure figure and table generation is deterministic under a fixed seed where applicable.
6. Add a lightweight final validation command if helpful, such as `report-assets verify`.

## Deliverables

- one canonical asset-regeneration command
- one canonical full-rerun command or documented command sequence
- report-asset generation command
- `artifacts/report/figures/`
- `artifacts/report/tables/`
- `artifacts/report/full_rerun_manifest.json`
- reproducibility runbook in markdown

## Verification

Run these checks from the repository root:

```bash
uv run python -m ivory.cli report-assets build
```

Expected result:
- figures and tables are generated successfully

```bash
uv run python -m ivory.cli report-assets full-rerun-check
```

Expected result:
- the full-rerun path is documented and executable
- `artifacts/report/full_rerun_manifest.json` is created
- the manifest records successful completion of `collect`, `featurize`, `train`, `evaluate`, and `report_assets`
- failure to satisfy collection prerequisites is surfaced explicitly

```bash
uv run python -c "import json; from pathlib import Path; m=json.loads(Path('artifacts/report/full_rerun_manifest.json').read_text()); assert all(m['stages'][k]=='completed' for k in ['collect','featurize','train','evaluate','report_assets']); print('ok')"
```

Expected result:
- the full-rerun manifest proves every required stage completed successfully

```bash
find artifacts/report/figures -maxdepth 1 -type f | sort
find artifacts/report/tables -maxdepth 1 -type f | sort
```

Expected result:
- the expected figure and table files are present

```bash
uv run python -m ivory.cli report-assets verify
```

Expected result:
- the command confirms all expected report assets exist
- missing inputs are surfaced as errors, not silently ignored

```bash
uv sync
uv run python -m ivory.cli report-assets build
```

Expected result:
- the project can regenerate report assets from a clean synced environment

## Definition of Done

- There is a canonical way to regenerate report figures and tables from frozen artifacts.
- There is a distinct canonical way to perform a full rerun from raw inputs.
- The rerun process is documented and scriptable.
- Report assets are generated from saved experiment outputs or deterministic reruns.
- A clean environment can reproduce the asset set without manual editing.

## Common Failure Modes

- Requiring undocumented manual notebook steps to regenerate figures.
- Producing the final paper figures once and never codifying how they were made.
- Mixing exploratory plots with final report plots in uncontrolled ways.
- Depending on hidden local state that a clean environment does not have.
- Omitting table-generation scripts while documenting only figures.
