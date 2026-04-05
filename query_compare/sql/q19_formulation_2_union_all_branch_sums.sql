select
    sum(branch_revenues.revenue) as revenue
from
    (
        select
            sum(l.l_extendedprice * (1 - l.l_discount)) as revenue
        from
            lineitem l
        join part p
            on p.p_partkey = l.l_partkey
        where
            p.p_brand = 'Brand#24'
            and p.p_container in ('SM CASE', 'SM BOX', 'SM PACK', 'SM PKG')
            and l.l_quantity between 2 and 12
            and p.p_size between 1 and 5
            and l.l_shipmode in ('AIR', 'AIR REG')
            and l.l_shipinstruct = 'DELIVER IN PERSON'
        union all
        select
            sum(l.l_extendedprice * (1 - l.l_discount)) as revenue
        from
            lineitem l
        join part p
            on p.p_partkey = l.l_partkey
        where
            p.p_brand = 'Brand#15'
            and p.p_container in ('MED BAG', 'MED BOX', 'MED PKG', 'MED PACK')
            and l.l_quantity between 16 and 26
            and p.p_size between 1 and 10
            and l.l_shipmode in ('AIR', 'AIR REG')
            and l.l_shipinstruct = 'DELIVER IN PERSON'
        union all
        select
            sum(l.l_extendedprice * (1 - l.l_discount)) as revenue
        from
            lineitem l
        join part p
            on p.p_partkey = l.l_partkey
        where
            p.p_brand = 'Brand#52'
            and p.p_container in ('LG CASE', 'LG BOX', 'LG PACK', 'LG PKG')
            and l.l_quantity between 23 and 33
            and p.p_size between 1 and 15
            and l.l_shipmode in ('AIR', 'AIR REG')
            and l.l_shipinstruct = 'DELIVER IN PERSON'
    ) as branch_revenues;
