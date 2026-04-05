select
    part_values.ps_partkey,
    part_values.value
from (
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
) as part_values
cross join (
    select
        sum(grouped_values.value) * 0.0001000000 as threshold_value
    from (
        select
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
    ) as grouped_values
) as threshold
where
    part_values.value > threshold.threshold_value
order by
    part_values.value desc;
