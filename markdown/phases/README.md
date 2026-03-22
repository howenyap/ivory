# Phase Guides

These files turn the project plan into operational contracts for repeated Codex runs. Each run should target exactly one phase guide, implement only that scope, and stop only after the listed verification checks pass.

## Execution Order

1. [Phase 0a: Bootstrap](./phase-0a-bootstrap.md)
2. [Phase 0b: Experiment Contract](./phase-0b-experiment-contract.md)
3. [Phase 1a: PostgreSQL + TPC-H Setup](./phase-1a-postgres-tpch-setup.md)
4. [Phase 1b: Query Generation and Collection](./phase-1b-query-generation-and-collection.md)
5. [Phase 2a: SQL Feature Extraction](./phase-2a-sql-feature-extraction.md)
6. [Phase 2b: Plan Feature Extraction](./phase-2b-plan-feature-extraction.md)
7. [Phase 2c: Feature Dataset Assembly](./phase-2c-feature-dataset-assembly.md)
8. [Phase 3a: Baseline Modeling](./phase-3a-baseline-modeling.md)
9. [Phase 3b: Evaluation, Ablations, and Error Analysis](./phase-3b-evaluation-ablations-error-analysis.md)
10. [Phase 4a: Reproducibility and Report Assets](./phase-4a-reproducibility-and-report-assets.md)
11. [Phase 4b: Paper and Video Packaging](./phase-4b-paper-and-video-packaging.md)

## Dependency Map

| Phase | Prerequisites | Main Outputs | Used By |
| --- | --- | --- | --- |
| `0a` | None | `pyproject.toml`, `uv.lock`, `src/ivory/`, CLI skeleton, config loader skeleton | `0b` onward |
| `0b` | `0a` | `configs/experiment.toml`, schema docs, `schemas/artifact_contract.json`, metric schemas | `1a`, `1b`, `2a`, `2b`, `2c`, `3a`, `3b`, `4a` |
| `1a` | `0a`, `0b` | Dockerized PostgreSQL, loaded TPC-H datasets, DB health checks | `1b` |
| `1b` | `0a`, `0b`, `1a` | Raw runs dataset with SQL text, plan JSONL, manifests, failure logs | `2a`, `2b`, `2c`, `3b` |
| `2a` | `0a`, `0b`, `1b` | SQL structural feature extractor, SQL feature dataset, SQL feature exclusions | `2c`, `3b` |
| `2b` | `0a`, `0b`, `1b` | Plan feature extractor, plan feature dataset, plan feature exclusions | `2c`, `3b` |
| `2c` | `0b`, `1b`, `2a`, `2b` | `features.parquet`, modeling-ready schema contract | `3a`, `3b`, `4a` |
| `3a` | `0b`, `2c` | Baseline models, metrics, training manifest | `3b`, `4a`, `4b` |
| `3b` | `0b`, `2c`, `3a` | Ablation tables, grouped evaluation, split manifest, error analysis plots | `4a`, `4b` |
| `4a` | `0b`, `2c`, `3a`, `3b` | Reproduction commands, full rerun manifest, final figures, final tables | `4b` |
| `4b` | `4a` | Paper outline, section-to-artifact mapping, video flow, submission checklist | Final submission |

## Canonical Project Conventions

- Python runtime: `3.14`
- Environment and package manager: `uv`
- Dataframe engine: `polars`
- Modeling library: `scikit-learn`
- SQL parsing: `sqlglot`
- Package name: `ivory`
- Canonical CLI entrypoint: `uv run python -m ivory.cli <command>`
- Canonical config path: `configs/experiment.toml`
- Canonical artifact root: `artifacts/`
- Canonical modeling grain: one row per successful observation
- Canonical join keys are frozen in Phase `0b`; later phases must implement them, not redefine them

## Expected Artifact Layout

The guides assume this high-level layout once the project is implemented:

```text
artifacts/
  raw/
    raw_runs.parquet
    plans.jsonl
    collection_manifest.json
    exclusions.parquet
  features/
    sql_features.parquet
    sql_feature_exclusions.parquet
    plan_features.parquet
    plan_feature_exclusions.parquet
    features.parquet
  models/
    baseline_metrics.json
    baseline_predictions.parquet
    training_manifest.json
  evaluation/
    grouped_metrics.json
    grouped_split_manifest.json
    ablations.json
    error_analysis.parquet
  report/
    figures/
    tables/
    full_rerun_manifest.json
configs/
  experiment.toml
schemas/
  artifact_contract.json
  raw_runs.schema.json
  sql_features.schema.json
  plan_features.schema.json
  features.schema.json
  baseline_metrics.schema.json
  grouped_metrics.schema.json
src/
  ivory/
```

## How To Run A Codex Loop

1. Open the relevant phase file in `markdown/phases/`.
2. Treat that file as the contract for the run.
3. Implement only the scope in `Implementation Steps`.
4. Produce every item in `Deliverables`.
5. Run every command or check listed in `Verification`.
6. Stop if any verification step fails or any Definition of Done item is unmet.
7. Do not start the next phase until the current phase gate passes.

## Rules For Updating These Guides

- If implementation reveals that a contract is incomplete or impossible, update the relevant phase guide before moving on.
- If an interface changes, update every downstream guide that depends on it in the same Codex run.
- Keep file names and CLI commands stable once a later phase depends on them.
- Do not loosen verification criteria just to make a failing phase appear complete.
- If a phase guide says a decision is frozen in `0b`, later phase guides must treat it as an input, not a choice.
