with filtered_part as (
    select
        p_partkey
    from
        part
    where
        p_name like '%indian%'
)
select
    profit.nation,
    profit.o_year,
    sum(profit.amount) as sum_profit
from (
    select
        n.n_name as nation,
        extract(year from o.o_orderdate) as o_year,
        l.l_extendedprice * (1 - l.l_discount) - ps.ps_supplycost * l.l_quantity as amount
    from
        filtered_part p
    join lineitem l
        on l.l_partkey = p.p_partkey
    join partsupp ps
        on ps.ps_partkey = l.l_partkey
        and ps.ps_suppkey = l.l_suppkey
    join orders o
        on o.o_orderkey = l.l_orderkey
    join supplier s
        on s.s_suppkey = l.l_suppkey
    join nation n
        on n.n_nationkey = s.s_nationkey
) as profit
group by
    profit.nation,
    profit.o_year
order by
    profit.nation,
    profit.o_year desc;
