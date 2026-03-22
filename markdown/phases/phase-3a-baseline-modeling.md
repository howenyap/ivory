# Phase 3a: Baseline Modeling

## Objective

Train the first full set of baseline regressors on the assembled modeling dataset and emit standard metrics. This phase should establish a reproducible baseline for all three targets before any deeper evaluation or ablation work begins.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-2c-feature-dataset-assembly.md`](./phase-2c-feature-dataset-assembly.md) is complete.
- `artifacts/features/features.parquet` exists and is validated.

## Implementation Steps

1. Load the modeling dataset from `artifacts/features/features.parquet`.
2. Prepare the three targets:
   - `planner_total_cost`
   - `planning_time_ms`
   - `execution_time_ms`
3. Implement the baseline model set:
   - dummy mean or median regressor
   - linear regression or ridge
   - random forest regressor
   - gradient boosting or histogram gradient boosting regressor
4. Implement split handling according to `configs/experiment.toml`.
5. Emit per-target metrics using the canonical metric set:
   - `MAE`
   - `RMSE`
   - `sMAPE`
   - rank correlation for execution time if already part of the contract
6. Save model outputs in stable artifact locations.
7. Add a CLI command for baseline training.
8. Keep the output format stable so Phase `3b` can extend, not replace, this work.

## Deliverables

- baseline training pipeline
- `artifacts/models/baseline_metrics.json`
- `artifacts/models/baseline_predictions.parquet`
- baseline training CLI command
- any split or training metadata needed for reproducibility

## Verification

Run these checks from the repository root after baseline training:

```bash
uv run python -m ivory.cli train baseline
```

Expected result:
- baseline training completes successfully
- metrics and prediction artifacts are created

```bash
uv run python -c "from pathlib import Path; import json; print(json.loads(Path('artifacts/models/baseline_metrics.json').read_text()).keys())"
```

Expected result:
- metrics file parses successfully
- per-target results are present

```bash
uv run python -c "import polars as pl; df = pl.read_parquet('artifacts/models/baseline_predictions.parquet'); print(df.columns); print(df.height)"
```

Expected result:
- predictions artifact exists
- prediction rows are present

```bash
uv run python -m ivory.cli train baseline --seed 4221
uv run python -m ivory.cli train baseline --seed 4221
```

Expected result:
- repeated runs with the same seed produce stable metrics within the documented tolerance

## Definition of Done

- Every baseline model trains successfully on the assembled dataset.
- Standard metrics are emitted in a stable machine-readable format.
- The split logic follows the experiment contract.
- Output artifacts are reproducible enough for downstream evaluation.
- Phase `3b` can consume the baseline outputs without changing their format.

## Common Failure Modes

- Inconsistent target naming between dataset assembly and training.
- Accidentally training on identifier columns or leakage features.
- Using a different split policy than the one frozen in the config.
- Reporting metrics in ad hoc text instead of a stable structured artifact.
- Ignoring seed control and then calling the results reproducible.

## Codex Prompt Contract

Implement only baseline training and baseline metric emission. Do not add grouped evaluation, ablations, or final plotting in this phase. Before stopping, confirm that all baseline models train, metrics are written in a stable format, and repeated runs with the same seed behave reproducibly.
