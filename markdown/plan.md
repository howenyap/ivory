# Project 6 Plan: ML Cost Estimator for PostgreSQL

## Summary
Build a research-first, reproducible experiment pipeline that predicts PostgreSQL query `Total Cost`, `Planning Time`, and `Execution Time`. Use `Python 3.14`, `uv` for environment and package management, `polars` for data processing, and `scikit-learn` for the core modeling stack. Keep the project centered on TPC-H, classical supervised learning, and reproducible experimental results rather than a user-facing assistant tool.

## Key Changes / Implementation Plan
### Phase 0: Stack, repo, and experiment contract
- Initialize the project with `uv` and pin `Python 3.14` as the canonical runtime.
- Standardize the main stack:
  - `polars` for tabular data pipelines
  - `scikit-learn` for model training and evaluation
  - `sqlglot` for SQL parsing
  - `matplotlib` or `seaborn` for figures
  - PostgreSQL accessed through a thin Python client layer
- Create a greenfield repo structure around reproducibility: `src/`, `data/`, `experiments/`, `infra/`, `figures/`, `reports/`.
- Define one stable pipeline interface for each stage: `collect`, `featurize`, `train`, `evaluate`, `report-assets`.
- Lock the experiment contract up front:
  - PostgreSQL version
  - machine profile
  - TPC-H scale factors
  - query run count
  - timeout policy
  - warm vs cold cache policy
  - fixed seed and split policy

### Phase 1: PostgreSQL + TPC-H benchmark setup
- Provision PostgreSQL locally with Docker and load TPC-H at scale factors `1`, `3`, and `10`.
- Generate parameterized query instances for all 22 TPC-H templates.
- Target roughly `50-100` parameter sets per template per scale factor, adjusted downward only if runtime becomes a bottleneck.
- Execute each query with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` and store:
  - raw SQL
  - template id
  - parameter values
  - scale factor
  - plan JSON
  - planner total cost
  - planning time
  - execution time
  - selected top-level plan metadata
- Run each query multiple times and choose one canonical labeling policy for the main study. Recommended default: warm-cache median of 3 runs.
- Record failures, timeouts, and excluded runs explicitly so the dataset can be audited and regenerated.

### Phase 2: Feature engineering with `polars`
- Build the raw-to-feature pipeline in `polars` end to end.
- Extract SQL-structural features:
  - join count
  - predicate count
  - aggregation presence
  - sort/limit presence
  - subquery count
  - table count
  - selected column count
  - operator/token counts where useful
- Extract plan-summary features from PostgreSQL JSON plans:
  - node-type counts
  - plan tree depth
  - scan/join/aggregate operator mix
  - estimated rows and widths summaries
  - node-level cost aggregates
- Keep the feature set tabular and interpretable.
- Materialize clean modeling datasets as `parquet` outputs to support fast iteration and reproducibility.

### Phase 3: Model training and evaluation with `scikit-learn`
- Train separate regressors for:
  - planner cost
  - planning time
  - execution time
- Use baseline and comparison models that fit the course scope:
  - dummy mean/median regressor
  - linear regression / ridge
  - random forest regressor
  - gradient boosting or histogram gradient boosting
- For execution time, include PostgreSQL’s own `Total Cost` as a non-ML baseline and optionally add a simple linear calibration on top of it.
- Evaluate under two split regimes:
  - random instance split for in-distribution performance
  - grouped split by query template for harder generalization
- Report `MAE`, `RMSE`, and `sMAPE`; for execution time also report rank correlation.
- Run ablations that make the paper defensible:
  - SQL-only vs plan-based features
  - single-scale vs multi-scale training
  - baseline cost proxy vs learned model
- Add targeted error analysis on the most poorly predicted query templates and operator patterns.

### Phase 4: Reproducibility, paper, and video
- Provide one-command reproduction for the main experiment and figure generation through `uv run ...`.
- Generate final tables and figures directly from experiment outputs so the paper is not manually maintained.
- Draft the report in parallel with implementation:
  - Background and Related Work begin once the stack is fixed
  - Methodology starts once data collection and featurization stabilize
  - Performance Evaluation is filled from the generated metrics and plots
- Build the video around a compact flow:
  - problem statement
  - PostgreSQL/TPC-H setup
  - feature + model pipeline
  - evaluation results
  - limitations and conclusion
- Leave the final buffer for reruns, compression to page limit, figure cleanup, and rehearsed narration.

## Public Interfaces / Outputs
- Stable CLI commands:
  - `collect`
  - `featurize`
  - `train`
  - `evaluate`
  - `report-assets`
- Standard outputs:
  - `raw_runs.parquet`
  - `plans.jsonl`
  - `features.parquet`
  - `metrics.json` or `metrics.csv`
  - `figures/` for paper/video assets
- Config surface should stay small and explicit:
  - Python version
  - PostgreSQL version
  - scale factors
  - number of runs
  - timeout
  - seed
  - split mode

## Test Plan
- Smoke-test the full pipeline on a tiny subset: 2 TPC-H templates, 1 scale factor, a few parameter settings.
- Validate that labels extracted into tabular outputs match the PostgreSQL JSON source.
- Snapshot-test a few featurization outputs for known queries and plan shapes.
- Verify training/evaluation reproducibility with a fixed seed.
- Exercise timeout and malformed-plan handling paths.
- Before submission, rerun the main experiment from a clean `uv` environment and confirm that figures and tables regenerate without manual edits.

## Assumptions and Defaults
- Chosen so far:
  - project is **research first**
  - workload is **TPC-H first**
  - query-assistance feature is **out of scope**
  - implementation artifact is a **reproducible pipeline**
  - stack is `Python 3.14` + `uv` + `polars` + `scikit-learn`
- Recommended defaults:
  - PostgreSQL `16`
  - Docker-based local setup
  - warm-cache median-of-3 labels
  - grouped-by-template evaluation to avoid overstating generalization
- Optional extension only if time remains:
  - add one stronger comparison model or an extra scale factor after the core pipeline and paper results are stable
