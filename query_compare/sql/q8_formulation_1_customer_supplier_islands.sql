with region_customers as (
    select
        c.c_custkey
    from
        customer c
    join nation n1
        on n1.n_nationkey = c.c_nationkey
    join region r
        on r.r_regionkey = n1.n_regionkey
    where
        r.r_name = 'AFRICA'
),
filtered_parts as (
    select
        p.p_partkey
    from
        part p
    where
        p.p_type = 'MEDIUM BRUSHED NICKEL'
),
supplier_nations as (
    select
        s.s_suppkey,
        n2.n_name as nation
    from
        supplier s
    join nation n2
        on n2.n_nationkey = s.s_nationkey
),
all_nations as (
    select
        extract(year from o.o_orderdate) as o_year,
        l.l_extendedprice * (1 - l.l_discount) as volume,
        sn.nation
    from
        filtered_parts p
    join lineitem l
        on l.l_partkey = p.p_partkey
    join orders o
        on o.o_orderkey = l.l_orderkey
    join region_customers rc
        on rc.c_custkey = o.o_custkey
    join supplier_nations sn
        on sn.s_suppkey = l.l_suppkey
    where
        o.o_orderdate between date '1995-01-01' and date '1996-12-31'
)
select
    o_year,
    sum(case
        when nation = 'MOROCCO' then volume
        else 0
    end) / sum(volume) as mkt_share
from
    all_nations
group by
    o_year
order by
    o_year;
