# Query Compare

This directory holds a small curated workflow for comparing alternative SQL
formulations of the same query with Ivory's trained estimator.

The benchmark is curated for plausible planner-cost discrimination, not
syntax-only SQL variation. It uses five rendered TPC-H templates on
`tpch_sf_1`: `Q9`, `Q11`, `Q13`, `Q15`, and `Q17`.

Not every selected template has to become headline evidence. The benchmark is
intended to include a small number of structurally meaningful controls, while
headline writeup claims should come from templates that actually show realized
planner-cost separation after validation.

## Inputs

- `benchmark.json` is the machine-readable source of truth.
- `sql/*.sql` contains the baseline and three accepted alternative
  formulations for each selected template.

## Phase B: Exact-Output Validation

Validation is equivalence-first:

- baseline and rewrite outputs must match exactly
- row order is part of the contract
- order-sensitive templates are rerun to confirm stable ordered output
- live outputs are inspected against the active PostgreSQL instance used for
  validation in this run, not just compared as pass/fail hashes

Run the validator to confirm each accepted alternative matches the baseline's
exact ordered output on `tpch_sf_1`:

```bash
./.venv/bin/python -m ivory.query_compare_validation --database tpch_sf_1
```

The validator writes machine-readable output to
`query_compare/results/validation/`.

## Phase C: Estimator Comparison

After equivalence is established, run the prediction step to compare accepted
formulations with the trained `planner_total_cost` estimator:

```bash
./.venv/bin/python -m ivory.query_compare_prediction --database tpch_sf_1
```

To also collect measured runtime for writeup-ready comparison against planner
cost and model-predicted cost, run:

```bash
./.venv/bin/python -m ivory.query_compare_prediction --database tpch_sf_1 --analyze
```

This step:

- runs `EXPLAIN (FORMAT JSON)` for each formulation by default
- optionally runs `EXPLAIN (ANALYZE, FORMAT JSON)` to capture
  `execution_time_ms`
- extracts the existing SQL and plan features
- loads the selected `planner_total_cost` model from
  `artifacts/models/training_manifest.json`
- writes explain captures to `query_compare/results/explains/`
- writes prediction artifacts to `query_compare/results/predictions/`

The Parquet artifact under `query_compare/results/predictions/` is the
canonical comparison output. The companion JSON summary reports, per template,
the baseline formulation, the lowest planner-cost formulation, the lowest
model-predicted formulation, the lowest runtime formulation when analyze mode
is enabled, agreement between those winners, and pairwise dense-rank
correlations.
