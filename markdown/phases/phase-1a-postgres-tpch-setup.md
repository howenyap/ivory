# Phase 1a: PostgreSQL + TPC-H Setup

## Codex Prompt Contract

Implement only the PostgreSQL and TPC-H environment setup plus smoke-check commands. Do not build the collection pipeline in this phase. Before stopping, prove that every configured scale factor is loaded and queryable through project-managed commands that honor the scale-factor mapping from Phase `0b`.

## Objective

Provision a reproducible PostgreSQL environment and load TPC-H data for the selected scale factors. This phase should end with a healthy database that later collection code can target directly. No query collection pipeline should be implemented here beyond basic smoke checks.

## Inputs / Dependencies

- [`phase-0a-bootstrap.md`](./phase-0a-bootstrap.md) is complete.
- [`phase-0b-experiment-contract.md`](./phase-0b-experiment-contract.md) is complete.
- `configs/experiment.toml` defines:
  - PostgreSQL version
  - scale factors
  - database connection defaults

## Implementation Steps

1. Create Docker configuration for PostgreSQL using the version frozen in `configs/experiment.toml`.
2. Choose and document the TPC-H data generator approach, such as `dbgen`, and make it reproducible.
3. Create scripts or commands that:
   - initialize the database container
   - create the target database or databases
   - generate TPC-H data for each configured scale factor
   - load the data into PostgreSQL
4. Implement the scale-factor-to-database mapping exactly as frozen in `configs/experiment.toml` and `schemas/artifact_contract.json`. This phase must not redefine the mapping.
5. Add lightweight SQL smoke checks:
   - table existence
   - row-count checks
   - one simple join query
6. Document how to start, stop, reset, and reload the local benchmark environment.
7. Keep all data-loading behavior idempotent where feasible, or clearly document reset behavior.

## Deliverables

- Docker or container config for PostgreSQL
- TPC-H generation/loading scripts
- initialization instructions or CLI command wrappers
- documented mapping from scale factor to database target
- row-count validation query set

## Verification

Run these checks from the repository root after bringing the database up:

```bash
docker compose ps
```

Expected result:
- PostgreSQL container is running and healthy

```bash
uv run python -m ivory.cli collect db-health
```

Expected result:
- the CLI can connect to PostgreSQL using project config
- the command reports success for every configured scale factor

```bash
uv run python -m ivory.cli collect db-row-counts
```

Expected result:
- expected TPC-H tables are present
- row counts print for each loaded scale factor
- obvious load failures are surfaced

```bash
uv run python -m ivory.cli collect db-smoke-query
```

Expected result:
- a sample SQL query executes successfully
- the query returns within a reasonable time

```bash
uv run python -c "import tomllib; cfg=tomllib.load(open('configs/experiment.toml','rb')); scales={str(v) for v in cfg['experiment']['scale_factors']}; mapping={str(k) for k in cfg['postgres']['scale_factor_databases']}; assert scales == mapping; print('ok')"
```

Expected result:
- the scale-factor mapping exists in project config
- every configured scale factor has exactly one configured database target
- later phases can target databases without inferring naming rules

## Definition of Done

- PostgreSQL is reproducibly provisioned from project files.
- TPC-H data loads successfully for every configured scale factor.
- The database target for each scale factor is deterministic and sourced from the frozen contract.
- Basic health and row-count checks pass.
- Later phases can assume the benchmark environment exists without manual repair.

## Common Failure Modes

- Using an undocumented local PostgreSQL instance instead of the project-managed one.
- Mixing data for different scale factors in ways that later phases cannot identify cleanly.
- Missing indexes or schema setup needed for correct TPC-H loading.
- No reset path, which makes reruns inconsistent.
- Treating “container started” as sufficient proof that the dataset loaded correctly.
