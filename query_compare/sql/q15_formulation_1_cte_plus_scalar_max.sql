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
max_revenue as (
    select
        max(total_revenue) as max_total_revenue
    from
        revenue0
)
select
    s.s_suppkey,
    s.s_name,
    s.s_address,
    s.s_phone,
    r.total_revenue
from
    supplier s
join revenue0 r
    on s.s_suppkey = r.supplier_no
cross join max_revenue m
where
    r.total_revenue = m.max_total_revenue
order by
    s.s_suppkey;
