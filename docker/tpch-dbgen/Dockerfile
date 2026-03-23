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
    && grep -q '^#ifdef POSTGRES$' tpcd.h || printf '\n#ifdef POSTGRES\n#define GEN_QUERY_PLAN ""\n#define START_TRAN ""\n#define END_TRAN ""\n#define SET_OUTPUT ""\n#define SET_ROWCOUNT "limit %%d;\\n"\n#define SET_DBASE ""\n#endif\n' >> tpcd.h \
    && make MACHINE=LINUX DATABASE=POSTGRES WORKLOAD=TPCH \
    && install -m 0755 dbgen /usr/local/bin/dbgen \
    && install -m 0755 qgen /usr/local/bin/qgen

WORKDIR /workspace
ENTRYPOINT ["/bin/bash", "-lc"]
