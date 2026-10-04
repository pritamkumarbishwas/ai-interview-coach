---
topic: system design
roles: backend, devops, full-stack
---

## Estimation and Requirements

Every design interview should start with a back-of-envelope estimate: QPS from daily active users, storage from retention and object size, bandwidth from payload size × QPS, and then a latency budget that allocates time across each hop. These numbers decide everything downstream — whether the datastore needs sharding, whether a CDN is mandatory, and whether in-memory state is even feasible. Interviewers watch whether the candidate writes the numbers down and revisits them when the design changes.

## Scaling a Web Service

Horizontal scaling needs statelessness first: sessions in a shared store or signed tokens, uploads in object storage, no in-process caches that differ between replicas. Behind a load balancer, add a CDN for static and cacheable responses, then consider read replicas for the database, queue-based load leveling for spikes, and partitioning (sharding) when a single primary's write throughput saturates. Call out the failure modes: sticky sessions break rolling deploys, replicas lag under heavy writes, and every new tier adds a cache-invalidation and observability problem.

## Data Stores and Consistency

Choosing a store follows the access pattern: document stores for nested, read-heavy aggregates; key-value for simple lookups and caching; time-series for metrics; relational when transactions and ad-hoc joins matter. CAP: a partitioned system must choose between linearizable reads (CP) and continued availability (AP); most systems pick per-operation semantics — strong for balances, eventual for feeds. Mention read-your-writes consistency for user-facing flows, idempotency keys for retried writes, and exactly-once as an end-to-end property built from at-least-once delivery plus idempotent consumers.
