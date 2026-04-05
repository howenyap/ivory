with revenue0 as (
    select
        l.l_suppkey as supplier_no,
        sum(l.l_extendedprice * (1 - l.l_discount)) as total_revenue
    from
        lineitem l
    where
        l.l_shipdate >= date '1995-06-01'
        and l.l_shipdate < date '1995-06-01' + interval '3 month'
    group by
        l.l_suppkey
),
ranked_revenue as (
    select
        supplier_no,
        total_revenue,
        dense_rank() over (order by total_revenue desc) as revenue_rank
    from
        revenue0
)
select
    s.s_suppkey,
    s.s_name,
    s.s_address,
    s.s_phone,
    rr.total_revenue
from
    supplier s
join ranked_revenue rr
    on s.s_suppkey = rr.supplier_no
where
    rr.revenue_rank = 1
order by
    s.s_suppkey;
