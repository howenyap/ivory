# Phase 2a: SQL Feature Extraction

## Codex Prompt Contract

Implement only SQL structural feature extraction from raw SQL text. Do not read PostgreSQL plan JSON and do not build the final modeling dataset in this phase. Before stopping, run the featurizer, validate schema coverage, and prove that successful plus excluded SQL feature rows exactly cover the raw query-instance inputs.

## Objective

Extract stable, interpretable structural features from the SQL text of collected queries using `sqlglot`. This phase should produce a query-instance-grain SQL feature dataset that can be broadcast onto the observation-level modeling dataset defined in Phase `0b`. It should not inspect PostgreSQL plan JSON and should not assemble the final modeling dataset yet.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-1b-query-generation-and-collection.md`](./phase-1b-query-generation-and-collection.md) is complete.
- `schemas/sql_features.schema.json` is finalized.
- `artifacts/raw/raw_runs.parquet` contains canonical query identifiers and raw SQL text.
- The modeling grain and join-key broadcast rules are already frozen in Phase `0b`.

## Implementation Steps

1. Implement a SQL parsing layer using `sqlglot`.
2. Implement the SQL feature set frozen by the contract, including at minimum:
   - join count
   - predicate count
   - aggregation presence
   - sort presence
   - limit presence
   - subquery count
   - table count
   - selected column count
3. Add stable feature names and output types that match `schemas/sql_features.schema.json`.
4. Ensure each SQL feature row carries the query-instance-level join key required by Phase `2c`.
5. Handle invalid or unparsable SQL according to the Phase `0b` contract. Records must either:
   - fail the phase immediately
   - or be emitted to `artifacts/features/sql_feature_exclusions.parquet` with explicit parse status
6. Output SQL features as a dedicated artifact, not embedded into the raw collection artifact.
7. Add a CLI command for SQL featurization.

## Deliverables

- SQL feature extraction code
- `artifacts/features/sql_features.parquet`
- `artifacts/features/sql_feature_exclusions.parquet`
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
uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/sql_features.parquet'); schema=json.loads(Path('schemas/sql_features.schema.json').read_text()); assert set(schema['required']).issubset(set(df.columns)); print('ok', df.height)"
```

Expected result:
- feature columns match the schema contract
- row count is consistent with the number of distinct query instances

```bash
uv run python -c "import polars as pl; raw=pl.read_parquet('artifacts/raw/raw_runs.parquet').filter(pl.col('status')=='success').select('query_instance_id').unique(); feat=pl.read_parquet('artifacts/features/sql_features.parquet').select('query_instance_id'); excl=pl.read_parquet('artifacts/features/sql_feature_exclusions.parquet').select('query_instance_id'); feat_ids=set(feat['query_instance_id'].to_list()); excl_ids=set(excl['query_instance_id'].to_list()); raw_ids=set(raw['query_instance_id'].to_list()); assert feat.height == len(feat_ids); assert excl.height == len(excl_ids); assert feat_ids.isdisjoint(excl_ids); assert raw_ids == (feat_ids | excl_ids); print('ok')"
```

Expected result:
- SQL feature coverage plus SQL-feature exclusions exactly equals the successful raw query-instance inputs
- feature and exclusion key sets are disjoint and duplicate-free

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
- Successful plus excluded SQL feature rows exactly cover the intended input grain.
- The output artifact is ready for Phase `2c` without further manual cleanup.

## Common Failure Modes

- Using unstable column names that drift during iteration.
- Forgetting to include a join key for downstream dataset assembly.
- Mixing query-run-level rows with query-instance-level rows without defining the grain.
- Hiding parse failures instead of surfacing them.
- Extracting plan-derived signals in this phase, which breaks phase boundaries.
