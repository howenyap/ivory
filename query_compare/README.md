# Query Compare

This directory holds a small curated workflow for comparing alternative SQL
formulations of the same query with Ivory's trained estimator.

The benchmark follows a feasible-only coverage policy. It is curated for
plausible planner-cost discrimination, not syntax-only SQL variation, and it
keeps only templates with at least one live-validated exact-match rewrite on
`tpch_sf_1`.

The current included templates are `Q2`, `Q5`, `Q7`, `Q8`, `Q9`, `Q11`,
`Q13`, `Q15`, `Q16`, `Q17`, and `Q19`. Excluded templates remain documented in
`benchmark.json` with explicit screening rationale, validation status, and
exclusion reason.

Not every selected template has to become headline evidence. The benchmark is
intended to include a small number of structurally meaningful controls, while
headline writeup claims should come from templates that actually show realized
planner-cost separation after validation.

## Inputs

- `benchmark.json` is the machine-readable source of truth.
- `sql/*.sql` contains only the baseline and accepted alternative formulations
  for included templates.

Accepted rewrite depth is intentionally variable:

- strong templates can keep `2-3` accepted rewrites
- moderate templates can keep `1-2` accepted rewrites
- excluded or dropped templates stay in metadata only

## Phase B: Exact-Output Validation

Validation is equivalence-first:

- baseline and rewrite outputs must match exactly
- row order is part of the contract
- order-sensitive templates are rerun to confirm stable ordered output
- candidate rewrites are screened against the running Docker-backed PostgreSQL
  instance before they are kept
- the repo validator then rechecks every included baseline/rewrite pair

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
