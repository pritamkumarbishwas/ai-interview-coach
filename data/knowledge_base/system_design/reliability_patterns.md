---
topic: system design
roles: backend, devops
---

## Rate Limiting

Token bucket allows bursts up to bucket size then sustains at the refill rate; fixed window counters are simple but allow double the limit at window edges; sliding window logs are accurate but memory-heavy; sliding window counters approximate logs cheaply. Distributed limiters need a shared store — Redis with atomic Lua scripts is the common answer — and the interview should surface the trade-off between accuracy and round-trips, plus fail-open versus fail-closed behavior when the limiter itself is down.

## Backpressure and Queues

A system under load must shed or slow work deliberately: bounded queues with explicit rejection (HTTP 429/503), worker pools sized to the bottleneck, and load leveling so a burst is absorbed by the queue rather than the database. Unbounded queues merely move the failure later and with less memory to spare. Detect saturation with queue depth and consumer lag metrics; scale consumers on lag, not CPU. Poison-message handling routes repeated failures to a dead-letter queue so one bad payload cannot stall the stream.

## Observability

The three pillars: metrics for aggregate health (RED — rate, errors, duration — plus saturation), logs for detail on individual requests, and traces to follow one request across services. Practical depth: structured JSON logs with a correlation ID propagated from the edge, histograms rather than averages for latency, alerts on symptoms users feel (error rate, p95) instead of causes (CPU), and dashboards that answer "is it the app, the database, or the network?" in one glance.
