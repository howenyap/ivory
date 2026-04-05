select
    c_count,
    count(*) as custdist
from (
    select
        c.c_custkey,
        count(o.o_orderkey) as c_count
    from
        customer c
    left join (
        select
            o_orderkey,
            o_custkey
        from
            orders
        where
            o_comment not like '%pending%deposits%'
    ) as o
        on c.c_custkey = o.o_custkey
    group by
        c.c_custkey
) as customer_orders
group by
    c_count
order by
    custdist desc,
    c_count desc;
