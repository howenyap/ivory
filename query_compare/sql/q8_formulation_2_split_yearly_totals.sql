with all_nations as (
    select
        extract(year from o.o_orderdate) as o_year,
        l.l_extendedprice * (1 - l.l_discount) as volume,
        n2.n_name as nation
    from
        part p
    join lineitem l
        on l.l_partkey = p.p_partkey
    join orders o
        on o.o_orderkey = l.l_orderkey
    join customer c
        on c.c_custkey = o.o_custkey
    join nation n1
        on n1.n_nationkey = c.c_nationkey
    join region r
        on r.r_regionkey = n1.n_regionkey
    join supplier s
        on s.s_suppkey = l.l_suppkey
    join nation n2
        on n2.n_nationkey = s.s_nationkey
    where
        r.r_name = 'AFRICA'
        and o.o_orderdate between date '1995-01-01' and date '1996-12-31'
        and p.p_type = 'MEDIUM BRUSHED NICKEL'
),
yearly_totals as (
    select
        o_year,
        sum(volume) as total_volume
    from
        all_nations
    group by
        o_year
),
morocco_totals as (
    select
        o_year,
        sum(volume) as morocco_volume
    from
        all_nations
    where
        nation = 'MOROCCO'
    group by
        o_year
)
select
    y.o_year,
    coalesce(m.morocco_volume, 0) / y.total_volume as mkt_share
from
    yearly_totals y
left join morocco_totals m
    on m.o_year = y.o_year
order by
    y.o_year;
