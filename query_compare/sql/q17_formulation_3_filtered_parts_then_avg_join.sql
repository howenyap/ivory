with target_parts as (
    select
        p_partkey
    from
        part
    where
        p_brand = 'Brand#32'
        and p_container = 'MED BOX'
),
part_avg as (
    select
        l.l_partkey,
        0.2 * avg(l.l_quantity) as quantity_threshold
    from
        target_parts p
    join lineitem l
        on l.l_partkey = p.p_partkey
    group by
        l.l_partkey
)
select
    sum(l.l_extendedprice) / 7.0 as avg_yearly
from
    target_parts p
join lineitem l
    on l.l_partkey = p.p_partkey
join part_avg pa
    on pa.l_partkey = l.l_partkey
where
    l.l_quantity < pa.quantity_threshold;
