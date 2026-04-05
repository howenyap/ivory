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
annotated_rows as (
    select
        o_year,
        nation,
        volume,
        sum(volume) over (partition by o_year) as total_volume
    from
        all_nations
)
select
    o_year,
    sum(case
        when nation = 'MOROCCO' then volume
        else 0
    end) / max(total_volume) as mkt_share
from
    annotated_rows
group by
    o_year
order by
    o_year;
