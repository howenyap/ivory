CREATE INDEX idx_nation_regionkey ON nation (n_regionkey);
CREATE INDEX idx_supplier_nationkey ON supplier (s_nationkey);
CREATE INDEX idx_customer_nationkey ON customer (c_nationkey);
CREATE INDEX idx_partsupp_suppkey ON partsupp (ps_suppkey);
CREATE INDEX idx_orders_custkey ON orders (o_custkey);
CREATE INDEX idx_lineitem_part_suppkey ON lineitem (l_partkey, l_suppkey);
CREATE INDEX idx_lineitem_shipdate ON lineitem (l_shipdate);

ANALYZE;
