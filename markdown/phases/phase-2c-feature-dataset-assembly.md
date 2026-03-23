# Phase 2c: Feature Dataset Assembly

## Codex Prompt Contract

Implement only the final dataset assembly in `polars`. Do not train models in this phase. Before stopping, verify that the output has exactly one row per successful observation, that join behavior matches the frozen key contract, and that null handling and target columns match Phase `0b`.

## Objective

Join raw collection outputs, SQL structural features, and plan features into the final modeling dataset using `polars`. This phase implements the modeling grain, null-handling policy, and assembly rules already frozen in Phase `0b`. It should not train models yet.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-1b-query-generation-and-collection.md`](./phase-1b-query-generation-and-collection.md) is complete.
- [`phase-2a-sql-feature-extraction.md`](./phase-2a-sql-feature-extraction.md) is complete.
- [`phase-2b-plan-feature-extraction.md`](./phase-2b-plan-feature-extraction.md) is complete.
- `schemas/features.schema.json` is finalized.

## Implementation Steps

1. Implement the final modeling grain explicitly:
   - one row per successful observation, exactly as frozen in Phase `0b`
2. Load:
   - `artifacts/raw/sf_*/raw_runs.parquet`
   - `artifacts/features/sql_features.parquet`
   - `artifacts/features/sql_feature_exclusions.parquet`
   - `artifacts/features/plan_features.parquet`
   - `artifacts/features/plan_feature_exclusions.parquet`
3. Implement `polars` joins using the keys frozen in Phase `0b`, including SQL-feature broadcast from `query_instance_id` onto successful observation rows.
4. Ensure failed and excluded runs do not silently leak into the final modeling dataset unless the contract explicitly requires them.
5. Apply the null-handling policy frozen in Phase `0b`:
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
uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/features.parquet'); schema=json.loads(Path('schemas/features.schema.json').read_text()); assert set(schema['required']).issubset(set(df.columns)); print('ok', df.height)"
```

Expected result:
- the final dataset contains all target columns and feature columns
- row count is greater than zero

```bash
uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/features.parquet'); contract=json.loads(Path('schemas/artifact_contract.json').read_text()); allowed=set(contract['null_policy']['allowed_nullable_columns']); nulls=df.null_count().to_dicts()[0]; assert all((k in allowed) or (v==0) for k,v in nulls.items()); print('ok')"
```

Expected result:
- null counts match the documented policy
- no unexpected null spikes appear

```bash
uv run python -c "import polars as pl; from pathlib import Path; raw=pl.concat([pl.read_parquet(path) for path in sorted(Path('artifacts/raw').glob('sf_*/raw_runs.parquet'))], how='vertical').filter(pl.col('status')=='success').select('observation_id'); feat=pl.read_parquet('artifacts/features/features.parquet').select('observation_id'); raw_ids=raw['observation_id'].to_list(); feat_ids=feat['observation_id'].to_list(); assert len(raw_ids)==len(set(raw_ids)); assert len(feat_ids)==len(set(feat_ids)); assert set(raw_ids)==set(feat_ids); print('ok')"
```

Expected result:
- the final dataset contains exactly one row for each successful observation
- raw and final observation key sets match exactly with no duplicates

```bash
uv run python -m pytest tests -k dataset_assembly
```

Expected result:
- dataset assembly tests pass

## Definition of Done

- The modeling grain from Phase `0b` is implemented consistently.
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
