with q10_rows as (
    select
        c.c_custkey,
        c.c_name,
        c.c_acctbal,
        n.n_name,
        c.c_address,
        c.c_phone,
        c.c_comment,
        l.l_extendedprice,
        l.l_discount
    from customer c
    join orders o
        on o.o_custkey = c.c_custkey
    join lineitem l
        on l.l_orderkey = o.o_orderkey
    join nation n
        on n.n_nationkey = c.c_nationkey
    where o.o_orderdate >= date '1994-08-01'
      and o.o_orderdate < date '1994-08-01' + interval '3 month'
      and l.l_returnflag = 'R'
)
select
    c_custkey,
    c_name,
    sum(l_extendedprice * (1 - l_discount)) as revenue,
    c_acctbal,
    n_name,
    c_address,
    c_phone,
    c_comment
from q10_rows
group by
    c_custkey,
    c_name,
    c_acctbal,
    c_phone,
    n_name,
    c_address,
    c_comment
order by revenue desc
limit 20;
