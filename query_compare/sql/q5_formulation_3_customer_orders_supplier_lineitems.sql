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
),
nation_customer_orders as (
    select
        o.o_orderkey,
        an.n_name,
        an.n_nationkey
    from
        asia_nations an
    join customer c
        on c.c_nationkey = an.n_nationkey
    join orders o
        on o.o_custkey = c.c_custkey
    where
        o.o_orderdate >= date '1994-01-01'
        and o.o_orderdate < date '1994-01-01' + interval '1 year'
),
supplier_lineitems as (
    select
        l.l_orderkey,
        s.s_nationkey,
        l.l_extendedprice * (1 - l.l_discount) as revenue
    from
        supplier s
    join lineitem l
        on l.l_suppkey = s.s_suppkey
)
select
    nco.n_name,
    sum(sl.revenue) as revenue
from
    nation_customer_orders nco
join supplier_lineitems sl
    on sl.l_orderkey = nco.o_orderkey
    and sl.s_nationkey = nco.n_nationkey
group by
    nco.n_name
order by
    revenue desc;
