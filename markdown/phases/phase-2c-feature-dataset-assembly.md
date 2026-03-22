# Phase 2c: Feature Dataset Assembly

## Objective

Join raw collection outputs, SQL structural features, and plan features into the final modeling dataset using `polars`. This phase defines the modeling grain, final null-handling policy, and assembly rules for `features.parquet`. It should not train models yet.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-1b-query-generation-and-collection.md`](./phase-1b-query-generation-and-collection.md) is complete.
- [`phase-2a-sql-feature-extraction.md`](./phase-2a-sql-feature-extraction.md) is complete.
- [`phase-2b-plan-feature-extraction.md`](./phase-2b-plan-feature-extraction.md) is complete.
- `schemas/features.schema.json` is finalized.

## Implementation Steps

1. Define the final modeling grain explicitly:
   - one row per successful observation
   - or one row per aggregated query instance if the contract says so
2. Load:
   - `artifacts/raw/raw_runs.parquet`
   - `artifacts/features/sql_features.parquet`
   - `artifacts/features/plan_features.parquet`
3. Implement `polars` joins using the keys frozen in Phase `0b`.
4. Ensure failed and excluded runs do not silently leak into the final modeling dataset unless the contract explicitly requires them.
5. Apply the final null-handling policy:
   - fill values only when contractually justified
   - otherwise fail fast on unexpected nulls
6. Ensure target columns are present and typed correctly:
   - planner cost
   - planning time
   - execution time
7. Write `artifacts/features/features.parquet`.
8. Add a CLI command for dataset assembly.

## Deliverables

- dataset assembly code using `polars`
- `artifacts/features/features.parquet`
- dataset assembly CLI command
- any validation tests for row counts and join correctness

## Verification

Run these checks from the repository root after assembling the dataset:

```bash
uv run python -m ivory.cli featurize assemble
```

Expected result:
- dataset assembly completes successfully
- `artifacts/features/features.parquet` is created

```bash
uv run python -c "import polars as pl; df = pl.read_parquet('artifacts/features/features.parquet'); print(df.columns); print(df.height)"
```

Expected result:
- the final dataset contains all target columns and feature columns
- row count is greater than zero

```bash
uv run python -c "import polars as pl; df = pl.read_parquet('artifacts/features/features.parquet'); print(df.null_count())"
```

Expected result:
- null counts match the documented policy
- no unexpected null spikes appear

```bash
uv run python -m pytest tests -k dataset_assembly
```

Expected result:
- dataset assembly tests pass

## Definition of Done

- The modeling grain is explicit and implemented consistently.
- Joins are deterministic and do not silently drop required rows.
- Target columns are present and correctly typed.
- The final dataset matches `schemas/features.schema.json`.
- The output is immediately usable by Phase `3a`.

## Common Failure Modes

- Joining at the wrong grain and duplicating or collapsing rows.
- Accidentally including timed-out or excluded observations in the training set.
- Filling nulls without documenting why.
- Letting SQL feature keys and plan feature keys disagree.
- Treating row-count mismatches as acceptable without explanation.

## Codex Prompt Contract

Implement only the final dataset assembly in `polars`. Do not train models in this phase. Before stopping, verify row counts, join behavior, null policy, and target-column presence so the dataset is ready for baseline modeling with no manual fixes.
