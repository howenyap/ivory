with bad_suppliers as (
    select
        s.s_suppkey
    from
        supplier s
    where
        s.s_comment like '%Customer%Complaints%'
)
select
    p.p_brand,
    p.p_type,
    p.p_size,
    count(distinct ps.ps_suppkey) as supplier_cnt
from
    part p
join partsupp ps
    on ps.ps_partkey = p.p_partkey
left join bad_suppliers bs
    on bs.s_suppkey = ps.ps_suppkey
where
    p.p_brand <> 'Brand#33'
    and p.p_type not like 'STANDARD BURNISHED%'
    and p.p_size in (1, 3, 47, 36, 42, 22, 20, 37)
    and bs.s_suppkey is null
group by
    p.p_brand,
    p.p_type,
    p.p_size
order by
    supplier_cnt desc,
    p.p_brand,
    p.p_type,
    p.p_size;
