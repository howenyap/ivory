with shipping as (
    select
        n1.n_name as supp_nation,
        n2.n_name as cust_nation,
        extract(year from l.l_shipdate) as l_year,
        l.l_extendedprice * (1 - l.l_discount) as volume
    from
        supplier s
    join lineitem l
        on l.l_suppkey = s.s_suppkey
    join orders o
        on o.o_orderkey = l.l_orderkey
    join customer c
        on c.c_custkey = o.o_custkey
    join nation n1
        on n1.n_nationkey = s.s_nationkey
    join nation n2
        on n2.n_nationkey = c.c_nationkey
    where
        n1.n_name = 'GERMANY'
        and n2.n_name = 'MOZAMBIQUE'
        and l.l_shipdate between date '1995-01-01' and date '1996-12-31'

    union all

    select
        n1.n_name as supp_nation,
        n2.n_name as cust_nation,
        extract(year from l.l_shipdate) as l_year,
        l.l_extendedprice * (1 - l.l_discount) as volume
    from
        supplier s
    join lineitem l
        on l.l_suppkey = s.s_suppkey
    join orders o
        on o.o_orderkey = l.l_orderkey
    join customer c
        on c.c_custkey = o.o_custkey
    join nation n1
        on n1.n_nationkey = s.s_nationkey
    join nation n2
        on n2.n_nationkey = c.c_nationkey
    where
        n1.n_name = 'MOZAMBIQUE'
        and n2.n_name = 'GERMANY'
        and l.l_shipdate between date '1995-01-01' and date '1996-12-31'
)
select
    supp_nation,
    cust_nation,
    l_year,
    sum(volume) as revenue
from
    shipping
group by
    supp_nation,
    cust_nation,
    l_year
order by
    supp_nation,
    cust_nation,
    l_year;
