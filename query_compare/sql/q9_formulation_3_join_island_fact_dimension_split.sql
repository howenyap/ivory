with supplier_nations as (
    select
        s.s_suppkey,
        n.n_name as nation
    from
        supplier s
    join nation n
        on n.n_nationkey = s.s_nationkey
),
fact_rows as (
    select
        l.l_suppkey,
        l.l_orderkey,
        l.l_extendedprice,
        l.l_discount,
        l.l_quantity,
        ps.ps_supplycost
    from
        part p
    join lineitem l
        on l.l_partkey = p.p_partkey
    join partsupp ps
        on ps.ps_partkey = l.l_partkey
        and ps.ps_suppkey = l.l_suppkey
    where
        p.p_name like '%indian%'
)
select
    sn.nation,
    extract(year from o.o_orderdate) as o_year,
    sum(
        fr.l_extendedprice * (1 - fr.l_discount)
        - fr.ps_supplycost * fr.l_quantity
    ) as sum_profit
from
    fact_rows fr
join supplier_nations sn
    on sn.s_suppkey = fr.l_suppkey
join orders o
    on o.o_orderkey = fr.l_orderkey
group by
    sn.nation,
    extract(year from o.o_orderdate)
order by
    sn.nation,
    o_year desc;
