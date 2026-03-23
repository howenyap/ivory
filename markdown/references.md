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

- `Polars user guide`
  Useful for the join and nested-struct DataFrame operations used to assemble the final observation-grain modeling dataset in Phase 2c.
  Source: [Polars user guide](https://docs.pola.rs/user-guide/)
