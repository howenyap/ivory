with
c as (
    select *
    from customer
    where c_mktsegment = 'MACHINERY'
),
o as (
    select *
    from orders
    where o_orderdate < date '1995-03-25'
),
l as (
    select *
    from lineitem
    where l_shipdate > date '1995-03-25'
)
select
    l.l_orderkey,
    sum(l.l_extendedprice * (1 - l.l_discount)) as revenue,
    o.o_orderdate,
    o.o_shippriority
from c
join o
  on c.c_custkey = o.o_custkey
join l
  on l.l_orderkey = o.o_orderkey
group by
    l.l_orderkey,
    o.o_orderdate,
    o.o_shippriority
order by
    revenue desc,
    o.o_orderdate
limit 10;
