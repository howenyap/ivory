# Phase 2b: Plan Feature Extraction

## Codex Prompt Contract

Implement only the PostgreSQL plan-feature extractor and its dedicated output artifact. Do not parse SQL text and do not assemble the final modeling dataset. Before stopping, run the featurizer, confirm schema stability, and verify that successful plus excluded plan-feature rows exactly cover the raw observation identifiers.

## Objective

Extract stable summary features from PostgreSQL JSON execution plans. This phase should traverse plan trees, aggregate node-level signals into interpretable features, and persist them in a dedicated observation-level artifact keyed for later joins. It should not parse SQL text and should not assemble the final modeling dataset yet.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-1b-query-generation-and-collection.md`](./phase-1b-query-generation-and-collection.md) is complete.
- `schemas/plan_features.schema.json` is finalized.
- `artifacts/raw/plans.jsonl` exists and is keyed consistently with raw runs on `observation_id`.

## Implementation Steps

1. Implement a plan parser that can read `artifacts/raw/plans.jsonl`.
2. Traverse plan trees recursively and extract at minimum:
   - node-type counts
   - plan depth
   - scan operator counts
   - join operator counts
   - aggregate and sort operator counts
   - estimated rows summaries
   - estimated width summaries
   - node-level cost summaries
3. Freeze aggregation rules so repeated runs produce the same feature columns.
4. Attach the canonical observation-level join key required by Phase `2c`.
5. Handle malformed plan records according to the Phase `0b` contract. Records must either:
   - fail the phase immediately
   - or be emitted to `artifacts/features/plan_feature_exclusions.parquet` with explicit parse status
6. Output the plan features separately as `artifacts/features/plan_features.parquet`.
7. Add a CLI command for plan featurization.

## Deliverables

- plan feature extraction code
- `artifacts/features/plan_features.parquet`
- `artifacts/features/plan_feature_exclusions.parquet`
- plan featurization CLI command
- tests or snapshots for known plan shapes

## Verification

Run these checks from the repository root after featurizing a representative dataset:

```bash
uv run python -m ivory.cli featurize plan
```

Expected result:
- plan featurization completes successfully
- `artifacts/features/plan_features.parquet` is created

```bash
uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/plan_features.parquet'); schema=json.loads(Path('schemas/plan_features.schema.json').read_text()); assert set(schema['required']).issubset(set(df.columns)); print('ok', df.height)"
```

Expected result:
- feature columns match the schema contract
- row count is greater than zero

```bash
uv run python -c "import polars as pl; raw=pl.read_parquet('artifacts/raw/raw_runs.parquet').filter(pl.col('status')=='success').select('observation_id').unique(); feat=pl.read_parquet('artifacts/features/plan_features.parquet').select('observation_id'); excl=pl.read_parquet('artifacts/features/plan_feature_exclusions.parquet').select('observation_id'); feat_ids=set(feat['observation_id'].to_list()); excl_ids=set(excl['observation_id'].to_list()); raw_ids=set(raw['observation_id'].to_list()); assert feat.height == len(feat_ids); assert excl.height == len(excl_ids); assert feat_ids.isdisjoint(excl_ids); assert raw_ids == (feat_ids | excl_ids); print('ok')"
```

Expected result:
- plan feature coverage plus plan-feature exclusions exactly equals the successful raw observation inputs
- feature and exclusion key sets are disjoint and duplicate-free

```bash
uv run python -m pytest tests -k plan_feature
```

Expected result:
- plan feature tests pass

## Definition of Done

- Plan feature extraction is deterministic and schema-stable.
- Plan features carry the correct downstream join key.
- Aggregation rules are documented and implemented.
- Malformed-plan handling is explicit.
- Successful plus excluded plan-feature rows exactly cover the intended raw observation inputs.
- The output artifact is ready for Phase `2c` with no manual intervention.

## Common Failure Modes

- Flattening plan trees inconsistently across different node shapes.
- Using plan keys that vary across PostgreSQL versions without normalizing them.
- Losing the observation-level join key.
- Allowing malformed JSON to disappear silently.
- Combining plan and SQL features in the same artifact before the assembly phase.
