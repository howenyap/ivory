select
    s.s_suppkey,
    s.s_name,
    s.s_address,
    s.s_phone,
    revenue0.total_revenue
from
    supplier s
join (
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
) as revenue0
    on s.s_suppkey = revenue0.supplier_no
join (
    select
        max(revenue_by_supplier.total_revenue) as max_total_revenue
    from (
        select
            sum(l.l_extendedprice * (1 - l.l_discount)) as total_revenue
        from
            lineitem l
        where
            l.l_shipdate >= date '1995-06-01'
            and l.l_shipdate < date '1995-06-01' + interval '3 month'
        group by
            l.l_suppkey
    ) as revenue_by_supplier
) as max_revenue
    on revenue0.total_revenue = max_revenue.max_total_revenue
order by
    s.s_suppkey;
