# ivory

Ivory provisions a reproducible PostgreSQL + TPC-H benchmark environment for later collection and modeling phases.

## Development setup

Requirements:

- Python `3.14`
- [`uv`](https://docs.astral.sh/uv/)
- Docker with `docker compose`

Install the project and dev tools:

```bash
uv sync --dev
```

Run the CLI with either of these forms:

```bash
uv run ivory --help
uv run python -m ivory.cli --help
```

## CLI commands

Top-level commands currently exposed by the CLI:

- `collect`
- `featurize`
- `train`
- `results`
- `validate-config`
- `validate-metrics`
- `evaluate` (placeholder, not implemented)
- `report-assets` (placeholder, not implemented)

`collect` offers both raw artifact collection and PostgreSQL environment management:

- `collect start-db`
- `collect stop-db`
- `collect reset-db`
- `collect load-db`
- `collect reload-db`
- `collect db-health`
- `collect db-row-counts`
- `collect db-smoke-query`

`featurize` offers:

- `featurize sql`
- `featurize plan`
- `featurize assemble`

`train` offers:

- `train baseline`

`results` offers:

- `results baseline`

`validate-metrics` offers:

- `validate-metrics baseline`

## Common commands

Bring the local benchmark environment up:

```bash
uv run ivory collect load-db
```

If cached `.tbl` files already exist for a scale factor, `load-db` will prompt before regenerating them. Answering `no` reuses the existing files as-is.
When `load-db` is run without interactive stdin, it will safely reuse existing cached `.tbl` files instead of raising an input error. Use `reload-db` to force regeneration in non-interactive runs.

Stop the PostgreSQL container without deleting data:

```bash
uv run ivory collect stop-db
```

Reset the PostgreSQL container state:

```bash
uv run ivory collect reset-db
```

Recreate PostgreSQL and reload every configured scale factor:

```bash
uv run ivory collect reload-db
```

`reload-db` is the force-refresh path: it does not prompt and always regenerates the TPC-H flat files.

Smoke checks:

```bash
uv run ivory collect db-health
uv run ivory collect db-row-counts
uv run ivory collect db-smoke-query
```

Run raw collection:

```bash
uv run ivory collect
```

Build feature artifacts:

```bash
uv run ivory featurize sql
uv run ivory featurize plan
uv run ivory featurize assemble
```

Train and inspect the baseline model:

```bash
uv run ivory train baseline
uv run ivory results baseline
```

Validate configuration and metrics artifacts:

```bash
uv run ivory validate-config
uv run ivory validate-metrics baseline --schema path/to/schema.json --artifact path/to/artifact.json
```

## TPC-H data generation

This phase uses a pinned Docker-built `dbgen` binary from `https://github.com/electrum/tpch-dbgen.git` at commit `32f1c1b92d1664dba542e927d23d86ffa57aa253`. Generated flat files are written under `artifacts/tpch-data/` and then bulk-loaded into PostgreSQL databases defined by the frozen scale-factor mapping in `configs/experiment.toml`.

The pinned values in `docker-compose.yml` are intentionally concrete so raw `docker compose` commands work directly from the repo root. `validate-config` checks that those pinned Compose values still match the canonical PostgreSQL contract in `configs/experiment.toml`.
