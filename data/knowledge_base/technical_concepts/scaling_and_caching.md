---
topic: caching
roles: backend, full-stack, devops
---

## Cache Strategies

Cache-aside (lazy loading): the application reads the cache first, and on a miss loads from the database and populates the cache. Simple, only stores data actually used, but the first request after invalidation is slow and stale data can linger until TTL expiry. Write-through: writes go to the cache and database together — low read latency, higher write latency, cache and DB stay consistent. Write-behind: writes hit the cache and flush to the database asynchronously — fast writes, risk of data loss on failure. Read-through: a caching layer in front of the database loads data itself, centralizing the logic.

Invalidation is the hard part: TTLs bound staleness cheaply; explicit invalidation on writes is immediate but must cover every write path; versioned keys (`item:{id}:v{hash}`) let old entries expire naturally without coordinated deletes.

## Cache Invalidation Patterns

Typical interview answer: use a short TTL for volatile data, delete keys on mutation for strong consistency, and namespace keys per tenant to prevent cross-tenant leakage. Discuss stampede protection — a hot expired key can be hit by hundreds of requests at once; solve it with request coalescing (only one caller recomputes), logical early expiry so a fraction of requests refresh proactively, or probabilistic early expiration. Also mention negative caching for known-missing entries, and that caches must have a bounded size (LRU) or memory pressure grows unbounded.

## Queues and Async Work

Message queues decouple producers from slow consumers: web requests enqueue a job (send email, generate report) and return immediately; workers process at their own pace and absorb traffic spikes. Delivery semantics matter: at-most-once loses messages, at-least-once duplicates them, so consumers must be idempotent (dedupe keys, upserts, natural primary keys). Dead-letter queues capture poison messages for inspection instead of blocking the stream. Redis lists give simple at-least-once handoff; RabbitMQ adds acknowledgements and routing; Kafka persists an ordered, replayable log with consumer offsets and partition-key ordering guarantees.
