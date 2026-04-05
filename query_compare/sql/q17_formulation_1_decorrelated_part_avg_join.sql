with part_avg as (
    select
        l.l_partkey,
        0.2 * avg(l.l_quantity) as quantity_threshold
    from
        lineitem l
    group by
        l.l_partkey
)
select
    sum(l.l_extendedprice) / 7.0 as avg_yearly
from
    part p
join lineitem l
    on l.l_partkey = p.p_partkey
join part_avg pa
    on pa.l_partkey = l.l_partkey
where
    p.p_brand = 'Brand#32'
    and p.p_container = 'MED BOX'
    and l.l_quantity < pa.quantity_threshold;
