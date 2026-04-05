with dated_lineitems as (
    select
        l.l_orderkey,
        l.l_suppkey,
        extract(year from l.l_shipdate) as l_year,
        l.l_extendedprice * (1 - l.l_discount) as volume
    from
        lineitem l
    where
        l.l_shipdate between date '1995-01-01' and date '1996-12-31'
),
customer_orders as (
    select
        o.o_orderkey,
        n.n_name as cust_nation
    from
        orders o
    join customer c
        on c.c_custkey = o.o_custkey
    join nation n
        on n.n_nationkey = c.c_nationkey
    where
        n.n_name in ('GERMANY', 'MOZAMBIQUE')
),
supplier_nations as (
    select
        s.s_suppkey,
        n.n_name as supp_nation
    from
        supplier s
    join nation n
        on n.n_nationkey = s.s_nationkey
    where
        n.n_name in ('GERMANY', 'MOZAMBIQUE')
)
select
    sn.supp_nation,
    co.cust_nation,
    dl.l_year,
    sum(dl.volume) as revenue
from
    dated_lineitems dl
join customer_orders co
    on co.o_orderkey = dl.l_orderkey
join supplier_nations sn
    on sn.s_suppkey = dl.l_suppkey
where
    (sn.supp_nation = 'GERMANY' and co.cust_nation = 'MOZAMBIQUE')
    or (sn.supp_nation = 'MOZAMBIQUE' and co.cust_nation = 'GERMANY')
group by
    sn.supp_nation,
    co.cust_nation,
    dl.l_year
order by
    sn.supp_nation,
    co.cust_nation,
    dl.l_year;
