select
    customer_counts.c_count,
    count(*) as custdist
from (
    select
        c.c_custkey,
        coalesce(order_counts.c_count, 0) as c_count
    from
        customer c
    left join lateral (
        select
            count(*) as c_count
        from
            orders o
        where
            o.o_custkey = c.c_custkey
            and o.o_comment not like '%pending%deposits%'
    ) as order_counts
        on true
) as customer_counts
group by
    customer_counts.c_count
order by
    custdist desc,
    customer_counts.c_count desc;
