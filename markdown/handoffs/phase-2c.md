# Phase 2c Handoff

## Objective
- Implement the final dataset assembly for Phase 2c in `polars`, add a CLI entrypoint, write `artifacts/features/features.parquet`, and verify that joins, row coverage, null handling, and target columns match the project contract used in this thread.

## Status
- Complete

## What Was Implemented
- Added final dataset assembly code in [src/ivory/dataset_assembly.py](/Users/howen/dev/ivory/src/ivory/dataset_assembly.py).
- Implemented loading of:
  - `artifacts/raw/sf_*/raw_runs.parquet`
  - `artifacts/features/sql_features.parquet`
  - `artifacts/features/sql_feature_exclusions.parquet`
  - `artifacts/features/plan_features.parquet`
  - `artifacts/features/plan_feature_exclusions.parquet`
- Implemented observation-grain assembly rules:
  - raw base rows come from successful, modeling-included, non-excluded raw observations
  - SQL features are joined by `query_instance_id`, `template_id`, `parameter_set_id`, and `scale_factor`
  - plan features are joined by `observation_id`, with audit validation that the attached query identifiers still match raw
  - upstream SQL and plan exclusion artifacts are applied before final coverage checks
- Implemented fail-fast validation for:
  - duplicate raw, SQL-feature, and plan-feature keys
  - missing joined feature rows
  - mismatched plan audit keys
  - missing required targets
  - final observation coverage
  - top-level feature-schema coverage
  - nested struct field-set coverage for `targets`, `sql_features`, and `plan_features`
  - `null_indicator_columns` dtype being `List(String)`
- Added CLI support for `uv run python -m ivory.cli featurize assemble`.
- Added dataset-assembly tests in [tests/test_dataset_assembly.py](/Users/howen/dev/ivory/tests/test_dataset_assembly.py).
- Added CLI dispatch coverage for `featurize assemble` in [tests/test_cli.py](/Users/howen/dev/ivory/tests/test_cli.py).
- Updated machine-readable contracts to carry `planning_time_ms` in the final dataset and downstream metric target schemas.
- Added a Phase 2c reference entry to [markdown/references.md](/Users/howen/dev/ivory/markdown/references.md).

## Files Changed
- [src/ivory/dataset_assembly.py](/Users/howen/dev/ivory/src/ivory/dataset_assembly.py)
  Added the Phase 2c assembler, join logic, exclusion handling, schema checks, and artifact writing.
- [src/ivory/commands/featurize.py](/Users/howen/dev/ivory/src/ivory/commands/featurize.py)
  Added the `assemble` subcommand and its handler.
- [tests/test_dataset_assembly.py](/Users/howen/dev/ivory/tests/test_dataset_assembly.py)
  Added tests for successful assembly output and explicit feature-exclusion filtering.
- [tests/test_cli.py](/Users/howen/dev/ivory/tests/test_cli.py)
  Added a dispatch test for `featurize assemble`.
- [schemas/features.schema.json](/Users/howen/dev/ivory/schemas/features.schema.json)
  Updated the final dataset schema so `targets` includes `planning_time_ms`.
- [schemas/baseline_metrics.schema.json](/Users/howen/dev/ivory/schemas/baseline_metrics.schema.json)
  Added `planning_time_ms` to required baseline metric targets.
- [schemas/grouped_metrics.schema.json](/Users/howen/dev/ivory/schemas/grouped_metrics.schema.json)
  Added `planning_time_ms` to required grouped metric targets.
- [schemas/artifact_contract.json](/Users/howen/dev/ivory/schemas/artifact_contract.json)
  Added `null_policy` with `allowed_nullable_columns`, `null_indicator_column`, and notes for top-level final-dataset null handling.
- [configs/experiment.toml](/Users/howen/dev/ivory/configs/experiment.toml)
  Added `planning_time_ms` to both `experiment.required_metrics.baseline` and `experiment.required_metrics.grouped`.
- [src/ivory/config.py](/Users/howen/dev/ivory/src/ivory/config.py)
  Updated `REQUIRED_TARGETS` to include `planning_time_ms`.
- [markdown/references.md](/Users/howen/dev/ivory/markdown/references.md)
  Added a `Polars user guide` reference for the Phase 2c work.

## Commands / Interfaces
- Added CLI command:
  - `uv run python -m ivory.cli featurize assemble`
- Added Python entrypoint:
  - `ivory.dataset_assembly.assemble_feature_dataset()`

## Artifacts / Outputs
- Generated [artifacts/features/features.parquet](/Users/howen/dev/ivory/artifacts/features/features.parquet)
  - Final row count observed in this thread: `3303`
  - Verified top-level `null_indicator_columns` dtype output: `List(String)`
  - Verified sample target struct shape included:
    - `planner_total_cost`
    - `planning_time_ms`
    - `execution_time_ms`

## Verification
- `uv run python -m pytest tests/test_dataset_assembly.py tests/test_cli.py`
  - Passed before later schema/config updates.
- `uv run python -m ivory.cli featurize assemble`
  - Passed.
  - Output included:
    - `[INFO] dataset assembly start | successful_observations=3303 eligible_observations=3303`
    - `[SUCCESS] dataset assembly complete | completed=3303/3303 (100.0%) features=3303`
- `uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/features.parquet'); schema=json.loads(Path('schemas/features.schema.json').read_text()); assert set(schema['required']).issubset(set(df.columns)); print('ok', df.height)"`
  - Passed with output: `ok 3303`
- `uv run python -c "import json, polars as pl; from pathlib import Path; df = pl.read_parquet('artifacts/features/features.parquet'); contract=json.loads(Path('schemas/artifact_contract.json').read_text()); allowed=set(contract['null_policy']['allowed_nullable_columns']); nulls=df.null_count().to_dicts()[0]; assert all((k in allowed) or (v==0) for k,v in nulls.items()); print('ok')"`
  - Passed with output: `ok`
- `uv run python -c "import polars as pl; from pathlib import Path; raw=pl.concat([pl.read_parquet(path) for path in sorted(Path('artifacts/raw').glob('sf_*/raw_runs.parquet'))], how='vertical').filter(pl.col('status')=='success').select('observation_id'); feat=pl.read_parquet('artifacts/features/features.parquet').select('observation_id'); raw_ids=raw['observation_id'].to_list(); feat_ids=feat['observation_id'].to_list(); assert len(raw_ids)==len(set(raw_ids)); assert len(feat_ids)==len(set(feat_ids)); assert set(raw_ids)==set(feat_ids); print('ok')"`
  - Passed with output: `ok`
- `uv run python -m pytest tests -k dataset_assembly`
  - Passed.
  - One earlier parallel run failed during import collection with `ModuleNotFoundError: No module named 'ivory.config'`; rerunning the same command serially passed.
- `uv run python -m pytest tests/test_dataset_assembly.py tests/test_cli.py tests/test_config_validation.py`
  - Passed after the review-driven fixes.
- `uv run python -m ivory.cli validate-config --config configs/experiment.toml`
  - Passed with output: `Experiment contract validation succeeded.`
- `prek run`
  - Initially failed on two `ruff` line-length violations in `src/ivory/dataset_assembly.py`.
  - After wrapping those messages, `prek run` passed.
- Review cycle:
  - First `gpt-5.4` review found two issues:
    - `planning_time_ms` was missing from final `targets`
    - `null_indicator_columns` was inferred as `List(Null)` instead of `List(String)`
  - Both were fixed.
  - Second `gpt-5.4` review reported no findings.

## Decisions and Assumptions
- The final dataset is observation-grain and built only from successful raw observations that are still marked for modeling.
- SQL features are treated as broadcast features and must join deterministically from query-instance grain onto observation rows.
- Plan features are treated as observation-grain and must agree with raw identifiers after the join.
- Upstream feature exclusion artifacts are respected before final coverage validation.
- The machine-readable contract in this thread was extended to include `planning_time_ms` in final-modeling and metrics targets because the first review found that Phase 2c and Phase 3a both expected three targets while the checked-in schemas only required two.
- Top-level final dataset columns are treated as non-nullable in practice; nullable feature semantics are documented as nested struct leaf behavior plus `null_indicator_columns`.

## Issues Encountered
- Contract mismatch discovered during implementation:
  - `schemas/features.schema.json` originally required only `planner_total_cost` and `execution_time_ms`, while the Phase 2c and Phase 3a documents referenced three targets including `planning_time_ms`.
- Verification mismatch discovered during implementation:
  - `markdown/phases/phase-2c-feature-dataset-assembly.md` referenced `contract['null_policy']['allowed_nullable_columns']`, but `schemas/artifact_contract.json` did not originally include `null_policy`.
- First review found:
  - missing `planning_time_ms` in final `targets`
  - wrong inferred dtype for `null_indicator_columns`
- `prek run` found two long lines in `src/ivory/dataset_assembly.py`; both were fixed.
- One parallel `pytest -k dataset_assembly` invocation failed during import collection; the same command passed when rerun serially.

## Remaining Work
- None for Phase 2c, based on this thread.

## Next Recommended Step
- Start Phase 3a baseline modeling using `artifacts/features/features.parquet`, which now contains all three targets and the validated assembled feature dataset.

## Notes for Future Agents
- The final assembled dataset file was generated during this thread at [artifacts/features/features.parquet](/Users/howen/dev/ivory/artifacts/features/features.parquet).
- If you touch Phase 3a or metric contracts next, keep the three-target alignment consistent across:
  - [schemas/features.schema.json](/Users/howen/dev/ivory/schemas/features.schema.json)
  - [schemas/baseline_metrics.schema.json](/Users/howen/dev/ivory/schemas/baseline_metrics.schema.json)
  - [schemas/grouped_metrics.schema.json](/Users/howen/dev/ivory/schemas/grouped_metrics.schema.json)
  - [configs/experiment.toml](/Users/howen/dev/ivory/configs/experiment.toml)
  - [src/ivory/config.py](/Users/howen/dev/ivory/src/ivory/config.py)
- The repo instruction in this thread required:
  - adding research references to [markdown/references.md](/Users/howen/dev/ivory/markdown/references.md)
  - running `prek run`
  - running a `gpt-5.4` review cycle until no findings remained
- No model training was implemented in this thread.
