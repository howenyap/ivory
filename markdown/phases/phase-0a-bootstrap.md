# Phase 0a: Bootstrap

## Codex Prompt Contract

Implement only the bootstrap scaffolding for the `ivory` project. Do not build PostgreSQL integration, dataset logic, feature extraction, or ML code in this phase. Before stopping, run every verification command in this file and ensure the CLI and imports work through `uv`.

## Objective

Initialize the repository as a runnable Python project managed by `uv`, pinned to Python `3.14`, with a stable package layout, CLI skeleton, and config skeleton. The goal of this phase is not to implement any project logic. The goal is to create the minimum project structure that every later phase can depend on without renaming files or rethinking the package boundary.

## Inputs / Dependencies

- Repository root exists.
- [`../plan.md`](../plan.md) is the high-level project plan.
- No code from later phases should be required.

## Implementation Steps

1. Initialize the Python project with `uv` and ensure the canonical interpreter is Python `3.14`.
2. Create `pyproject.toml` with:
   - project metadata
   - `requires-python = ">=3.14,<3.15"`
   - core dependencies for the project skeleton only
   - optional dependency groups for dev tools if needed
3. Create the package layout:
   - `src/ivory/__init__.py`
   - `src/ivory/cli.py`
   - `src/ivory/config.py`
   - `src/ivory/commands/__init__.py`
4. Add a CLI skeleton that exposes placeholder commands for:
   - `collect`
   - `featurize`
   - `train`
   - `evaluate`
   - `report-assets`
5. Add a config skeleton with a stable minimal API:
   - `ivory.config.load_config(path: str | None = None)`
   - default path `configs/experiment.toml`
   - a predictable error if the file does not exist yet
6. Create the stable top-level directory layout:
   - `artifacts/`
   - `configs/`
   - `schemas/`
   - `src/`
   - `tests/`
7. Create a `.python-version` file if needed to reduce accidental interpreter drift in local runs.
8. Run `uv sync` and generate `uv.lock`.
9. Confirm the package is runnable through `uv run python -m ivory.cli --help`.

## Deliverables

- `pyproject.toml`
- `uv.lock`
- `.python-version` if used
- `src/ivory/__init__.py`
- `src/ivory/cli.py`
- `src/ivory/config.py`
- `src/ivory/commands/__init__.py`
- `artifacts/`
- `configs/`
- `schemas/`
- `tests/`

## Verification

Run these checks from the repository root:

```bash
uv sync
```

Expected result:
- the environment resolves successfully
- `uv.lock` is created or updated

```bash
uv run python --version
```

Expected result:
- output shows Python `3.14.x`

```bash
uv run python -m ivory.cli --help
```

Expected result:
- the CLI prints usage text
- all five top-level commands are visible

```bash
uv run python -c "import ivory, ivory.cli, ivory.config"
```

Expected result:
- process exits successfully with no import errors

```bash
uv run python -c "import ivory.config as c; print(hasattr(c, 'load_config'))"
```

Expected result:
- prints `True`

```bash
uv run python - <<'PY'
import ivory.config as c

try:
    c.load_config()
    raise SystemExit("expected load_config() to fail before configs/experiment.toml exists")
except Exception as e:
    assert "experiment.toml" in str(e) or isinstance(e, FileNotFoundError)
    print(type(e).__name__)
PY
```

Expected result:
- `load_config()` fails in a predictable way before the config file exists
- the failure mentions `experiment.toml` or uses a file-not-found style error

```bash
find src/ivory -maxdepth 2 -type f | sort
```

Expected result:
- the package skeleton files are present

## Definition of Done

- `uv` manages the project successfully.
- Python `3.14` is the active project runtime.
- The `ivory` package imports successfully.
- The CLI help command works through `uv run`.
- `ivory.config.load_config` exists with the default-path contract.
- The repo layout matches the contract in this file.
- No phase-specific business logic has leaked into the bootstrap layer.

## Common Failure Modes

- Using the system Python instead of the `uv` environment.
- Letting the CLI command names drift from the canonical interface.
- Adding later-phase dependencies before they are needed.
- Hardcoding paths in the CLI instead of centralizing config loading.
- Omitting `uv.lock`, which breaks reproducibility for later phases.
