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
orders_in_range as (
    select
        o.o_orderkey,
        o.o_custkey
    from
        orders o
    where
        o.o_orderdate >= date '1994-01-01'
        and o.o_orderdate < date '1994-01-01' + interval '1 year'
),
customer_orders as (
    select
        o.o_orderkey,
        c.c_nationkey
    from
        orders_in_range o
    join customer c
        on c.c_custkey = o.o_custkey
),
asia_suppliers as (
    select
        s.s_suppkey,
        an.n_nationkey,
        an.n_name
    from
        supplier s
    join asia_nations an
        on an.n_nationkey = s.s_nationkey
)
select
    asup.n_name,
    sum(l.l_extendedprice * (1 - l.l_discount)) as revenue
from
    customer_orders co
join lineitem l
    on l.l_orderkey = co.o_orderkey
join asia_suppliers asup
    on asup.s_suppkey = l.l_suppkey
    and asup.n_nationkey = co.c_nationkey
group by
    asup.n_name
order by
    revenue desc;
