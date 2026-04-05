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
valued_parts as (
    select
        ps_partkey,
        value,
        sum(value) over () * 0.0001000000 as threshold_value
    from
        part_values
)
select
    ps_partkey,
    value
from
    valued_parts
where
    value > threshold_value
order by
    value desc;
