with filtered_parts as (
    select
        p.p_partkey,
        p.p_brand,
        p.p_type,
        p.p_size
    from
        part p
    where
        p.p_brand <> 'Brand#33'
        and p.p_type not like 'STANDARD BURNISHED%'
        and p.p_size in (1, 3, 47, 36, 42, 22, 20, 37)
),
bad_suppliers as (
    select
        s.s_suppkey
    from
        supplier s
    where
        s.s_comment like '%Customer%Complaints%'
)
select
    fp.p_brand,
    fp.p_type,
    fp.p_size,
    count(distinct ps.ps_suppkey) as supplier_cnt
from
    filtered_parts fp
join partsupp ps
    on ps.ps_partkey = fp.p_partkey
left join bad_suppliers bs
    on bs.s_suppkey = ps.ps_suppkey
where
    bs.s_suppkey is null
group by
    fp.p_brand,
    fp.p_type,
    fp.p_size
order by
    supplier_cnt desc,
    fp.p_brand,
    fp.p_type,
    fp.p_size;
