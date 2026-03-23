# Phase 2b Handoff

## Objective
- Implement PostgreSQL plan-feature extraction for Phase 2b, writing a dedicated plan-features artifact and exclusion artifact from `artifacts/raw/sf_*/plans.jsonl`, without parsing SQL text or assembling the final modeling dataset.

## Status
- Complete

## What Was Implemented
- Added a new plan-feature extractor in [src/ivory/plan_features.py](/Users/howen/dev/ivory/src/ivory/plan_features.py).
- Implemented JSONL loading from `artifacts/raw/sf_*/plans.jsonl` using Python `json.loads(...)`.
- Implemented manual recursive/stack-based traversal of PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plan trees starting at `record["plan"]["Plan"]`.
- Extracted deterministic observation-level features including:
  - `plan_node_count`
  - `join_node_count`
  - `scan_node_count`
  - `aggregate_node_count`
  - `sort_node_count`
  - `plan_depth_max`
  - root/sum/max summaries for `Plan Rows`
  - root/sum/max summaries for `Plan Width`
  - root/sum/max summaries for `Startup Cost`
  - root/sum/max summaries for `Total Cost`
  - stable node-type count columns for observed PostgreSQL node types
  - `other_node_count`
- Added explicit exclusion handling for malformed or incomplete plan records via `PlanFeatureError` and `artifacts/features/plan_feature_exclusions.parquet`.
- Added schema validation and coverage validation so successful raw `observation_id`s must exactly equal feature rows plus exclusion rows.
- Added CLI support for `uv run python -m ivory.cli featurize plan`.
- Updated the frozen contract so plan features are treated as observation-level, not broadcast features in final dataset assembly.
- Added tests for:
  - feature extraction from a known plan tree
  - exclusion-row construction
  - writing plan feature and exclusion artifacts
  - duplicate successful-observation detection
  - failure when plan rows do not fully cover successful raw observations
- Added one research reference for PostgreSQL EXPLAIN JSON docs to `markdown/references.md`.

## Files Changed
- [src/ivory/plan_features.py](/Users/howen/dev/ivory/src/ivory/plan_features.py)
  - New module for Phase 2b plan feature extraction, validation, artifact writing, and exclusion handling.
- [src/ivory/commands/featurize.py](/Users/howen/dev/ivory/src/ivory/commands/featurize.py)
  - Added `featurize plan` CLI subcommand and handler.
- [schemas/plan_features.schema.json](/Users/howen/dev/ivory/schemas/plan_features.schema.json)
  - Replaced with an observation-grain plan-features schema matching implemented columns.
- [schemas/artifact_contract.json](/Users/howen/dev/ivory/schemas/artifact_contract.json)
  - Updated `plan_features` grain to `one row per successful observation_id`.
  - Updated `plan_features_broadcast_to_successful_observations` to `false`.
- [schemas/features.schema.json](/Users/howen/dev/ivory/schemas/features.schema.json)
  - Updated `plan_features_broadcast` constant to `false` to match observation-grain plan features.
- [markdown/contracts.md](/Users/howen/dev/ivory/markdown/contracts.md)
  - Updated prose to reflect that `plan_features` joins by `observation_id` and is not broadcast.
- [markdown/references.md](/Users/howen/dev/ivory/markdown/references.md)
  - Added PostgreSQL EXPLAIN documentation reference.
- [tests/test_plan_features.py](/Users/howen/dev/ivory/tests/test_plan_features.py)
  - New tests for Phase 2b extractor behavior and validation.

## Commands / Interfaces
- Added CLI command:
  - `uv run python -m ivory.cli featurize plan`
- Implemented public function:
  - `ivory.plan_features.featurize_query_plans()`
- Plan parsing path in collection code confirmed to already produce JSON plans from:
  - `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ...`
  - Source location: [src/ivory/collection.py](/Users/howen/dev/ivory/src/ivory/collection.py)

## Artifacts / Outputs
- Generated:
  - [artifacts/features/plan_features.parquet](/Users/howen/dev/ivory/artifacts/features/plan_features.parquet)
  - [artifacts/features/plan_feature_exclusions.parquet](/Users/howen/dev/ivory/artifacts/features/plan_feature_exclusions.parquet)
- Observed output after running the real featurizer:
  - `observations=3303`
  - `feature_rows=3303`
  - `exclusions=0`

## Verification
- Ran:
  - `uv run pytest tests/test_plan_features.py tests/test_cli.py -q`
  - Outcome: passed (`8 passed` at that point in the thread).
- Ran:
  - `uv run python -m ivory.cli featurize plan`
  - Outcome: completed successfully.
  - Notable output: `Plan featurization complete: observations=3303 feature_rows=3303 exclusions=0`
- Ran schema check:
  - `uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/plan_features.parquet'); schema=json.loads(Path('schemas/plan_features.schema.json').read_text()); assert set(schema['required']).issubset(set(df.columns)); print('ok', df.height)"`
  - Outcome: `ok 3303`
- Ran coverage check:
  - `uv run python -c "import polars as pl; from pathlib import Path; raw=pl.concat([pl.read_parquet(path) for path in sorted(Path('artifacts/raw').glob('sf_*/raw_runs.parquet'))], how='vertical').filter(pl.col('status')=='success').select('observation_id').unique(); feat=pl.read_parquet('artifacts/features/plan_features.parquet').select('observation_id'); excl=pl.read_parquet('artifacts/features/plan_feature_exclusions.parquet').select('observation_id'); feat_ids=set(feat['observation_id'].to_list()); excl_ids=set(excl['observation_id'].to_list()); raw_ids=set(raw['observation_id'].to_list()); assert feat.height == len(feat_ids); assert excl.height == len(excl_ids); assert feat_ids.isdisjoint(excl_ids); assert raw_ids == (feat_ids | excl_ids); print('ok')"`
  - Outcome: `ok`
- Ran:
  - `uv run python -m pytest tests -k plan_feature`
  - Outcome: `3 passed, 39 deselected`
- Ran later after follow-up fixes:
  - `uv run pytest tests/test_plan_features.py -q`
  - Outcome: `5 passed`
- Ran contract consistency check:
  - `uv run python - <<'PY' ... assert features['properties']['plan_features_broadcast']['const'] == False ... PY`
  - Outcome: `ok`
- Ran required repo check:
  - `prek run`
  - Outcome: passed

## Decisions and Assumptions
- Plan features were implemented at observation grain, keyed by `observation_id`.
- This was chosen because:
  - `plans.jsonl` is one row per successful observation.
  - Phase 2b verification in this thread required exact coverage over successful `observation_id`s.
- Plan parsing uses manual traversal over PostgreSQL JSON plans, not a third-party plan parser package.
- Plan JSON is produced upstream by PostgreSQL with `FORMAT JSON`; this phase does not parse textual plan output.
- SQL features remain query-instance level and broadcast later; plan features do not broadcast.
- Generated parquet feature artifacts were produced locally during this thread. Whether to commit them was discussed, but not decided or implemented here.

## Issues Encountered
- Initial attempt to inspect artifacts with bare `python` failed because `python` was not on `PATH`; switched to `uv run python`.
- Review agent found two implemented issues:
  - downstream contract mismatch between `artifact_contract.json` and `features.schema.json` for `plan_features_broadcast`
  - duplicate successful observations were deduplicated before validation in `load_successful_observations()`
- Both issues were fixed during this thread.
- Review agent follow-up found no remaining correctness findings.

## Remaining Work
- No implementation work remains for Phase 2b based on this thread.
- Test coverage gaps noted by the review agent remain:
  - no explicit test for an extra `plans.jsonl` row whose `observation_id` is not present in successful raw runs
  - no explicit test for malformed JSON lines in `plans.jsonl`

## Next Recommended Step
- Start Phase 2c and assemble the final observation-level modeling dataset by joining successful raw runs, SQL features, and observation-level plan features.

## Notes for Future Agents
- There was an unrelated pre-existing modification in [AGENTS.md](/Users/howen/dev/ivory/AGENTS.md) visible in `git status`; it was not part of Phase 2b work.
- The reviewer explicitly re-checked the final state and reported no remaining findings, only the two residual test-coverage gaps listed above.
- If Phase 2c assumes plan features are broadcast, that assumption is now wrong; the current contract says plan features join directly on `observation_id`.
- The actual raw planner outputs are stored in:
  - [artifacts/raw/sf_0_1/plans.jsonl](/Users/howen/dev/ivory/artifacts/raw/sf_0_1/plans.jsonl)
  - [artifacts/raw/sf_1_0/plans.jsonl](/Users/howen/dev/ivory/artifacts/raw/sf_1_0/plans.jsonl)
- Collection already obtains structured plans via PostgreSQL:
  - `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ...`
  - so Phase 2b consumes JSON, not text plans.
