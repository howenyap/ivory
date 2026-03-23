# Phase 1a Handoff

## Objective
- Provision a reproducible local PostgreSQL + TPC-H environment for the configured scale factors in `configs/experiment.toml`.
- Implement project-managed load and smoke-check commands for the database environment.
- Keep this phase limited to environment setup and verification; do not build the later query collection pipeline.

## Status
- Complete

## What Was Implemented
- Added a local PostgreSQL Docker Compose environment with a persistent database volume and a mounted TPC-H flat-file cache.
- Added a pinned Docker build for TPC-H `dbgen` using `https://github.com/electrum/tpch-dbgen.git` at commit `32f1c1b92d1664dba542e927d23d86ffa57aa253`.
- Added TPC-H schema, constraints, and index SQL files.
- Implemented PostgreSQL/TPC-H management helpers in `src/ivory/postgres.py`.
- Replaced the placeholder `collect` command with real subcommands for:
  - `start-db`
  - `stop-db`
  - `reset-db`
  - `load-db`
  - `reload-db`
  - `db-health`
  - `db-row-counts`
  - `db-smoke-query`
- Added cache-aware `.tbl` handling:
  - `load-db` prompts before regenerating cached `.tbl` files for a scale factor.
  - declining regeneration reuses the existing cache.
  - incomplete cache reuse fails fast with a missing-file error.
  - non-interactive `load-db` safely reuses cache instead of failing with `EOFError`.
  - `reload-db` force-regenerates without prompting.
- Tightened row-count validation to check exact deterministic counts for `region`, `nation`, `supplier`, `customer`, `part`, `partsupp`, and `orders`, plus `lineitem > orders`.
- Made raw `docker compose` self-contained again by keeping concrete values in `docker-compose.yml`.
- Added validation that the pinned Compose values match the canonical PostgreSQL contract in `configs/experiment.toml`.
- Removed the duplicate `experiment.postgresql_version` field so `postgres.version` is the only PostgreSQL version source of truth.
- Added `artifacts/tpch-data/` to `.gitignore`.

## Files Changed
- `/Users/howen/dev/ivory/.gitignore`
  - Added `artifacts/tpch-data/`.
- `/Users/howen/dev/ivory/README.md`
  - Documented Phase 1a workflow, cache prompt behavior, non-interactive reuse behavior, and `reload-db` force-regeneration.
  - Documented that `docker-compose.yml` remains concrete and is validated against `configs/experiment.toml`.
- `/Users/howen/dev/ivory/configs/experiment.toml`
  - Added `[postgres]` settings:
    - `version`
    - host/port/user/password/admin DB
    - compose/service names
    - `data_root`
    - `dbgen_image_tag`
    - `dbgen_repo`
    - `dbgen_commit`
    - `postgres.scale_factor_databases`
  - Added `experiment.scale_factors`.
  - Removed duplicate `experiment.postgresql_version`.
- `/Users/howen/dev/ivory/docker-compose.yml`
  - Added `postgres` service with persistent volume and mounted `./artifacts/tpch-data:/tpch-data`.
  - Added `tpch-dbgen` build/service with mounted repo and `tpch-data`.
  - Pinned concrete values:
    - `postgres:16`
    - `TPCH_DBGEN_REPO: https://github.com/electrum/tpch-dbgen.git`
    - `TPCH_DBGEN_COMMIT: 32f1c1b92d1664dba542e927d23d86ffa57aa253`
    - `image: ivory/tpch-dbgen:phase-1a`
- `/Users/howen/dev/ivory/docker/tpch-dbgen/Dockerfile`
  - Builds `dbgen` inside the image and installs `/usr/local/bin/dbgen`.
- `/Users/howen/dev/ivory/pyproject.toml`
  - Added `psycopg[binary]>=3.2.12`.
- `/Users/howen/dev/ivory/sql/tpch_schema.sql`
  - Added TPC-H base tables.
- `/Users/howen/dev/ivory/sql/tpch_constraints.sql`
  - Added primary keys and foreign keys.
- `/Users/howen/dev/ivory/sql/tpch_indexes.sql`
  - Added supporting indexes and `ANALYZE`.
- `/Users/howen/dev/ivory/src/ivory/cli.py`
  - Registered the real `collect` command tree instead of using the phase-0 placeholder.
- `/Users/howen/dev/ivory/src/ivory/commands/collect.py`
  - Added collect subcommand registration and handlers.
  - Added interactive/non-interactive cache regeneration behavior.
  - Added stronger row-count validation.
- `/Users/howen/dev/ivory/src/ivory/config.py`
  - Added `PostgresConfig`.
  - Added `experiment_scale_factors()`, `postgres_config()`, `compose_contract_values()`.
  - Extended config validation for:
    - `[postgres]`
    - scale-factor mapping consistency
    - concrete Compose pin alignment with config
  - Removed `experiment.postgresql_version` from required keys.
- `/Users/howen/dev/ivory/src/ivory/postgres.py`
  - Added PostgreSQL/TPC-H orchestration:
    - compose invocation
    - container startup/shutdown/reset
    - cache inspection
    - `dbgen` execution
    - schema creation
    - `COPY FROM PROGRAM` loading from `/tpch-data`
    - post-load constraints/indexes
    - health/count/smoke-query helpers
  - Added cache-prompt helper and expected row-count logic.
- `/Users/howen/dev/ivory/tests/test_collect_load_db.py`
  - Added tests for cache detection, incomplete cache rejection, prompt handling, non-interactive reuse, and `reload-db`.
- `/Users/howen/dev/ivory/tests/test_config_validation.py`
  - Added tests for PostgreSQL mapping consistency and Compose pin/config alignment.
- `/Users/howen/dev/ivory/uv.lock`
  - Updated after adding `psycopg[binary]`.

## Commands / Interfaces
- CLI:
  - `uv run python -m ivory.cli collect start-db`
  - `uv run python -m ivory.cli collect stop-db`
  - `uv run python -m ivory.cli collect reset-db`
  - `uv run python -m ivory.cli collect load-db`
  - `uv run python -m ivory.cli collect reload-db`
  - `uv run python -m ivory.cli collect db-health`
  - `uv run python -m ivory.cli collect db-row-counts`
  - `uv run python -m ivory.cli collect db-smoke-query`
  - `uv run python -m ivory.cli validate-config --config configs/experiment.toml`
- Python helpers in `src/ivory/postgres.py`:
  - `project_postgres_config`
  - `scale_factor_cache_status`
  - `validate_cache_for_reuse`
  - `generate_tpch_data`
  - `load_scale_factor`
  - `load_scale_factor_from_cache`
  - `table_counts`
  - `table_presence`
  - `run_smoke_query`
- Validation helper in `src/ivory/config.py`:
  - `compose_contract_values`

## Artifacts / Outputs
- Local TPC-H flat-file cache under:
  - `/Users/howen/dev/ivory/artifacts/tpch-data`
  - scale-factor directories used in this thread:
    - `/Users/howen/dev/ivory/artifacts/tpch-data/sf_0_1`
    - `/Users/howen/dev/ivory/artifacts/tpch-data/sf_1_0`
    - `/Users/howen/dev/ivory/artifacts/tpch-data/sf_10_0`
- Local PostgreSQL databases loaded in this thread:
  - `tpch_sf_0_1`
  - `tpch_sf_1`
  - `tpch_sf_10`
- Notable observed cache size during this thread:
  - `artifacts/tpch-data` was approximately `12G`.

## Verification
- `uv sync`
  - Succeeded.
- `uv run python -m unittest tests/test_config_validation.py`
  - Passed.
- `uv run python -m unittest tests/test_config_validation.py tests/test_collect_load_db.py`
  - Passed after implementation updates.
- `uv run python -m ivory.cli --help`
  - Passed and showed the real `collect` command.
- `uv run python -m ivory.cli collect --help`
  - Passed.
- `uv run python -m ivory.cli validate-config --config configs/experiment.toml`
  - Passed after config changes.
- `uv run python -m ivory.cli collect load-db`
  - Eventually succeeded after debugging Docker/dbgen/path issues.
- `docker compose -f docker-compose.yml ps`
  - Passed cleanly after reverting Compose back to concrete values.
- `uv run python -m ivory.cli collect db-health`
  - User reported success:
    - `0.1 tpch_sf_0_1 healthy`
    - `1.0 tpch_sf_1 healthy`
    - `10.0 tpch_sf_10 healthy`
- `uv run python -m ivory.cli collect db-row-counts`
  - Passed with observed output:
    - `0.1 tpch_sf_0_1 region=5, nation=25, supplier=1000, customer=15000, part=20000, partsupp=80000, orders=150000, lineitem=600572`
    - `1.0 tpch_sf_1 region=5, nation=25, supplier=10000, customer=150000, part=200000, partsupp=800000, orders=1500000, lineitem=6001215`
    - `10.0 tpch_sf_10 region=5, nation=25, supplier=100000, customer=1500000, part=2000000, partsupp=8000000, orders=15000000, lineitem=59986052`
- `uv run ruff check src tests`
  - Passed.
- `uv run ty check`
  - Passed.
- `uv run prek run --all-files`
  - Passed.
- `uv run prek run`
  - Failed when run with unstaged changes because `prek` stashed the working tree and checked the older staged snapshot instead of the current unstaged fixes.

## Decisions and Assumptions
- `dbgen` was used as the TPC-H data generator.
- `dbgen` is built in Docker instead of being committed as a binary.
- `docker-compose.yml` was intentionally kept concrete so raw `docker compose` commands work directly from the repo root.
- `configs/experiment.toml` remains the contract source of truth, but Compose drift is caught by `validate-config`.
- `postgres.version` is the single PostgreSQL version source of truth.
- `load-db` prompts if any `.tbl` file exists for a scale factor.
- Declining the prompt reuses cached `.tbl` files as-is.
- Reusing an incomplete cache is treated as an error.
- Non-interactive `load-db` defaults to reusing cache rather than failing.
- `reload-db` is the force-regenerate path and does not prompt.
- `artifacts/tpch-data/` should stay out of Git.

## Issues Encountered
- Initial `load-db` failed because the local Docker daemon was not running.
- Initial `dbgen` invocation failed because `dists.dss` was not available from the working directory; fixed by passing `-b /opt/tpch-dbgen/dists.dss`.
- Initial PostgreSQL load failed because `COPY FROM PROGRAM` used host paths instead of container-visible `/tpch-data/...` paths.
- Initial `dbgen` output path was wrong because generation ran inside the Linux container with a host absolute path; fixed by writing to the shared `/tpch-data` mount.
- The largest scale factor (`10.0`) spent significant time in post-load constraint/index creation; this was monitored through `pg_stat_activity`.
- Two subagent review passes found contract alignment issues:
  - duplicated pinned versions not actually sourced from config
  - weak `db-row-counts` validation
  - non-interactive cache prompt failure risk
  - non-self-contained Compose env indirection
  - duplicated PostgreSQL version fields
  - these were addressed during this thread
- `uv run prek run` can give misleading failures when there are unstaged changes because it checks the staged snapshot after stashing unstaged work.

## Remaining Work
- No phase-specific implementation gap was identified as unfinished in this thread.
- End-to-end automated coverage for the full live Phase 1a verification flow was discussed as a residual testing gap, but no such CI/integration test was implemented in this thread.

## Next Recommended Step
- Move to the next project phase, or if desired add a dedicated end-to-end integration check that exercises the full live Phase 1a verification flow against a real loaded database.

## Notes for Future Agents
- The current loaded environment in this thread used:
  - PostgreSQL container `ivory-postgres`
  - port `55432`
  - user/password `ivory` / `ivory`
- Raw `docker compose` commands should now work directly from the repo root without wrapper env injection.
- If `uv run prek run` appears to fail with old lint output while direct Ruff/`ty` pass, check whether the worktree has unstaged changes; `uv run prek run --all-files` reflected the actual current tree in this thread.
- The `.tbl` cache is large and intentionally ignored by Git.
- The handoff content above is limited to work and discussion from this thread only.
