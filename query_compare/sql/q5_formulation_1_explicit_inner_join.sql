select
    n.n_name,
    sum(l.l_extendedprice * (1 - l.l_discount)) as revenue
from customer c
join orders o
    on c.c_custkey = o.o_custkey
join lineitem l
    on l.l_orderkey = o.o_orderkey
join supplier s
    on l.l_suppkey = s.s_suppkey
join nation n
    on s.s_nationkey = n.n_nationkey
join region r
    on n.n_regionkey = r.r_regionkey
where c.c_nationkey = s.s_nationkey
  and r.r_name = 'ASIA'
  and o.o_orderdate >= date '1994-01-01'
  and o.o_orderdate < date '1994-01-01' + interval '1 year'
group by n.n_name
order by revenue desc;
