FROM debian:bookworm-slim

ARG TPCH_DBGEN_REPO
ARG TPCH_DBGEN_COMMIT

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone "${TPCH_DBGEN_REPO}" tpch-dbgen \
    && cd tpch-dbgen \
    && git checkout "${TPCH_DBGEN_COMMIT}" \
    && make MACHINE=LINUX DATABASE=ORACLE WORKLOAD=TPCH \
    && install -m 0755 dbgen /usr/local/bin/dbgen

WORKDIR /workspace
ENTRYPOINT ["/bin/bash", "-lc"]
