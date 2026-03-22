# Phase 3b: Evaluation, Ablations, and Error Analysis

## Codex Prompt Contract

Implement grouped evaluation, ablations, and error analysis only. Do not change the baseline artifact contract from Phase `3a` unless strictly necessary, and if you must change it, update the relevant docs in the same run. Before stopping, prove that grouped splits are enforced with disjoint template sets and that every evaluation claim is backed by a saved artifact using the frozen metrics schema.

## Objective

Extend baseline modeling into defensible evaluation. This phase should add grouped-by-template generalization tests, feature-family ablations, scale-factor comparisons, and targeted error analysis. The goal is to produce the evidence needed for the paper's performance evaluation section.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-2c-feature-dataset-assembly.md`](./phase-2c-feature-dataset-assembly.md) is complete.
- [`phase-3a-baseline-modeling.md`](./phase-3a-baseline-modeling.md) is complete.
- baseline metric outputs exist in `artifacts/models/`.

## Implementation Steps

1. Implement grouped evaluation where query templates are isolated across train and test splits.
2. Add ablation runs for:
   - SQL-only features
   - plan-only features
   - combined features
   - single-scale versus multi-scale training
3. Compare learned execution-time models against PostgreSQL `Total Cost` as a non-ML baseline.
4. Produce summary tables and machine-readable evaluation outputs under `artifacts/evaluation/`.
5. Implement error analysis for the worst-performing templates, operators, or scale factors.
6. Save `artifacts/evaluation/grouped_split_manifest.json` that records the exact train/test template split for grouped evaluation and a `split_hash` derived from that split.
7. Generate at least the core plots required by the paper and video:
   - model comparison
   - grouped generalization
   - ablation comparison
   - error distribution or worst-case analysis
8. Emit grouped metrics in the exact structure required by `schemas/grouped_metrics.schema.json`, including the same `split_hash` used in the split manifest.
9. Add or reuse a schema-validation command that validates grouped metrics against `schemas/grouped_metrics.schema.json`.
10. Keep plotting and evaluation steps scriptable rather than notebook-only.

## Deliverables

- grouped evaluation pipeline
- `artifacts/evaluation/grouped_metrics.json`
- `artifacts/evaluation/grouped_split_manifest.json`
- `artifacts/evaluation/ablations.json`
- `artifacts/evaluation/error_analysis.parquet`
- evaluation plots under `artifacts/report/figures/`
- evaluation CLI command or subcommands

## Verification

Run these checks from the repository root after the evaluation pass:

```bash
uv run python -m ivory.cli evaluate grouped
```

Expected result:
- grouped evaluation completes successfully
- grouped metrics artifact is created

```bash
uv run python -c "import json; from pathlib import Path; m=json.loads(Path('artifacts/evaluation/grouped_split_manifest.json').read_text()); data=json.loads(Path('artifacts/evaluation/grouped_metrics.json').read_text()); train=set(m['train_template_ids']); test=set(m['test_template_ids']); assert train.isdisjoint(test); assert m['split_hash'] == data['grouped_split']['split_hash']; print('ok')"
```

Expected result:
- grouped split metadata exists
- train and test template sets are disjoint
- grouped metrics are tied to the same split via matching `split_hash`

```bash
uv run python -m ivory.cli evaluate ablations
```

Expected result:
- ablation outputs are created
- SQL-only, plan-only, combined-feature, and scale-factor comparisons are present

```bash
uv run python -m ivory.cli validate-metrics grouped --schema schemas/grouped_metrics.schema.json --artifact artifacts/evaluation/grouped_metrics.json
```

Expected result:
- grouped metrics pass full schema validation

```bash
uv run python -c "from pathlib import Path; import json; data=json.loads(Path('artifacts/evaluation/ablations.json').read_text()); assert {'sql_only','plan_only','combined','single_scale_vs_multi_scale'}.issubset(set(data)); print('ok')"
```

Expected result:
- ablation file parses successfully with the full required ablation matrix

```bash
uv run python -c "import polars as pl; df = pl.read_parquet('artifacts/evaluation/error_analysis.parquet'); print(df.columns); print(df.height)"
```

Expected result:
- error analysis rows are present
- diagnostic columns exist

```bash
find artifacts/report/figures -maxdepth 1 -type f | sort
```

Expected result:
- the expected plots are present as files

## Definition of Done

- Grouped-by-template evaluation is implemented and enforced correctly.
- The main ablation comparisons are reproducible and saved.
- Error analysis identifies concrete model weaknesses.
- Plots and tables are generated from code, not manually edited.
- Train/test template leakage is auditable and ruled out by saved split metadata.
- The project now has defensible evidence for the evaluation section of the paper.

## Common Failure Modes

- Accidentally leaking the same template into both train and test splits.
- Calling a comparison an ablation without actually isolating one variable.
- Generating plots manually or in a notebook without scriptable reproduction.
- Saving only images and losing the underlying structured results.
- Performing error analysis only qualitatively without artifact outputs.
