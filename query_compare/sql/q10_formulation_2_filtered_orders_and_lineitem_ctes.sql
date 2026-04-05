with orders_f as (
    select o_orderkey, o_custkey
    from orders
    where o_orderdate >= date '1994-08-01'
      and o_orderdate < date '1994-08-01' + interval '3 month'
),
lineitem_f as (
    select l_orderkey, l_extendedprice, l_discount
    from lineitem
    where l_returnflag = 'R'
)
select
    c.c_custkey,
    c.c_name,
    sum(l.l_extendedprice * (1 - l.l_discount)) as revenue,
    c.c_acctbal,
    n.n_name,
    c.c_address,
    c.c_phone,
    c.c_comment
from customer c
join orders_f o
    on o.o_custkey = c.c_custkey
join lineitem_f l
    on l.l_orderkey = o.o_orderkey
join nation n
    on n.n_nationkey = c.c_nationkey
group by
    c.c_custkey,
    c.c_name,
    c.c_acctbal,
    c.c_phone,
    n.n_name,
    c.c_address,
    c.c_comment
order by revenue desc
limit 20;
