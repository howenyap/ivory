with filtered_lineitems as (
    select
        l.l_extendedprice,
        l.l_quantity,
        avg(l.l_quantity) over (partition by l.l_partkey) as avg_part_quantity
    from
        part p
    join lineitem l
        on l.l_partkey = p.p_partkey
    where
        p.p_brand = 'Brand#32'
        and p.p_container = 'MED BOX'
)
select
    sum(l_extendedprice) / 7.0 as avg_yearly
from
    filtered_lineitems
where
    l_quantity < 0.2 * avg_part_quantity;
