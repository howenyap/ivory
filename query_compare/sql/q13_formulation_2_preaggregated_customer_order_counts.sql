with customer_order_counts as (
    select
        o.o_custkey,
        count(*) as c_count
    from
        orders o
    where
        o.o_comment not like '%pending%deposits%'
    group by
        o.o_custkey
)
select
    customer_counts.c_count,
    count(*) as custdist
from (
    select
        c.c_custkey,
        coalesce(coc.c_count, 0) as c_count
    from
        customer c
    left join customer_order_counts coc
        on coc.o_custkey = c.c_custkey
) as customer_counts
group by
    customer_counts.c_count
order by
    custdist desc,
    customer_counts.c_count desc;
