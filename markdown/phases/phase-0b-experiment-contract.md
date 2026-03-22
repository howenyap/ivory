# Phase 0b: Experiment Contract

## Codex Prompt Contract

Implement the configuration and schema contract only. Do not collect data, stand up PostgreSQL, or build modeling code in this phase. Before stopping, validate the config and confirm every schema file is parseable, complete, and explicit about artifact paths, keys, modeling grain, and metric contracts.

## Objective

Define the machine-readable experiment contract that all later phases must obey. This phase freezes the project-wide defaults for PostgreSQL version, TPC-H scale factors, collection policy, split policy, artifact names, dataset grain, join keys, null-handling policy, and output schemas. The purpose is to eliminate ambiguity before any data collection or modeling work begins.

## Inputs / Dependencies

- [`phase-0a-bootstrap.md`](./phase-0a-bootstrap.md) is complete.
- The `ivory` package and CLI skeleton exist.
- The project conventions in [`README.md`](./README.md) are accepted as the baseline.

## Implementation Steps

1. Create `configs/experiment.toml` with explicit defaults for:
   - PostgreSQL version
   - TPC-H scale factors
   - scale-factor-to-database mapping
   - query timeout
   - retry count
   - run count per query
   - primary timing label policy
   - random seed
   - train/test split modes
   - canonical modeling grain: one row per successful observation
   - null-handling policy for final modeling data
   - required metric set for baseline and grouped evaluation
2. Create schema contracts in `schemas/` for:
   - `artifact_contract.json`
   - `raw_runs.schema.json`
   - `sql_features.schema.json`
   - `plan_features.schema.json`
   - `features.schema.json`
   - `baseline_metrics.schema.json`
   - `grouped_metrics.schema.json`
3. Define canonical artifact names and locations under `artifacts/` in `schemas/artifact_contract.json`.
4. Freeze the required identifiers across datasets, including exact columns and semantics for:
   - `template_id`
   - `parameter_set_id`
   - `query_instance_id`
   - `scale_factor`
   - `run_attempt_id`
   - `observation_id`
5. Freeze how SQL features relate to the final modeling grain, including whether query-instance-level SQL features are broadcast onto observation-level rows.
6. Define how failed runs, excluded runs, retried runs, and feature-featurization exclusions must be represented.
7. Freeze the required metrics artifact structure and required keys for:
   - `artifacts/models/baseline_metrics.json`
   - `artifacts/evaluation/grouped_metrics.json`
8. Add a config loader and schema reference helpers to the codebase if needed.
9. Add a simple config validation command or script reachable through the CLI.
10. Write a short contract document in `markdown/contracts.md`, but keep the machine-readable config and schema files authoritative.

## Deliverables

- `configs/experiment.toml`
- `schemas/artifact_contract.json`
- `schemas/raw_runs.schema.json`
- `schemas/sql_features.schema.json`
- `schemas/plan_features.schema.json`
- `schemas/features.schema.json`
- `schemas/baseline_metrics.schema.json`
- `schemas/grouped_metrics.schema.json`
- required `markdown/contracts.md` describing dataset grain, key relationships, and failure semantics in prose
- a CLI or script path for config validation

## Verification

Run these checks from the repository root:

```bash
uv run python -m ivory.cli validate-config --config configs/experiment.toml
```

Expected result:
- validation succeeds
- no required field is missing

```bash
uv run python -c "from pathlib import Path; import json; [json.loads(Path(p).read_text()) for p in ['schemas/artifact_contract.json','schemas/raw_runs.schema.json','schemas/sql_features.schema.json','schemas/plan_features.schema.json','schemas/features.schema.json','schemas/baseline_metrics.schema.json','schemas/grouped_metrics.schema.json']]"
```

Expected result:
- all schema files parse as valid JSON

```bash
uv run python -c "from pathlib import Path; import re; pattern=re.compile(r'TODO|TBD|decide later|placeholder'); paths=[Path('configs/experiment.toml'), Path('markdown/contracts.md'), *Path('schemas').rglob('*')]; matches=[]; \
[matches.append(f'{p}:{i}:{line}') for p in paths if p.is_file() for i, line in enumerate(p.read_text().splitlines(), 1) if pattern.search(line)]; \
assert not matches, '\\n'.join(matches)"
```

Expected result:
- no unresolved contract placeholders remain

```bash
uv run python -c "import tomllib; print(tomllib.load(open('configs/experiment.toml','rb'))['experiment']['seed'])"
```

Expected result:
- a concrete numeric seed prints successfully

```bash
uv run python -c "import json; from pathlib import Path; c=json.loads(Path('schemas/artifact_contract.json').read_text()); required=['modeling_grain','artifacts','keys','status_fields']; assert c['modeling_grain']=='successful_observation'; assert all(k in c for k in required); print('ok')"
```

Expected result:
- the artifact contract exists
- the modeling grain is frozen to `successful_observation`
- artifact paths, canonical keys, and status fields are present

```bash
uv run python -c "import json; from pathlib import Path; raw=json.loads(Path('schemas/raw_runs.schema.json').read_text()); feat=json.loads(Path('schemas/features.schema.json').read_text()); assert 'observation_id' in raw['required']; assert 'query_instance_id' in raw['required']; assert 'observation_id' in feat['required']; print('ok')"
```

Expected result:
- required join keys are present in the dataset schemas

```bash
uv run python -c "import json; from pathlib import Path; m=json.loads(Path('schemas/baseline_metrics.schema.json').read_text()); g=json.loads(Path('schemas/grouped_metrics.schema.json').read_text()); assert 'planner_total_cost' in m['properties']['targets']['required']; assert 'execution_time_ms' in m['properties']['targets']['required']; assert 'grouped_split' in g['properties']; print('ok')"
```

Expected result:
- metric schemas require the expected targets
- grouped metrics schema explicitly covers grouped split metadata

## Definition of Done

- The experiment defaults are frozen in `configs/experiment.toml`.
- Dataset grain, join keys, null policy, metric set, and scale-factor mapping are frozen in machine-readable artifacts.
- Every cross-phase dataset has an explicit machine-readable schema.
- Artifact names and locations are fixed in `schemas/artifact_contract.json`.
- Failure, timeout, retry, exclusion, and featurization-exclusion representation is defined.
- No later phase needs to invent missing contract details.

## Common Failure Modes

- Defining only prose without a machine-readable config.
- Allowing artifact names to remain informal or implied.
- Forgetting to define keys that allow joins across phases.
- Leaving the modeling grain undecided until Phase `2c`.
- Leaving split modes ambiguous, which invalidates evaluation later.
- Pushing schema choices into later phases instead of freezing them here.
