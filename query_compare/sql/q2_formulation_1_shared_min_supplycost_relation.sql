with africa_suppliers as (
    select
        s.s_suppkey,
        s.s_acctbal,
        s.s_name,
        n.n_name,
        s.s_address,
        s.s_phone,
        s.s_comment
    from
        supplier s
    join nation n
        on n.n_nationkey = s.s_nationkey
    join region r
        on r.r_regionkey = n.n_regionkey
    where
        r.r_name = 'AFRICA'
),
min_supplycost as (
    select
        ps.ps_partkey,
        min(ps.ps_supplycost) as min_supplycost
    from
        partsupp ps
    join africa_suppliers af
        on af.s_suppkey = ps.ps_suppkey
    group by
        ps.ps_partkey
)
select
    af.s_acctbal,
    af.s_name,
    af.n_name,
    p.p_partkey,
    p.p_mfgr,
    af.s_address,
    af.s_phone,
    af.s_comment
from
    part p
join partsupp ps
    on ps.ps_partkey = p.p_partkey
join africa_suppliers af
    on af.s_suppkey = ps.ps_suppkey
join min_supplycost m
    on m.ps_partkey = p.p_partkey
    and m.min_supplycost = ps.ps_supplycost
where
    p.p_size = 12
    and p.p_type like '%COPPER'
order by
    af.s_acctbal desc,
    af.n_name,
    af.s_name,
    p.p_partkey
limit 100;
