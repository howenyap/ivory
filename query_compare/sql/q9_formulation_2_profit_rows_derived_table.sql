with profit_rows as (
    select
        n.n_name as nation,
        extract(year from o.o_orderdate) as o_year,
        l.l_extendedprice * (1 - l.l_discount) - ps.ps_supplycost * l.l_quantity as amount
    from
        lineitem l
    join partsupp ps
        on ps.ps_partkey = l.l_partkey
        and ps.ps_suppkey = l.l_suppkey
    join orders o
        on o.o_orderkey = l.l_orderkey
    join supplier s
        on s.s_suppkey = l.l_suppkey
    join nation n
        on n.n_nationkey = s.s_nationkey
    join part p
        on p.p_partkey = l.l_partkey
    where
        p.p_name like '%indian%'
)
select
    nation,
    o_year,
    sum(amount) as sum_profit
from
    profit_rows
group by
    nation,
    o_year
order by
    nation,
    o_year desc;
