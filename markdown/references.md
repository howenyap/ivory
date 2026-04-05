# References

- `TPC-H specification`
  Useful for the canonical benchmark definition, the 22-query template set, and the role of `QGEN` in producing executable query text.
  Source: [TPC-H Standard Specification Revision 2.18.0](https://tpc.org/TPC_Documents_Current_Versions/pdf/tpc-h_v2.18.0.pdf)

- `QPPNet (Marcus and Papaemmanouil, PVLDB 2019)`
  Useful as evidence that learned query-latency work on TPC-H and TPC-DS is typically done at benchmark-query counts in the tens of thousands rather than a few hundred rows.
  Source: [QPPNet: Predicting the Performance of Ad Hoc Queries Using Deep Learning](https://www.vldb.org/pvldb/vol12/p1733-marcus.pdf)

- `BICE (Liang et al., ICDM 2023)`
  Useful as direct evidence that recent TPC-H cost and cardinality estimation work trains on 22,000 TPC-H queries and evaluates on a separate TPC-H test set generated with `qgen`.
  Source: [Efficient Cardinality and Cost Estimation with Bidirectional Compressor-based Ensemble Learning](https://zheng-kai.com/paper/icdm_2023_liang.pdf)

- `QueryFormer (Zhao et al., PVLDB 2022)`
  Useful for framing that stronger learned estimators often rely on much larger and more diverse workloads than TPC-H, and that TPC-H is comparatively simple.
  Source: [QueryFormer: A Tree-Structured Transformer for Query Performance Prediction](https://www.vldb.org/pvldb/vol15/p1658-zhao.pdf)

- `How Good Are Query Optimizers, Really? (Leis et al., PVLDB 2015)`
  Useful for the limitation argument: TPC-H and similar synthetic benchmarks are valuable, but they simplify data distributions and are weaker than more realistic workloads for optimizer-estimation research.
  Source: [How Good Are Query Optimizers, Really?](https://vldb.org/pvldb/vol9/p204-leis.pdf)

- `Repository maintenance note (2026-03-23)`
  This `AGENTS.md` wording update was made without external research; the change reflects a local workflow preference requested in-session.
  Source: Local repository instruction update request

- `SQLGlot documentation`
  Useful for the parser and expression-tree API used to extract structural SQL features from PostgreSQL SQL text in Phase 2a.
  Source: [SQLGlot documentation](https://sqlglot.com/sqlglot.html)

- `PostgreSQL EXPLAIN documentation`
  Useful for the shape and semantics of PostgreSQL execution plans, including the JSON output consumed by the Phase 2b plan-feature extractor.
  Source: [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)

- `PostgreSQL EXPLAIN ANALYZE semantics`
  Useful for the query-comparison writeup because it distinguishes planner-only `EXPLAIN` output from `EXPLAIN ANALYZE`, which executes the query and reports measured runtime via `Execution Time`.
  Source: [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)

- `Polars user guide`
  Useful for the join and nested-struct DataFrame operations used to assemble the final observation-grain modeling dataset in Phase 2c.
  Source: [Polars user guide](https://docs.pola.rs/user-guide/)

- `scikit-learn regression estimator and preprocessing documentation`
  Useful for the Phase 3a baseline estimator set and preprocessing pipeline, including `DummyRegressor`, `Ridge`, `RandomForestRegressor`, `HistGradientBoostingRegressor`, `Pipeline`, and `StandardScaler`.
  Source: [scikit-learn API reference](https://scikit-learn.org/stable/modules/classes.html)

- `jsonschema validation documentation`
  Useful for validating the baseline metrics artifact against the frozen Draft 2020-12 JSON schema from the CLI.
  Source: [jsonschema schema validation docs](https://python-jsonschema.readthedocs.io/en/latest/validate/)

- `Repository CLI and setup sources (2026-03-23)`
  Useful for documenting the currently supported Ivory CLI commands and the local development setup requirements directly from the repository source.
  Source: Local repository files `pyproject.toml`, `src/ivory/cli.py`, `src/ivory/commands/collect.py`, `src/ivory/commands/featurize.py`, `src/ivory/commands/train.py`, `src/ivory/commands/results.py`, and `src/ivory/commands/validate_metrics.py`

- `Repository pipeline dependency check (2026-03-23)`
  Useful for confirming which downstream stages consume the raw `sf_*` collection artifacts and therefore must be rerun after recollecting scale factor `0.1`.
  Source: Local repository files `src/ivory/sql_features.py`, `src/ivory/plan_features.py`, `src/ivory/dataset_assembly.py`, `src/ivory/baseline_modeling.py`, and `README.md`

- `PostgreSQL WITH query materialization`
  Useful for deciding which CTE and derived-table rewrites are likely to remain structurally meaningful in PostgreSQL rather than being treated as trivial syntax wrappers.
  Source: [PostgreSQL 16 documentation: 7.8 WITH Queries](https://www.postgresql.org/docs/16/queries-with.html)

- `PostgreSQL subquery semantics`
  Useful for excluding `EXISTS`, `IN`, and `NOT IN` rewrite families that can change duplicate or null semantics relative to duplicate-preserving joins.
  Source: [PostgreSQL 16 documentation: 9.24 Subquery Expressions](https://www.postgresql.org/docs/16/functions-subquery.html)

- `PostgreSQL ordering semantics`
  Useful for treating row order as part of the equivalence contract and excluding fragile top-N rewrites where ordering is not fully determined.
  Source: [PostgreSQL 16 documentation: 7.5 Sorting Rows](https://www.postgresql.org/docs/16/queries-order.html)

- `Including Group-By in Query Optimization (Chaudhuri and Shim, VLDB 1994)`
  Useful for justifying safe early-group-by and aggregate-factoring rewrites on subgraphs where grouping keys preserve downstream semantics.
  Source: [Including Group-By in Query Optimization](https://www.microsoft.com/en-us/research/publication/including-group-by-in-query-optimization/)

- `Performing Group-by before Join (Yan and Larson, 1994)`
  Useful for the benchmark's pre-aggregation rewrite families and the conditions under which aggregate-before-join is semantically valid.
  Source: [Performing Group-by before Join](https://www.microsoft.com/en-us/research/publication/performing-group-by-before-join/)

- `Unnesting Arbitrary Queries (Neumann and Kemper, 2015)`
  Useful for decorrelation-based rewrite families such as the accepted `q17` alternatives and for reasoning about planner-relevant structural changes to nested-query forms.
  Source: [Unnesting Arbitrary Queries](https://portal.fis.tum.de/en/publications/unnesting-arbitrary-queries/)

- `A Practical Approach to Groupjoin and Nested Aggregates (Fent and Neumann, PVLDB 2021)`
  Useful for the `q13`-style outer-join-plus-aggregate rewrites where preserving zero-match rows and nested aggregate semantics is essential.
  Source: [A Practical Approach to Groupjoin and Nested Aggregates](https://vldb.org/pvldb/vol14/p2383-fent.pdf)

- `Query compare baseline source artifact (2026-04-05)`
  Useful for extracting the exact rendered `p0000` SQL text used as the baseline source for the `q13`, `q15`, and `q17` query-compare inputs at scale factor `1.0`.
  Source: Local repository artifact `artifacts/raw/sf_1_0/raw_runs.parquet`

- `Rendered q9/q11 p0000 SQL provenance (2026-04-05)`
  Useful for grounding the query-compare SQL rewrites in the exact rendered baseline text selected from the scale-factor 1.0 raw collection artifact.
  Source: Local artifact `artifacts/raw/sf_1_0/raw_runs.parquet`
