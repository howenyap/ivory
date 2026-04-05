with part_values as (
    select
        ps.ps_partkey,
        sum(ps.ps_supplycost * ps.ps_availqty) as value
    from
        partsupp ps
    join supplier s
        on s.s_suppkey = ps.ps_suppkey
    join nation n
        on n.n_nationkey = s.s_nationkey
    where
        n.n_name = 'CHINA'
    group by
        ps.ps_partkey
),
threshold as (
    select
        sum(value) * 0.0001000000 as threshold_value
    from
        part_values
)
select
    pv.ps_partkey,
    pv.value
from
    part_values pv
cross join threshold t
where
    pv.value > t.threshold_value
order by
    pv.value desc;
