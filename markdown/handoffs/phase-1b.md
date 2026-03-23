# Phase 1b Handoff

## Objective
- Implement the phase 1b raw collection pipeline so `uv run python -m ivory.cli collect` can generate deterministic TPC-H queries, run them against the configured PostgreSQL databases, and persist raw per-scale artifacts for later phases.
- Harden the collector enough for long runs: retries, timeouts, resume/checkpointing, progress logging, per-scale artifact layout, and direct per-scale invocation.

## Status
- Partially complete

## What Was Implemented
- Implemented the phase 1b collector behind `uv run python -m ivory.cli collect`.
- Switched TPC-H query generation to use `qgen` from the pinned `tpch-dbgen` image, built for PostgreSQL instead of Oracle.
- Added query normalization for remaining `qgen` quirks, including interval cleanup, trailing `limit` handling, and TPC-H query 15 rewrite.
- Added retries, timeout handling, exclusion recording, and raw attempt logging.
- Added resumable collection with per-scale checkpoint/state files and per-scale materialized artifacts.
- Refactored raw outputs from one shared top-level set into per-scale directories under `artifacts/raw/sf_*`.
- Added top-level aggregate manifest indexing per-scale manifests.
- Added collection progress logging with tagged lines (`[INFO]`, `[SUCCESS]`, etc.).
- Added direct scale-factor collection syntax:
  - `uv run python -m ivory.cli collect 0.1`
  - `uv run python -m ivory.cli collect 1.0`
  - `uv run python -m ivory.cli collect 3.0`
- Added behavior for direct scale collection:
  - explicit scale-factor validation against config
  - `already collected` skip when a matching per-scale manifest and intact materialized files already exist
  - normal argparse invalid-subcommand errors for typo-like tokens (for example `collect lod-db`)
- Updated config/schema/docs from `10.0` to `3.0`, then restored `1.0` so active configured scale factors are `0.1`, `1.0`, and `3.0`.
- Updated `.gitignore` so persisted raw per-scale artifacts are trackable, while checkpoint/state files remain ignored.

## Files Changed
- [configs/experiment.toml](/Users/howen/dev/ivory/configs/experiment.toml)
  - Changed configured scale factors from `0.1, 1.0, 10.0` to `0.1, 1.0, 3.0`.
  - Changed DB mappings from `tpch_sf_10` to `tpch_sf_3`.
- [docker/tpch-dbgen/Dockerfile](/Users/howen/dev/ivory/docker/tpch-dbgen/Dockerfile)
  - Reworked `tpch-dbgen` build to target PostgreSQL and install both `dbgen` and `qgen`.
- [src/ivory/commands/collect.py](/Users/howen/dev/ivory/src/ivory/commands/collect.py)
  - Added `--scale-factor`.
  - Passed explicit scale-factor requests into collection.
  - Converted collection `ValueError`s into clean CLI exits.
- [src/ivory/cli.py](/Users/howen/dev/ivory/src/ivory/cli.py)
  - Added argv normalization so `collect 1.0` becomes `--scale-factor 1.0`.
  - Limited rewrite behavior to numeric scale-factor-like tokens only.
- [src/ivory/collection.py](/Users/howen/dev/ivory/src/ivory/collection.py)
  - Main collector implementation and later hardening.
  - Added `ScaleArtifactPaths`, per-scale manifests, aggregate manifest, checkpoint/state handling, compatibility validation, skip-if-collected behavior, and logging.
- [schemas/raw_runs.schema.json](/Users/howen/dev/ivory/schemas/raw_runs.schema.json)
  - Updated `scale_factor` enum to `0.1, 1.0, 3.0`.
- [schemas/sql_features.schema.json](/Users/howen/dev/ivory/schemas/sql_features.schema.json)
  - Updated `scale_factor` enum to `0.1, 1.0, 3.0`.
- [schemas/plan_features.schema.json](/Users/howen/dev/ivory/schemas/plan_features.schema.json)
  - Updated `scale_factor` enum to `0.1, 1.0, 3.0`.
- [schemas/features.schema.json](/Users/howen/dev/ivory/schemas/features.schema.json)
  - Updated `scale_factor` enum to `0.1, 1.0, 3.0`.
- [schemas/artifact_contract.json](/Users/howen/dev/ivory/schemas/artifact_contract.json)
  - Updated contract for per-scale raw artifact layout.
- [markdown/phases/phase-1b-query-generation-and-collection.md](/Users/howen/dev/ivory/markdown/phases/phase-1b-query-generation-and-collection.md)
  - Updated phase contract to reflect phase 1b implementation and per-scale outputs.
- [markdown/phases/phase-2a-sql-feature-extraction.md](/Users/howen/dev/ivory/markdown/phases/phase-2a-sql-feature-extraction.md)
  - Updated downstream assumptions to per-scale raw inputs.
- [markdown/phases/phase-2b-plan-feature-extraction.md](/Users/howen/dev/ivory/markdown/phases/phase-2b-plan-feature-extraction.md)
  - Updated downstream assumptions to per-scale raw inputs.
- [markdown/phases/phase-2c-feature-dataset-assembly.md](/Users/howen/dev/ivory/markdown/phases/phase-2c-feature-dataset-assembly.md)
  - Updated downstream assumptions to per-scale raw inputs.
- [markdown/phases/README.md](/Users/howen/dev/ivory/markdown/phases/README.md)
  - Updated expected raw artifact layout to `sf_0_1`, `sf_1_0`, `sf_3_0`.
- [markdown/references.md](/Users/howen/dev/ivory/markdown/references.md)
  - Added research references used to justify collection scale choices.
- [tests/test_collection.py](/Users/howen/dev/ivory/tests/test_collection.py)
  - Added/updated tests for per-scale artifacts, resume behavior, manifest validation, and compatible manifest loading.
- [tests/test_config_validation.py](/Users/howen/dev/ivory/tests/test_config_validation.py)
  - Updated expected scale-factor DB mapping.
- [tests/test_cli.py](/Users/howen/dev/ivory/tests/test_cli.py)
  - Added CLI tests for direct scale-factor invocation behavior.
- [AGENTS.md](/Users/howen/dev/ivory/AGENTS.md)
  - Added standing rules discussed in-thread:
    - always add research references to `markdown/references.md`
    - always run `prek run` and fix reported errors
- [`.gitignore`](/Users/howen/dev/ivory/.gitignore)
  - Stopped ignoring persisted per-scale raw artifacts.
  - Continued ignoring transient checkpoint/state files and `artifacts/tpch-data/`.

## Commands / Interfaces
- Added/changed collection commands:
  - `uv run python -m ivory.cli collect`
  - `uv run python -m ivory.cli collect --resume`
  - `uv run python -m ivory.cli collect 0.1`
  - `uv run python -m ivory.cli collect 1.0`
  - `uv run python -m ivory.cli collect 3.0`
  - `uv run python -m ivory.cli collect --limit-templates N --limit-params N --limit-scales N`
- Existing DB commands retained:
  - `uv run python -m ivory.cli collect start-db`
  - `uv run python -m ivory.cli collect stop-db`
  - `uv run python -m ivory.cli collect reset-db`
  - `uv run python -m ivory.cli collect load-db`
  - `uv run python -m ivory.cli collect reload-db`
  - `uv run python -m ivory.cli collect db-health`
  - `uv run python -m ivory.cli collect db-row-counts`
  - `uv run python -m ivory.cli collect db-smoke-query`
- Not implemented:
  - arbitrary multi-scale selection flag like `--scale-factors 1.0,3.0` as a first-class parser option beyond repeated `--scale-factor`
  - dedicated phase 2a feature-extraction command

## Artifacts / Outputs
- Current raw artifact layout:
  - [artifacts/raw/collection_manifest.json](/Users/howen/dev/ivory/artifacts/raw/collection_manifest.json)
  - [artifacts/raw/sf_0_1/raw_runs.parquet](/Users/howen/dev/ivory/artifacts/raw/sf_0_1/raw_runs.parquet)
  - [artifacts/raw/sf_0_1/plans.jsonl](/Users/howen/dev/ivory/artifacts/raw/sf_0_1/plans.jsonl)
  - [artifacts/raw/sf_0_1/exclusions.parquet](/Users/howen/dev/ivory/artifacts/raw/sf_0_1/exclusions.parquet)
  - [artifacts/raw/sf_0_1/collection_manifest.json](/Users/howen/dev/ivory/artifacts/raw/sf_0_1/collection_manifest.json)
  - [artifacts/raw/sf_1_0/raw_runs.parquet](/Users/howen/dev/ivory/artifacts/raw/sf_1_0/raw_runs.parquet)
  - [artifacts/raw/sf_1_0/plans.jsonl](/Users/howen/dev/ivory/artifacts/raw/sf_1_0/plans.jsonl)
  - [artifacts/raw/sf_1_0/exclusions.parquet](/Users/howen/dev/ivory/artifacts/raw/sf_1_0/exclusions.parquet)
  - [artifacts/raw/sf_1_0/collection_manifest.json](/Users/howen/dev/ivory/artifacts/raw/sf_1_0/collection_manifest.json)
- Current notable output state at the end of the thread:
  - `sf_0_1` exists
  - `sf_1_0` exists
  - `sf_3_0` has not been collected yet
  - `artifacts/raw/sf_1_0/.collection_state.json` exists in the current working tree, indicating an in-progress or resumable state for that scale
- Notable historical outputs from this thread:
  - A smoke run of `--limit-templates 2 --limit-params 3 --limit-scales 1` produced `18` raw success rows, `18` plan rows, and `0` exclusions.
  - A timeout smoke run with `--timeout-ms 1` produced timed-out attempts and exclusions.
  - The user’s large mixed-scale run was interrupted during `sf=10.0`; partial `10.0` data was later discarded when switching to per-scale layout.

## Verification
- Ran and reported passing at multiple points:
  - `uv run python -m unittest discover -s tests`
  - `PYTHONPATH=/Users/howen/dev/ivory/src uv run python -m unittest tests.test_collection`
  - `PYTHONPATH=/Users/howen/dev/ivory/src uv run python -m unittest tests.test_cli tests.test_collection tests.test_config_validation`
  - `uv run prek run`
  - `uv run python -m ivory.cli collect --help`
  - `uv run python -m ivory.cli collect db-health`
  - `uv run python -m ivory.cli collect db-row-counts`
  - `uv run python -m ivory.cli collect --limit-templates 1 --limit-params 1 --limit-scales 1`
  - `uv run python -m ivory.cli collect 0.1 --limit-templates 1 --limit-params 1`
  - `uv run python -m ivory.cli collect 5.0` or `collect lod-db` to validate error handling
- Directly observed outputs:
  - `db-health` reported `0.1 tpch_sf_0_1 healthy`, `1.0 tpch_sf_1 healthy`, `3.0 tpch_sf_3 healthy`.
  - `uv run python -m ivory.cli collect lod-db` now exits with argparse invalid-subcommand error.
  - `uv run python -m ivory.cli collect 0.1 --limit-templates 1 --limit-params 1` prints `already collected` on exact rerun after an initial matching slice exists.
- Not fully certain:
  - Some direct `unittest` invocations behaved inconsistently with import paths during the thread, while `prek` passed reliably at the end.

## Decisions and Assumptions
- Query generation should use upstream `qgen`, not hand-authored SQL templates.
- PostgreSQL-targeted `qgen` output is preferred over Oracle output plus heavy rewriting.
- Per-scale raw artifact partitioning is preferred over one mixed raw file.
- Persisted raw artifacts are worth keeping and should be committable; transient checkpoint/state files should stay ignored.
- `50` parameter sets per template was treated as the balanced target for the main run.
- `3` repeated runs per logical query instance were retained.
- `10.0` was dropped from the active contract during this thread because runtime on the laptop was too expensive; `3.0` replaced it.
- The user explicitly chose to defer `3.0` and dry-run later phases first with `0.1 + 1.0`.

## Issues Encountered
- The initial `tpch-dbgen` build path involved an Oracle-derived patch block; the user rejected that and it was simplified to PostgreSQL only.
- Full collection looked frozen because logging was initially too quiet; progress logging was added later.
- Resume/checkpointing originally had crash-window and stale-artifact issues; those were reviewed and fixed in-thread.
- Fresh subset runs originally risked mixing stale scales; reviewed and fixed.
- Resume originally accepted incompatible completed manifests; reviewed and fixed.
- Direct scale invocation initially required awkward config workarounds; later changed to `collect 0.1` style.
- The “already collected” path originally trusted the manifest too much; later hardened to validate physical artifact files and counts.
- The CLI rewrite originally misreported subcommand typos as unconfigured scale factors; later fixed.
- `1.0` raw artifacts were lost during thread work and later recollected.
- `0.1` raw artifacts were overwritten by a tiny smoke slice during verification at one point in the thread. It is not certain from this thread alone whether `sf_0_1` was later recollected to a full dataset.

## Remaining Work
- Collect `sf_3_0` if phase 1b needs to be complete against the current active config.
- Confirm whether [artifacts/raw/sf_0_1](/Users/howen/dev/ivory/artifacts/raw/sf_0_1) currently contains a full collection or only the smoke slice that overwrote it during verification.
- Clean up or finish the in-progress state under [artifacts/raw/sf_1_0/.collection_state.json](/Users/howen/dev/ivory/artifacts/raw/sf_1_0/.collection_state.json) if it is not expected.
- Implement phase 2a feature extraction.

## Next Recommended Step
- If the goal is to move on with a dry run, verify `sf_0_1` and `sf_1_0` are usable and start phase 2a.
- If the goal is to fully close phase 1b under the current config, collect `3.0` first with `uv run python -m ivory.cli collect 3.0`.

## Notes for Future Agents
- Do not assume `sf_0_1` is a full dataset; this thread explicitly introduced a smoke-run overwrite risk.
- Do not assume `sf_3_0` exists; it was explicitly deferred by the user.
- `artifacts/raw/` is now intended to be persistent, not disposable scratch output.
- The user cares about operator ergonomics:
  - visible progress logging
  - direct `collect 1.0` syntax
  - safe skip behavior when data already exists
- The user also wants `prek` run and fixed before closeout.
- This handoff is based only on this thread; if the repo state has changed afterward, verify before continuing.
