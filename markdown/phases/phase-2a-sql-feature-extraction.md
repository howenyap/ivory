# Phase 2a: SQL Feature Extraction

## Objective

Extract stable, interpretable structural features from the SQL text of collected queries using `sqlglot`. This phase should produce a SQL feature dataset that can be joined with raw collection outputs later. It should not inspect PostgreSQL plan JSON and should not assemble the final modeling dataset yet.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-1b-query-generation-and-collection.md`](./phase-1b-query-generation-and-collection.md) is complete.
- `schemas/sql_features.schema.json` is finalized.
- `artifacts/raw/raw_runs.parquet` contains canonical query identifiers and raw SQL text.

## Implementation Steps

1. Implement a SQL parsing layer using `sqlglot`.
2. Decide and freeze the SQL feature set, including at minimum:
   - join count
   - predicate count
   - aggregation presence
   - sort presence
   - limit presence
   - subquery count
   - table count
   - selected column count
3. Add stable feature names and output types that match `schemas/sql_features.schema.json`.
4. Ensure each SQL feature row carries the join key needed by Phase `2c`.
5. Implement predictable behavior for invalid or unparsable SQL:
   - fail fast if the raw dataset is expected to be valid only
   - or record parse status explicitly if recovery is part of the contract
6. Output SQL features as a dedicated artifact, not embedded into the raw collection artifact.
7. Add a CLI command for SQL featurization.

## Deliverables

- SQL feature extraction code
- `artifacts/features/sql_features.parquet`
- SQL featurization CLI command
- any tests or snapshots needed to prove feature correctness

## Verification

Run these checks from the repository root after featurizing a representative dataset:

```bash
uv run python -m ivory.cli featurize sql
```

Expected result:
- SQL featurization completes successfully
- `artifacts/features/sql_features.parquet` is created

```bash
uv run python -c "import polars as pl; df = pl.read_parquet('artifacts/features/sql_features.parquet'); print(df.columns); print(df.height)"
```

Expected result:
- feature columns match the schema contract
- row count is consistent with the number of distinct query instances

```bash
uv run python -c "import polars as pl; raw = pl.read_parquet('artifacts/raw/raw_runs.parquet'); feat = pl.read_parquet('artifacts/features/sql_features.parquet'); print(raw.select('query_instance_id').n_unique(), feat.select('query_instance_id').n_unique())"
```

Expected result:
- SQL feature keys align with raw query identifiers

```bash
uv run python -m pytest tests -k sql_feature
```

Expected result:
- SQL feature tests pass

## Definition of Done

- SQL structural features are extracted deterministically.
- Feature names and types match the schema contract.
- Output rows are keyed correctly for later joins.
- Invalid SQL handling is explicit rather than accidental.
- The output artifact is ready for Phase `2c` without further manual cleanup.

## Common Failure Modes

- Using unstable column names that drift during iteration.
- Forgetting to include a join key for downstream dataset assembly.
- Mixing query-run-level rows with query-instance-level rows without defining the grain.
- Hiding parse failures instead of surfacing them.
- Extracting plan-derived signals in this phase, which breaks phase boundaries.

## Codex Prompt Contract

Implement only SQL structural feature extraction from raw SQL text. Do not read PostgreSQL plan JSON and do not build the final modeling dataset in this phase. Before stopping, run the featurizer, inspect the output schema, and prove that query identifiers line up with the raw dataset.
