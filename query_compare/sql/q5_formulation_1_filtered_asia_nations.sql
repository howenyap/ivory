with asia_nations as (
    select
        n.n_nationkey,
        n.n_name
    from
        nation n
    join region r
        on r.r_regionkey = n.n_regionkey
    where
        r.r_name = 'ASIA'
)
select
    an.n_name,
    sum(l.l_extendedprice * (1 - l.l_discount)) as revenue
from
    asia_nations an
join supplier s
    on s.s_nationkey = an.n_nationkey
join customer c
    on c.c_nationkey = an.n_nationkey
join orders o
    on o.o_custkey = c.c_custkey
join lineitem l
    on l.l_orderkey = o.o_orderkey
    and l.l_suppkey = s.s_suppkey
where
    o.o_orderdate >= date '1994-01-01'
    and o.o_orderdate < date '1994-01-01' + interval '1 year'
group by
    an.n_name
order by
    revenue desc;
