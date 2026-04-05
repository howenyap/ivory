with lineitem_rev as (
    select
        l_orderkey,
        sum(l_extendedprice * (1 - l_discount)) as order_revenue
    from lineitem
    where l_shipdate > date '1995-03-25'
    group by l_orderkey
)
select
    lr.l_orderkey,
    sum(lr.order_revenue) as revenue,
    o.o_orderdate,
    o.o_shippriority
from customer c
join orders o
  on c.c_custkey = o.o_custkey
join lineitem_rev lr
  on lr.l_orderkey = o.o_orderkey
where c.c_mktsegment = 'MACHINERY'
  and o.o_orderdate < date '1995-03-25'
group by
    lr.l_orderkey,
    o.o_orderdate,
    o.o_shippriority
order by
    revenue desc,
    o.o_orderdate
limit 10;
