# ivory

Ivory provisions a reproducible PostgreSQL + TPC-H benchmark environment for later collection and modeling phases.

## Phase 1a workflow

Bring the local benchmark environment up:

```bash
uv run python -m ivory.cli collect load-db
```

If cached `.tbl` files already exist for a scale factor, `load-db` will prompt before regenerating them. Answering `no` reuses the existing files as-is.
When `load-db` is run without interactive stdin, it will safely reuse existing cached `.tbl` files instead of raising an input error. Use `reload-db` to force regeneration in non-interactive runs.

Stop the PostgreSQL container without deleting data:

```bash
uv run python -m ivory.cli collect stop-db
```

Reset the PostgreSQL container state:

```bash
uv run python -m ivory.cli collect reset-db
```

Recreate PostgreSQL and reload every configured scale factor:

```bash
uv run python -m ivory.cli collect reload-db
```

`reload-db` is the force-refresh path: it does not prompt and always regenerates the TPC-H flat files.

Smoke checks:

```bash
uv run python -m ivory.cli collect db-health
uv run python -m ivory.cli collect db-row-counts
uv run python -m ivory.cli collect db-smoke-query
```

## TPC-H data generation

This phase uses a pinned Docker-built `dbgen` binary from `https://github.com/electrum/tpch-dbgen.git` at commit `32f1c1b92d1664dba542e927d23d86ffa57aa253`. Generated flat files are written under `artifacts/tpch-data/` and then bulk-loaded into PostgreSQL databases defined by the frozen scale-factor mapping in `configs/experiment.toml`.

The pinned values in `docker-compose.yml` are intentionally concrete so raw `docker compose` commands work directly from the repo root. `validate-config` checks that those pinned Compose values still match the canonical PostgreSQL contract in `configs/experiment.toml`.
