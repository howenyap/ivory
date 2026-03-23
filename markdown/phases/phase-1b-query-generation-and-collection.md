# Phase 1b: Query Generation and Collection

## Codex Prompt Contract

Implement the query-generation and raw-collection pipeline only. This phase includes retries, timeout handling, exclusion logging, and manifests because those are part of collection correctness. Do not implement feature extraction or ML training. Before stopping, run the collector on a small slice and prove that success, timeout, retry, exclusion, and plan-to-raw identifier coverage are all recorded correctly.

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
   Default the main collection run to `50` parameter sets per template per scale factor unless the CLI explicitly narrows it for a smoke slice.
2. Implement the exact identifier contract frozen in Phase `0b`. At minimum, every successful collected run must carry:
   - `template_id`
   - `parameter_set_id`
   - `query_instance_id`
   - `scale_factor`
   - `run_attempt_id`
   - `observation_id`
3. Ensure `plans.jsonl` carries the same `observation_id` as `raw_runs.parquet` for every successful collected observation.
4. Implement the collection command that:
   - selects scale factors and query templates
   - renders SQL for each parameter set
   - executes `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`
   - captures raw SQL text, planner cost, planning time, execution time, row counts, and plan JSON
5. Persist the required raw artifacts:
   - `artifacts/raw/sf_<scale_factor>/raw_runs.parquet`
   - `artifacts/raw/sf_<scale_factor>/plans.jsonl`
   - `artifacts/raw/collection_manifest.json`
   - `artifacts/raw/sf_<scale_factor>/exclusions.parquet`
6. Implement timeout handling so timed-out queries are logged, not silently dropped.
7. Implement retry handling with a clear maximum retry count and explicit attempt tracking.
8. Distinguish between:
   - successful runs
   - failed runs
   - timed-out runs
   - excluded runs
9. Ensure `raw_runs.parquet` and `exclusions.parquet` expose explicit status fields such as:
   - `status`
   - `failure_reason`
   - `attempt_number`
   - `is_excluded`
10. Ensure the manifest records:
   - config hash or config path
   - collection timestamp
   - scale factors included
   - templates included
   - code revision if available
   - row counts for produced artifacts
    - identifier coverage for successful rows and plan records
11. Keep raw collection lossless enough that downstream feature extraction does not need to requery PostgreSQL just to recover missing metadata.

## Deliverables

- collection command reachable through `ivory.cli`
- deterministic query-generation logic
- `artifacts/raw/sf_<scale_factor>/raw_runs.parquet`
- `artifacts/raw/sf_<scale_factor>/plans.jsonl`
- `artifacts/raw/collection_manifest.json`
- `artifacts/raw/sf_<scale_factor>/exclusions.parquet`
- documented timeout and retry behavior
- explicit status and identifier fields matching the Phase `0b` contract
- raw SQL text persisted in `raw_runs.parquet` for downstream SQL featurization

## Verification

Run these checks from the repository root after a representative collection run:

```bash
uv run python -m ivory.cli collect --limit-templates 2 --limit-params 3 --limit-scales 1
```

Expected result:
- collection completes without crashing
- raw artifacts are created in `artifacts/raw/`

```bash
uv run python -c "import polars as pl; from pathlib import Path; paths=sorted(Path('artifacts/raw').glob('sf_*/raw_runs.parquet')); df=pl.concat([pl.read_parquet(path) for path in paths], how='vertical'); assert 'sql_text' in df.columns; assert df.filter(pl.col('status')=='success').select(pl.col('sql_text').is_not_null().all()).item(); print(df.columns, df.height)"
```

Expected result:
- required schema columns are present
- successful rows retain raw SQL text
- row count is greater than zero

```bash
uv run python -c "from pathlib import Path; import json; first=next(Path('artifacts/raw').glob('sf_*/plans.jsonl')).read_text().splitlines()[0]; json.loads(first); print('ok')"
```

Expected result:
- at least one JSONL plan record parses successfully

```bash
uv run python -c "import polars as pl; from pathlib import Path; paths=sorted(Path('artifacts/raw').glob('sf_*/exclusions.parquet')); df=pl.concat([pl.read_parquet(path) for path in paths], how='vertical') if paths else pl.DataFrame(schema={'status':pl.String,'failure_reason':pl.String,'attempt_number':pl.Int64,'is_excluded':pl.Boolean}); required={'status','failure_reason','attempt_number','is_excluded'}; assert required.issubset(set(df.columns)); print('ok')"
```

Expected result:
- the exclusions artifact exists even if it is empty
- the schema supports failure and timeout reasons

```bash
uv run python -m ivory.cli collect --limit-templates 1 --limit-params 1 --limit-scales 1 --timeout-ms 1
```

Expected result:
- the timeout path is exercised
- the run is logged as timed out or excluded according to policy
- the collector does not silently hang

```bash
uv run python -c "import polars as pl, json; from pathlib import Path; raw_paths=sorted(Path('artifacts/raw').glob('sf_*/raw_runs.parquet')); raw=pl.concat([pl.read_parquet(path) for path in raw_paths], how='vertical').filter(pl.col('status')=='success'); raw_ids=raw['observation_id'].to_list(); plan_ids=[json.loads(line)['observation_id'] for plan_path in sorted(Path('artifacts/raw').glob('sf_*/plans.jsonl')) for line in plan_path.read_text().splitlines() if line.strip()]; assert len(raw_ids)==len(set(raw_ids)); assert len(plan_ids)==len(set(plan_ids)); assert set(raw_ids)==set(plan_ids); print('ok')"
```

Expected result:
- every successful raw row has exactly one matching plan record

```bash
uv run python -c "import json; from pathlib import Path; m=json.loads(Path('artifacts/raw/collection_manifest.json').read_text()); assert 'identifier_coverage' in m; assert 'artifacts' in m; print('ok')"
```

Expected result:
- the manifest records identifier coverage and produced artifact metadata

## Definition of Done

- Query generation is deterministic and reproducible.
- Raw artifacts match the contract from Phase `0b`.
- Successful runs, failures, retries, and timeouts are all auditable.
- Plan JSON is persisted separately from the tabular raw dataset.
- The collection manifest makes it possible to trace how the dataset was produced.
- Successful observations and plan records join exactly on the frozen observation-level key.

## Common Failure Modes

- Using unstable random sampling with no seed or manifest trace.
- Mixing logical run ids and retry attempt ids.
- Writing only successful runs and losing evidence of failures.
- Letting `plans.jsonl` and `raw_runs.parquet` drift onto different identifiers.
- Embedding plan JSON directly in the main parquet file in ways that become brittle later.
- Letting the collector partially fail without surfacing that the dataset is incomplete.
