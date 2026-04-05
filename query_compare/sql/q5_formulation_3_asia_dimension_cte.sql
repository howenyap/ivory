with asia_nation as (
    select n.n_nationkey, n.n_name
    from nation n
    join region r
        on n.n_regionkey = r.r_regionkey
    where r.r_name = 'ASIA'
)
select
    an.n_name,
    sum(l.l_extendedprice * (1 - l.l_discount)) as revenue
from customer c
join orders o
    on c.c_custkey = o.o_custkey
join lineitem l
    on l.l_orderkey = o.o_orderkey
join supplier s
    on l.l_suppkey = s.s_suppkey
join asia_nation an
    on s.s_nationkey = an.n_nationkey
where c.c_nationkey = s.s_nationkey
  and o.o_orderdate >= date '1994-01-01'
  and o.o_orderdate < date '1994-01-01' + interval '1 year'
group by an.n_name
order by revenue desc;
