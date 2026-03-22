# Phase 1b: Query Generation and Collection

## Objective

Generate parameterized TPC-H query instances, execute them against PostgreSQL with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, and persist the raw collection artifacts. This phase also owns collection robustness: timeout policy, retry policy, exclusion logging, and run manifests must be implemented here because they define whether the dataset is reproducible and auditable.

## Inputs / Dependencies

- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- [`phase-1a-postgres-tpch-setup.md`](./phase-1a-postgres-tpch-setup.md) is complete.
- `configs/experiment.toml` defines:
  - scale factors
  - timeout policy
  - retry count
  - run count per query
  - artifact locations
- `schemas/raw_runs.schema.json` is finalized.

## Implementation Steps

1. Implement deterministic parameter generation for all targeted TPC-H templates.
2. Assign stable identifiers for:
   - query template
   - parameter set
   - scale factor
   - run attempt
   - successful observation
3. Implement the collection command that:
   - selects scale factors and query templates
   - renders SQL for each parameter set
   - executes `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`
   - captures planner cost, planning time, execution time, row counts, and plan JSON
4. Persist the required raw artifacts:
   - `artifacts/raw/raw_runs.parquet`
   - `artifacts/raw/plans.jsonl`
   - `artifacts/raw/collection_manifest.json`
   - `artifacts/raw/exclusions.parquet`
5. Implement timeout handling so timed-out queries are logged, not silently dropped.
6. Implement retry handling with a clear maximum retry count and explicit attempt tracking.
7. Distinguish between:
   - successful runs
   - failed runs
   - timed-out runs
   - excluded runs
8. Ensure the manifest records:
   - config hash or config path
   - collection timestamp
   - scale factors included
   - templates included
   - code revision if available
   - row counts for produced artifacts
9. Keep raw collection lossless enough that downstream feature extraction does not need to requery PostgreSQL just to recover missing metadata.

## Deliverables

- collection command reachable through `ivory.cli`
- deterministic query-generation logic
- `artifacts/raw/raw_runs.parquet`
- `artifacts/raw/plans.jsonl`
- `artifacts/raw/collection_manifest.json`
- `artifacts/raw/exclusions.parquet`
- documented timeout and retry behavior

## Verification

Run these checks from the repository root after a representative collection run:

```bash
uv run python -m ivory.cli collect --limit-templates 2 --limit-params 3 --limit-scales 1
```

Expected result:
- collection completes without crashing
- raw artifacts are created in `artifacts/raw/`

```bash
uv run python -c "import polars as pl; df = pl.read_parquet('artifacts/raw/raw_runs.parquet'); print(df.columns); print(df.height)"
```

Expected result:
- required schema columns are present
- row count is greater than zero

```bash
uv run python -c "from pathlib import Path; import json; first = Path('artifacts/raw/plans.jsonl').read_text().splitlines()[0]; json.loads(first); print('ok')"
```

Expected result:
- at least one JSONL plan record parses successfully

```bash
uv run python -c "import polars as pl; print(pl.read_parquet('artifacts/raw/exclusions.parquet').columns)"
```

Expected result:
- the exclusions artifact exists even if it is empty
- the schema supports failure and timeout reasons

```bash
uv run python -m ivory.cli collect --limit-templates 1 --limit-params 1 --limit-scales 1 --force-timeout-test
```

Expected result:
- the timeout path is exercised
- the run is logged as timed out or excluded according to policy
- the collector does not silently hang

## Definition of Done

- Query generation is deterministic and reproducible.
- Raw artifacts match the contract from Phase `0b`.
- Successful runs, failures, retries, and timeouts are all auditable.
- Plan JSON is persisted separately from the tabular raw dataset.
- The collection manifest makes it possible to trace how the dataset was produced.

## Common Failure Modes

- Using unstable random sampling with no seed or manifest trace.
- Mixing logical run ids and retry attempt ids.
- Writing only successful runs and losing evidence of failures.
- Embedding plan JSON directly in the main parquet file in ways that become brittle later.
- Letting the collector partially fail without surfacing that the dataset is incomplete.

## Codex Prompt Contract

Implement the query-generation and raw-collection pipeline only. This phase includes retries, timeout handling, exclusion logging, and manifests because those are part of collection correctness. Do not implement feature extraction or ML training. Before stopping, run the collector on a small slice and prove that success, timeout, and exclusion paths are all recorded correctly.
