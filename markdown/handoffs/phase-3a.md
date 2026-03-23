# Phase 3a Handoff

## Objective
- Implement Phase 3a baseline modeling for the assembled dataset in `artifacts/features/features.parquet`.
- Add a baseline training CLI, metrics validation CLI, durable baseline artifacts, and a readable CLI for inspecting saved baseline results.

## Status
- Complete

## What Was Implemented
- Added baseline training pipeline in `src/ivory/baseline_modeling.py`.
- Implemented deterministic query-instance train/validation/test splitting for the baseline workflow.
- Implemented baseline model families:
  - `dummy_mean`
  - `ridge`
  - `random_forest`
  - `hist_gradient_boosting`
- Trained one separate model per target:
  - `planner_total_cost`
  - `planning_time_ms`
  - `execution_time_ms`
- Selected the canonical per-target baseline model family using validation RMSE, then refit on train+validation before test evaluation.
- Excluded leakage-prone target-equivalent features for `planner_total_cost`:
  - `plan_features__planner_total_cost`
  - `null__plan_features__planner_total_cost`
- Persisted fitted estimator artifacts under `artifacts/models/baseline_estimators/<target>/<model_family>.pkl`.
- Emitted:
  - `artifacts/models/baseline_metrics.json`
  - `artifacts/models/baseline_predictions.parquet`
  - `artifacts/models/training_manifest.json`
- Added baseline metrics schema validation command.
- Added baseline results-reporting CLI with prettier output and prediction-derived context:
  - median absolute error
  - median/IQR/P90 relative error
  - RMSE and MAE as a percentage of median actual value
  - supplemental `sMAPE`
  - supplemental execution-time rank correlation
- Added tests for:
  - CLI dispatch
  - baseline training behavior
  - results output formatting
  - older-artifact fallback behavior for `results baseline`

## Files Changed
- `src/ivory/baseline_modeling.py`
  - New baseline training implementation, artifact writing, metrics computation, estimator serialization, and schema validation helper.
- `src/ivory/commands/train.py`
  - New `train baseline` CLI command.
- `src/ivory/commands/validate_metrics.py`
  - New `validate-metrics baseline` CLI command.
- `src/ivory/commands/results.py`
  - New `results baseline` CLI command for readable saved-result summaries.
- `src/ivory/cli.py`
  - Registered `train`, `validate-metrics`, and `results` command trees.
- `tests/test_baseline_modeling.py`
  - Added baseline modeling tests with temporary artifacts and patched paths/config.
- `tests/test_cli.py`
  - Added CLI dispatch coverage for `train baseline`, `validate-metrics baseline`, and `results baseline`.
- `tests/test_results_command.py`
  - Added output-format and older-artifact fallback tests for `results baseline`.
- `pyproject.toml`
  - Added dependencies:
    - `jsonschema`
    - `scikit-learn`
- `uv.lock`
  - Updated lockfile for new dependencies.
- `markdown/references.md`
  - Added references for scikit-learn API docs and jsonschema validation docs.

## Commands / Interfaces
- Added:
  - `uv run python -m ivory.cli train baseline`
  - `uv run python -m ivory.cli train baseline --seed 4221`
  - `uv run python -m ivory.cli train baseline --scale-factor 1.0`
  - `uv run python -m ivory.cli validate-metrics baseline --schema schemas/baseline_metrics.schema.json --artifact artifacts/models/baseline_metrics.json`
  - `uv run python -m ivory.cli results baseline`
  - `uv run python -m ivory.cli results baseline --metrics-artifact <path> --manifest-artifact <path> --predictions-artifact <path>`
- Changed behavior:
  - Default baseline training uses the merged feature dataset across scale factors.
  - Optional `--scale-factor` narrows training to a single scale factor.

## Artifacts / Outputs
- Generated real artifacts during this thread:
  - `artifacts/models/baseline_metrics.json`
  - `artifacts/models/baseline_predictions.parquet`
  - `artifacts/models/training_manifest.json`
  - `artifacts/models/baseline_estimators/execution_time_ms/*.pkl`
  - `artifacts/models/baseline_estimators/planner_total_cost/*.pkl`
  - `artifacts/models/baseline_estimators/planning_time_ms/*.pkl`
- Notable manifest content discussed and used:
  - `selected_model_family_per_target`
  - `model_artifact_paths`
  - `model_results`
  - `split`
  - `selected_features`
  - `excluded_columns`
  - `final_model_input_columns_per_model`

## Verification
- Ran:
  - `uv run pytest tests/test_cli.py tests/test_baseline_modeling.py`
  - `uv run pytest tests/test_cli.py tests/test_results_command.py`
  - `uv run python -m ivory.cli train baseline`
  - `uv run python -m ivory.cli train baseline --seed 4221`
  - `uv run python -m ivory.cli validate-metrics baseline --schema schemas/baseline_metrics.schema.json --artifact artifacts/models/baseline_metrics.json`
  - `uv run python -m ivory.cli results baseline`
  - `prek run`
- Outcomes:
  - Baseline training completed successfully on the real merged dataset.
  - Metrics artifact passed schema validation.
  - Same-seed reruns produced identical `baseline_metrics.json`.
  - `baseline_predictions.parquet` existed and was read successfully.
  - `prek run` passed after resolving Ruff/type-check issues and syncing the staged/unstaged copy of `src/ivory/baseline_modeling.py`.
- Real merged baseline training output observed:
  - `rows=3303`
  - `train=2115`
  - `validation=528`
  - `test=660`
- Real predictions artifact row count observed:
  - `7920`

## Decisions and Assumptions
- Followed the frozen repo contracts for `baseline_metrics.json`:
  - used `mape`, `q_error_*`, and `r2` in the schema-constrained metrics artifact
  - stored `sMAPE` and execution-time rank correlation as supplemental metrics in `training_manifest.json`
- Default baseline training uses the merged feature dataset; single-scale training is optional via `--scale-factor`.
- One separate model is trained per target, with one selected winning family per target.
- Constant-feature detection was changed to use the training partition only, not the full dataset.
- Pretty results output derives context from the held-out test partition only when `dataset_partition` is present.
- Results CLI was made backward-tolerant for older or partial artifacts:
  - missing `model_results` metadata does not crash the command
  - missing `is_selected_baseline` column falls back to target/model rows only
  - if no selected-model prediction rows are available, prediction-derived context is omitted instead of mixing models

## Issues Encountered
- `phase-3a-baseline-modeling.md` text and frozen repo schema/config were inconsistent:
  - phase text mentioned `sMAPE` and rank correlation
  - frozen schema expected `mape`, `q_error_*`, and `r2`
  - resolved by keeping schema-constrained metrics in `baseline_metrics.json` and storing supplemental metrics in the manifest
- Initial baseline modeling review found:
  - missing serialized model artifacts
  - missing supplemental metrics from the phase doc
  - tests not isolated from repo config
  - constant-feature detection used the full dataset and leaked held-out information
- Results CLI review found and this thread fixed:
  - hard dependency on `model_results`
  - hard dependency on `is_selected_baseline`
  - accidental mixing of metrics from one model with prediction summaries from another
  - loss of `dataset_partition == "test"` restriction in fallback paths
- `prek run` initially kept failing because `src/ivory/baseline_modeling.py` was `AM` in git; `prek` was checking the older staged snapshot until the file was added to the index.

## Remaining Work
- None for Phase 3a based on this thread.

## Next Recommended Step
- Start Phase 3b evaluation work: grouped-by-template evaluation, ablations, and error analysis using the saved baseline artifacts under `artifacts/models/`.

## Notes for Future Agents
- The baseline phase is implemented around `src/ivory/baseline_modeling.py`; start there for any follow-up changes.
- The selected winning model family on the real run was discussed as `random_forest` for all three targets.
- Real held-out metrics discussed from `artifacts/models/baseline_metrics.json`:
  - `planner_total_cost`: `RMSE 4171.283973`, `MAE 1035.341129`, `MAPE 0.010469`, `R2 0.999114`
  - `planning_time_ms`: `RMSE 0.928381`, `MAE 0.504509`, `MAPE 0.449585`, `R2 0.443876`
  - `execution_time_ms`: `RMSE 88.676388`, `MAE 39.317424`, `MAPE 0.101341`, `R2 0.960934`
- Real quartile-style context discussed from `results baseline` / predictions:
  - `planner_total_cost` median relative error: about `0.03%`
  - `execution_time_ms` median relative error: about `6.00%`
  - `planning_time_ms` median relative error: about `25.55%`
- There is an unrelated modification in `src/ivory/dataset_assembly.py` visible in git status that was not part of this thread’s implementation; do not revert it blindly.
