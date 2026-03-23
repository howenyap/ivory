# Phase 0b Handoff

## Objective
- Define the Phase 0b experiment contract in machine-readable files and add a validation path, based on [`markdown/phases/phase-0b-experiment-contract.md`](/Users/howen/dev/ivory/markdown/phases/phase-0b-experiment-contract.md).

## Status
- Partially complete

## What Was Implemented
- Added experiment defaults in [`configs/experiment.toml`](/Users/howen/dev/ivory/configs/experiment.toml).
- Added contract and schema files under [`schemas/`](/Users/howen/dev/ivory/schemas).
- Added prose contract summary in [`markdown/contracts.md`](/Users/howen/dev/ivory/markdown/contracts.md).
- Added CLI command `validate-config` in [`src/ivory/cli.py`](/Users/howen/dev/ivory/src/ivory/cli.py).
- Added config/schema loading and validation helpers in [`src/ivory/config.py`](/Users/howen/dev/ivory/src/ivory/config.py).
- Added basic validation tests in [`tests/test_config_validation.py`](/Users/howen/dev/ivory/tests/test_config_validation.py).

## Files Changed
- [`/Users/howen/dev/ivory/src/ivory/cli.py`](/Users/howen/dev/ivory/src/ivory/cli.py)
  Added `validate-config` subcommand and handler.
- [`/Users/howen/dev/ivory/src/ivory/config.py`](/Users/howen/dev/ivory/src/ivory/config.py)
  Expanded config loading with schema path constants, JSON loading, and contract validation.
- [`/Users/howen/dev/ivory/configs/experiment.toml`](/Users/howen/dev/ivory/configs/experiment.toml)
  Added experiment defaults for PostgreSQL version, scale factors, timeouts, retries, split modes, modeling grain, null handling, and required metrics.
- [`/Users/howen/dev/ivory/schemas/artifact_contract.json`](/Users/howen/dev/ivory/schemas/artifact_contract.json)
  Added top-level artifact contract for canonical artifact paths, keys, status fields, and failure semantics.
- [`/Users/howen/dev/ivory/schemas/raw_runs.schema.json`](/Users/howen/dev/ivory/schemas/raw_runs.schema.json)
  Added row schema for raw run observations.
- [`/Users/howen/dev/ivory/schemas/sql_features.schema.json`](/Users/howen/dev/ivory/schemas/sql_features.schema.json)
  Added row schema for SQL features.
- [`/Users/howen/dev/ivory/schemas/plan_features.schema.json`](/Users/howen/dev/ivory/schemas/plan_features.schema.json)
  Added row schema for plan features.
- [`/Users/howen/dev/ivory/schemas/features.schema.json`](/Users/howen/dev/ivory/schemas/features.schema.json)
  Added row schema for final modeling features.
- [`/Users/howen/dev/ivory/schemas/baseline_metrics.schema.json`](/Users/howen/dev/ivory/schemas/baseline_metrics.schema.json)
  Added schema for baseline metrics artifact.
- [`/Users/howen/dev/ivory/schemas/grouped_metrics.schema.json`](/Users/howen/dev/ivory/schemas/grouped_metrics.schema.json)
  Added schema for grouped metrics artifact.
- [`/Users/howen/dev/ivory/markdown/contracts.md`](/Users/howen/dev/ivory/markdown/contracts.md)
  Added prose summary of dataset grain, key relationships, and failure semantics.
- [`/Users/howen/dev/ivory/tests/test_config_validation.py`](/Users/howen/dev/ivory/tests/test_config_validation.py)
  Added basic tests for config validation and schema reference path count.

## Commands / Interfaces
- CLI command added:
  `uv run python -m ivory.cli validate-config --config configs/experiment.toml`
- Python helpers added in [`src/ivory/config.py`](/Users/howen/dev/ivory/src/ivory/config.py):
  `load_config(path: str | None = None) -> dict[str, Any]`
  `load_schema(path: str | Path) -> dict[str, Any]`
  `schema_reference_paths() -> tuple[Path, ...]`
  `validate_config(path: str | None = None) -> list[str]`

## Artifacts / Outputs
- Machine-readable contract/config files:
  `configs/experiment.toml`
  `schemas/artifact_contract.json`
  `schemas/raw_runs.schema.json`
  `schemas/sql_features.schema.json`
  `schemas/plan_features.schema.json`
  `schemas/features.schema.json`
  `schemas/baseline_metrics.schema.json`
  `schemas/grouped_metrics.schema.json`
- Prose contract file:
  `markdown/contracts.md`
- No experiment datasets, model outputs, or evaluation artifacts were produced in this thread.

## Verification
- Ran:
  `uv run python -m ivory.cli validate-config --config configs/experiment.toml`
  Outcome: succeeded with output `Experiment contract validation succeeded.`
- Ran:
  `uv run python -m unittest discover -s tests -p 'test_*.py'`
  Outcome: `Ran 2 tests ... OK`
- Ran:
  `uv run python -c "from pathlib import Path; import json; [json.loads(Path(p).read_text()) for p in ['schemas/artifact_contract.json','schemas/raw_runs.schema.json','schemas/sql_features.schema.json','schemas/plan_features.schema.json','schemas/features.schema.json','schemas/baseline_metrics.schema.json','schemas/grouped_metrics.schema.json']]"`
  Outcome: succeeded, no output.
- Ran placeholder scan:
  `uv run python -c "from pathlib import Path; import re; pattern=re.compile(r'TODO|TBD|decide later|placeholder'); paths=[Path('configs/experiment.toml'), Path('markdown/contracts.md'), *Path('schemas').rglob('*')]; matches=[]; [matches.append(f'{p}:{i}:{line}') for p in paths if p.is_file() for i, line in enumerate(p.read_text().splitlines(), 1) if pattern.search(line)]; assert not matches, '\\n'.join(matches)"`
  Outcome: succeeded, no matches.
- Ran seed check:
  `uv run python -c "import tomllib; print(tomllib.load(open('configs/experiment.toml','rb'))['experiment']['seed'])"`
  Outcome: printed `20260322`
- Ran artifact contract check:
  `uv run python -c "import json; from pathlib import Path; c=json.loads(Path('schemas/artifact_contract.json').read_text()); required=['modeling_grain','artifacts','keys','status_fields']; assert c['modeling_grain']=='successful_observation'; assert all(k in c for k in required); print('ok')"`
  Outcome: printed `ok`
- Ran join-key check:
  `uv run python -c "import json; from pathlib import Path; raw=json.loads(Path('schemas/raw_runs.schema.json').read_text()); feat=json.loads(Path('schemas/features.schema.json').read_text()); assert 'observation_id' in raw['required']; assert 'query_instance_id' in raw['required']; assert 'observation_id' in feat['required']; print('ok')"`
  Outcome: printed `ok`
- Ran metrics schema check:
  `uv run python -c "import json; from pathlib import Path; m=json.loads(Path('schemas/baseline_metrics.schema.json').read_text()); g=json.loads(Path('schemas/grouped_metrics.schema.json').read_text()); assert 'planner_total_cost' in m['properties']['targets']['required']; assert 'execution_time_ms' in m['properties']['targets']['required']; assert 'grouped_split' in g['properties']; print('ok')"`
  Outcome: printed `ok`

## Decisions and Assumptions
- Implemented Phase 0b as contract/config/schema work only. No data collection, PostgreSQL setup, or modeling code was added.
- The config and schemas were treated as the authoritative contract; [`markdown/contracts.md`](/Users/howen/dev/ivory/markdown/contracts.md) is only a prose summary.
- `successful_observation` was implemented as the modeling grain in code and schemas.
- `query_instance_id` was discussed as the identifier for one concrete query at one scale factor, conceptually combining `template_id`, `parameter_set_id`, and `scale_factor`.
- `baseline` was discussed as the normal random train/test split.
- `grouped` was discussed as splitting entire groups together, with `template_id` used as the example grouping key.
- The user later stated scale factors should be `1, 3, 10`.
- The user questioned the current choices for modeling grain, grouped evaluation, and several metrics. Those concerns were discussed but not yet reconciled in code.

## Issues Encountered
- The initial contract values were not fully aligned with later discussion in the thread.
- Specific unresolved questions raised by the user:
  scale factors currently use `0.1, 1.0, 10.0`, but the user stated they should be `1, 3, 10`
  the meaning and desirability of `successful_observation` as the modeling grain is still under discussion
  several metric names and split-policy terms were hard to review and required explanation
- No code errors blocked implementation or verification in this thread.

## Remaining Work
- Update [`configs/experiment.toml`](/Users/howen/dev/ivory/configs/experiment.toml) to use scale factors `1, 3, 10`.
- Reconcile the modeling-grain decision:
  keep one row per successful run attempt
  or switch to one row per `query_instance_id` with repeated runs aggregated
- Confirm whether grouped evaluation should remain in the Phase 0b contract and, if so, whether `template_id` is the correct grouping key.
- Review and possibly simplify the required metric set in config and schemas.
- If contract semantics change, update the schemas, prose summary, and validation logic to match.

## Next Recommended Step
- Resolve the open contract decisions first: scale factors, modeling grain, and whether grouped evaluation is part of the frozen Phase 0b contract. Then update the config and schemas accordingly and rerun the Phase 0b verification commands.

## Notes for Future Agents
- Base any follow-up edits on the user’s later clarifications in this thread, not only on the currently passing validation checks.
- The current validation path checks structural completeness and JSON parseability, not deep semantic correctness of every schema field.
- The user found several schema/config terms difficult to review. Prefer simplifying names or adding concise explanations if further contract edits are made.
- No Pydantic migration was implemented. Pydantic was discussed as a possible future improvement for config/schema generation, but nothing was changed for that.
