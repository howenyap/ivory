with shipped_lines as (
    select
        l.l_partkey,
        l.l_quantity,
        l.l_extendedprice,
        l.l_discount
    from
        lineitem l
    where
        l.l_shipmode in ('AIR', 'AIR REG')
        and l.l_shipinstruct = 'DELIVER IN PERSON'
),
target_parts as (
    select
        p.p_partkey,
        1 as family_id
    from
        part p
    where
        p.p_brand = 'Brand#24'
        and p.p_container in ('SM CASE', 'SM BOX', 'SM PACK', 'SM PKG')
        and p.p_size between 1 and 5
    union all
    select
        p.p_partkey,
        2 as family_id
    from
        part p
    where
        p.p_brand = 'Brand#15'
        and p.p_container in ('MED BAG', 'MED BOX', 'MED PKG', 'MED PACK')
        and p.p_size between 1 and 10
    union all
    select
        p.p_partkey,
        3 as family_id
    from
        part p
    where
        p.p_brand = 'Brand#52'
        and p.p_container in ('LG CASE', 'LG BOX', 'LG PACK', 'LG PKG')
        and p.p_size between 1 and 15
)
select
    sum(sl.l_extendedprice * (1 - sl.l_discount)) as revenue
from
    shipped_lines sl
join target_parts tp
    on tp.p_partkey = sl.l_partkey
where
    (tp.family_id = 1 and sl.l_quantity between 2 and 12)
    or (tp.family_id = 2 and sl.l_quantity between 16 and 26)
    or (tp.family_id = 3 and sl.l_quantity between 23 and 33);
