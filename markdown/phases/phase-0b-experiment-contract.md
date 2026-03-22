# Phase 0b: Experiment Contract

## Objective

Define the machine-readable experiment contract that all later phases must obey. This phase freezes the project-wide defaults for PostgreSQL version, TPC-H scale factors, collection policy, split policy, artifact names, and output schemas. The purpose is to eliminate ambiguity before any data collection or modeling work begins.

## Inputs / Dependencies

- [`phase-0a-bootstrap.md`](./phase-0a-bootstrap.md) is complete.
- The `ivory` package and CLI skeleton exist.
- The project conventions in [`README.md`](./README.md) are accepted as the baseline.

## Implementation Steps

1. Create `configs/experiment.toml` with explicit defaults for:
   - PostgreSQL version
   - TPC-H scale factors
   - query timeout
   - retry count
   - run count per query
   - primary timing label policy
   - random seed
   - train/test split modes
2. Create schema contracts in `schemas/` for:
   - `raw_runs.schema.json`
   - `sql_features.schema.json`
   - `plan_features.schema.json`
   - `features.schema.json`
3. Define canonical artifact names and locations under `artifacts/`.
4. Document the required primary keys across datasets, including how runs, queries, templates, and scale factors are identified.
5. Define how failed runs, excluded runs, and retried runs must be represented.
6. Add a config loader and schema reference helpers to the codebase if needed.
7. Add a simple config validation command or script reachable through the CLI.
8. Write a short contract document if additional narrative is needed, but keep the machine-readable config and schema files authoritative.

## Deliverables

- `configs/experiment.toml`
- `schemas/raw_runs.schema.json`
- `schemas/sql_features.schema.json`
- `schemas/plan_features.schema.json`
- `schemas/features.schema.json`
- optional `markdown/contracts.md` if a narrative explanation is needed
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
uv run python -c "from pathlib import Path; import json; [json.loads(Path(p).read_text()) for p in ['schemas/raw_runs.schema.json','schemas/sql_features.schema.json','schemas/plan_features.schema.json','schemas/features.schema.json']]"
```

Expected result:
- all schema files parse as valid JSON

```bash
rg -n "TODO|TBD|decide later|placeholder" configs/experiment.toml schemas
```

Expected result:
- no unresolved contract placeholders remain

```bash
uv run python -c "import tomllib; print(tomllib.load(open('configs/experiment.toml','rb'))['experiment']['seed'])"
```

Expected result:
- a concrete numeric seed prints successfully

## Definition of Done

- The experiment defaults are frozen in `configs/experiment.toml`.
- Every cross-phase dataset has an explicit machine-readable schema.
- Artifact names and locations are fixed.
- Failure and exclusion representation is defined.
- No later phase needs to invent missing contract details.

## Common Failure Modes

- Defining only prose without a machine-readable config.
- Allowing artifact names to remain informal or implied.
- Forgetting to define keys that allow joins across phases.
- Leaving split modes ambiguous, which invalidates evaluation later.
- Pushing schema choices into later phases instead of freezing them here.

## Codex Prompt Contract

Implement the configuration and schema contract only. Do not collect data, stand up PostgreSQL, or build modeling code in this phase. Before stopping, validate the config and confirm every schema file is parseable and complete.
