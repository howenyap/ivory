# Phase 2a Handoff

## Objective
- Implement SQL structural feature extraction from raw SQL text for Phase 2a, without reading PostgreSQL plan JSON and without assembling the final modeling dataset.
- Produce a query-instance-grain SQL feature artifact plus an explicit SQL feature exclusion artifact.

## Status
- Complete

## What Was Implemented
- Added SQL feature extraction in [src/ivory/sql_features.py](/Users/howen/dev/ivory/src/ivory/sql_features.py).
- Implemented parsing with `sqlglot` over successful raw query instances loaded from `artifacts/raw/sf_*/raw_runs.parquet`.
- Extracted these SQL features into the artifact:
  - `aggregation_present`
  - `selected_column_count`
  - `table_count`
  - `join_count`
  - `predicate_count`
  - `group_by_count`
  - `order_by_count`
  - `limit_count`
  - `subquery_count`
- Enforced query-instance grain using the keys:
  - `query_instance_id`
  - `template_id`
  - `parameter_set_id`
  - `scale_factor`
- Added explicit SQL feature exclusion rows with parse status in `artifacts/features/sql_feature_exclusions.parquet`.
- Added progress logging to the SQL featurizer using the collection pipeline logging helpers.
- Added a CLI command for SQL featurization in [src/ivory/commands/featurize.py](/Users/howen/dev/ivory/src/ivory/commands/featurize.py) and wired it into [src/ivory/cli.py](/Users/howen/dev/ivory/src/ivory/cli.py).
- Added tests for feature extraction, parse exclusions, and CLI dispatch in:
  - [tests/test_sql_features.py](/Users/howen/dev/ivory/tests/test_sql_features.py)
  - [tests/test_cli.py](/Users/howen/dev/ivory/tests/test_cli.py)
- Added a research reference for SQLGlot to [markdown/references.md](/Users/howen/dev/ivory/markdown/references.md).
- Updated [AGENTS.md](/Users/howen/dev/ivory/AGENTS.md) to require spawned agents to use `gpt-5.4` instead of mini models.

## Files Changed
- [src/ivory/sql_features.py](/Users/howen/dev/ivory/src/ivory/sql_features.py)
  Added the Phase 2a featurizer, schema/coverage validation, artifact writing, exclusion handling, and progress logging.
- [src/ivory/commands/featurize.py](/Users/howen/dev/ivory/src/ivory/commands/featurize.py)
  Added the `featurize sql` CLI handler.
- [src/ivory/cli.py](/Users/howen/dev/ivory/src/ivory/cli.py)
  Registered the `featurize` command tree.
- [schemas/sql_features.schema.json](/Users/howen/dev/ivory/schemas/sql_features.schema.json)
  Expanded the SQL feature schema to include `aggregation_present` and `selected_column_count`.
- [schemas/features.schema.json](/Users/howen/dev/ivory/schemas/features.schema.json)
  Expanded the nested `sql_features` object contract to include `aggregation_present` and `selected_column_count`.
- [tests/test_sql_features.py](/Users/howen/dev/ivory/tests/test_sql_features.py)
  Added focused Phase 2a tests.
- [tests/test_cli.py](/Users/howen/dev/ivory/tests/test_cli.py)
  Added CLI dispatch coverage for `featurize sql`.
- [pyproject.toml](/Users/howen/dev/ivory/pyproject.toml)
  Added `sqlglot` as a runtime dependency and `pytest` as a dev dependency.
- [uv.lock](/Users/howen/dev/ivory/uv.lock)
  Updated lockfile for the dependency changes.
- [markdown/references.md](/Users/howen/dev/ivory/markdown/references.md)
  Added the SQLGlot documentation reference.
- [AGENTS.md](/Users/howen/dev/ivory/AGENTS.md)
  Added the instruction to always use `gpt-5.4` for spawned agents.

## Commands / Interfaces
- Added CLI command:
  - `uv run ivory featurize sql`
- Also used successfully during this thread:
  - `uv run python -m ivory.cli featurize sql`
- Logging behavior:
  - Emits start, periodic progress, and completion lines during SQL featurization.

## Artifacts / Outputs
- Generated [artifacts/features/sql_features.parquet](/Users/howen/dev/ivory/artifacts/features/sql_features.parquet)
  - Current run produced `1101` rows.
- Generated [artifacts/features/sql_feature_exclusions.parquet](/Users/howen/dev/ivory/artifacts/features/sql_feature_exclusions.parquet)
  - Current run produced `0` rows.
- SQL feature artifact columns observed in this thread:
  - `query_instance_id`
  - `template_id`
  - `parameter_set_id`
  - `scale_factor`
  - `broadcast_to_modeling_grain`
  - `feature_status`
  - `aggregation_present`
  - `selected_column_count`
  - `table_count`
  - `join_count`
  - `predicate_count`
  - `group_by_count`
  - `order_by_count`
  - `limit_count`
  - `subquery_count`

## Verification
- Ran:
  - `uv run python -m pytest tests/test_sql_features.py tests/test_cli.py`
  - Outcome: passed.
- Ran:
  - `uv run python -m pytest tests -k sql_feature`
  - Outcome: `3 passed`.
- Ran:
  - `uv run python -m ivory.cli featurize sql`
  - Outcome: featurization completed successfully with `query_instances=1101 feature_rows=1101 exclusions=0`.
- Ran:
  - `uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/sql_features.parquet'); schema=json.loads(Path('schemas/sql_features.schema.json').read_text()); assert set(schema['required']).issubset(set(df.columns)); print('ok', df.height)"`
  - Outcome: `ok 1101`.
- Ran:
  - `uv run python -c "import polars as pl; from pathlib import Path; raw=pl.concat([pl.read_parquet(path) for path in sorted(Path('artifacts/raw').glob('sf_*/raw_runs.parquet'))], how='vertical').filter(pl.col('status')=='success').select('query_instance_id').unique(); feat=pl.read_parquet('artifacts/features/sql_features.parquet').select('query_instance_id'); excl=pl.read_parquet('artifacts/features/sql_feature_exclusions.parquet').select('query_instance_id'); feat_ids=set(feat['query_instance_id'].to_list()); excl_ids=set(excl['query_instance_id'].to_list()); raw_ids=set(raw['query_instance_id'].to_list()); assert feat.height == len(feat_ids); assert excl.height == len(excl_ids); assert feat_ids.isdisjoint(excl_ids); assert raw_ids == (feat_ids | excl_ids); print('ok')"`
  - Outcome: `ok`.
- Ran `prek run` multiple times after changes.
  - Final outcome: passed.

## Decisions and Assumptions
- Followed the Phase 2a scope boundary: no PostgreSQL plan JSON inspection was implemented in this phase.
- Treated SQL features as query-instance-grain rows and validated exact coverage against successful raw query instances.
- Added `aggregation_present` and `selected_column_count` to align the implementation with the phase doc’s minimum feature list, even though the original SQL schema in the repo was narrower at the start of the thread.
- Reused the collection pipeline logging helpers for consistent progress output.
- Confirmed from the current corpus that there are no multi-statement successful SQL query instances: `0` out of `1101`.

## Issues Encountered
- `pytest` was not initially installed in the dev environment; `pytest` was added as a dev dependency because the phase verification explicitly uses it.
- `prek run` initially failed on type-checking around Polars schema annotations; this was fixed by switching to `pl.Schema` usage and loosening the parsed SQL argument typing.
- `sqlglot` handles some nested query forms differently than expected:
  - `EXISTS(SELECT ...)` required explicit handling in `subquery_count`.
- The command `uv run python -m ivory.cli featurize sql` intermittently failed in this environment with:
  - `ivory: error: unrecognized arguments: sql`
  - The parser itself and the installed entrypoint were verified to work, and `uv run ivory featurize sql` worked reliably and showed the new progress logs.
- Two external reviews flagged the `sqlglot` multi-statement `Block` edge.
  - This is not present in the current corpus.
  - It was not implemented as a fix in this thread.

## Remaining Work
- Non-blocking hardening only:
  - Handle or explicitly exclude non-`ParseError` parser shapes such as multi-statement `Block` nodes.
  - Add a targeted q15-style rewritten CTE regression test.
- Plan feature extraction is not part of this phase and was not implemented here.

## Next Recommended Step
- Move on to Phase 2b using [markdown/phases/phase-2b-plan-feature-extraction.md](/Users/howen/dev/ivory/markdown/phases/phase-2b-plan-feature-extraction.md).

## Notes for Future Agents
- Phase 2a was assessed in-thread as ready to move to Phase 2b with no blocking findings.
- The current SQL feature artifact has `1101` rows and the exclusion artifact has `0` rows.
- If you want progress output during featurization, prefer:
  - `uv run ivory featurize sql`
- Be aware of the intermittent `python -m ivory.cli featurize sql` invocation issue in this environment.
- If you spawn agents from this repo, [AGENTS.md](/Users/howen/dev/ivory/AGENTS.md) now requires `gpt-5.4`.
