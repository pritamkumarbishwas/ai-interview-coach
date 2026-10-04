---
topic: databases
roles: backend, data, full-stack
---

## Row-Level Security

Row-Level Security (RLS) restricts which rows a user can read or write based on policies, evaluated inside the database rather than in application code. In PostgreSQL, policies are attached to tables and reference roles and expressions, for example `CREATE POLICY tenant_isolation ON orders USING (tenant_id = current_setting('app.tenant_id')::uuid)`. RLS matters multi-tenant systems: it prevents a bug in one query from leaking another tenant's data, and it keeps the rule enforceable even for direct SQL access.

Trade-offs worth mentioning in an interview: policies add per-row predicate overhead and can defeat naive index usage if written poorly; connection pools must set per-request GUCs like `app.tenant_id` correctly or every request sees the wrong tenant; and testing must cover both allow and deny paths. Alternatives are application-level filtering, database-per-tenant isolation, or views, each with weaker guarantees or higher operational cost.

## Indexing

B-tree indexes are the default and serve equality and range lookups; GIN indexes suit JSONB and full-text search; BRIN suits append-only time series; partial indexes cover queries with a fixed predicate. An index speeds reads but slows writes, costs storage, and only helps when the query's filter and sort align with the index columns in order.

Interview signals of depth: explaining why a composite index is used left-to-right (`WHERE tenant_id = ? AND created_at < ?` wants `(tenant_id, created_at)`), mentioning `EXPLAIN ANALYZE` as the starting point for any slowdown, the update-analyzer problem when a table is written heavily while its statistics go stale, and that `SELECT *` often makes the planner skip an index-only scan.

## Transactions and Isolation

ACID transactions give atomicity, consistency, durability, and isolation. The isolation levels trade correctness for throughput: Read Uncommitted allows dirty reads; Read Committed blocks dirty reads but allows non-repeatable reads; Repeatable Read adds snapshot stability but may still allow phantoms under some implementations; Serializable prevents all anomalies, sometimes by aborting transactions (PostgreSQL uses Serializable Snapshot Isolation, which rarely aborts).

Be ready to discuss deadlock handling (consistent lock ordering, detecting via wait graphs), long-running transactions holding vacuum back in Postgres, and choosing the weakest level that preserves business invariants — serializing everything is correctness bought at the price of throughput.
