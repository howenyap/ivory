# Phase 3a: Baseline Modeling

## Codex Prompt Contract

Implement only baseline training and baseline metric emission. Do not add grouped evaluation, ablations, or final plotting in this phase. Before stopping, confirm that all baseline models train, metrics match the frozen schema, the training manifest records leakage-relevant metadata, and repeated runs with the same seed produce identical metrics artifacts.

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
   - rank correlation for `execution_time_ms`
6. Emit metrics in the exact structure required by `schemas/baseline_metrics.schema.json`.
7. Save model outputs in stable artifact locations.
8. Save `artifacts/models/training_manifest.json` with:
   - selected feature columns
   - excluded columns
   - final model input columns per model family after preprocessing
   - target names
   - split config
   - seed
   - model family names
   - any preprocessing choices
9. Add a CLI command for baseline training.
10. Keep the output format stable so Phase `3b` can extend, not replace, this work.
11. Add or reuse a schema-validation command that validates metrics artifacts against `schemas/baseline_metrics.schema.json`.

## Deliverables

- baseline training pipeline
- `artifacts/models/baseline_metrics.json`
- `artifacts/models/baseline_predictions.parquet`
- `artifacts/models/training_manifest.json`
- baseline training CLI command
- split and training metadata needed for reproducibility

## Verification

Run these checks from the repository root after baseline training:

```bash
uv run python -m ivory.cli train baseline
```

Expected result:
- baseline training completes successfully
- metrics and prediction artifacts are created

```bash
uv run python -m ivory.cli validate-metrics baseline --schema schemas/baseline_metrics.schema.json --artifact artifacts/models/baseline_metrics.json
```

Expected result:
- the metrics artifact passes full schema validation

```bash
uv run python -c "import polars as pl; df = pl.read_parquet('artifacts/models/baseline_predictions.parquet'); print(df.columns); print(df.height)"
```

Expected result:
- predictions artifact exists
- prediction rows are present

```bash
uv run python -m ivory.cli train baseline --seed 4221
cp artifacts/models/baseline_metrics.json /tmp/ivory_baseline_metrics_1.json
uv run python -m ivory.cli train baseline --seed 4221
diff -u /tmp/ivory_baseline_metrics_1.json artifacts/models/baseline_metrics.json
```

Expected result:
- repeated runs with the same seed produce identical metrics artifacts

```bash
uv run python -c "import json; from pathlib import Path; m=json.loads(Path('artifacts/models/training_manifest.json').read_text()); assert 'selected_features' in m and 'excluded_columns' in m and 'final_model_input_columns_per_model' in m and 'split' in m and 'seed' in m; print('ok')"
```

Expected result:
- the training manifest exists
- leakage-relevant metadata is auditable, including final per-model input columns after preprocessing

## Definition of Done

- Every baseline model trains successfully on the assembled dataset.
- Standard metrics are emitted in a stable machine-readable format.
- The split logic follows the experiment contract.
- The selected features and excluded columns are auditable.
- Output artifacts are reproducible enough for downstream evaluation.
- Phase `3b` can consume the baseline outputs without changing their format.

## Common Failure Modes

- Inconsistent target naming between dataset assembly and training.
- Accidentally training on identifier columns or leakage features.
- Using a different split policy than the one frozen in the config.
- Reporting metrics in ad hoc text instead of a stable structured artifact.
- Ignoring seed control and then calling the results reproducible.
