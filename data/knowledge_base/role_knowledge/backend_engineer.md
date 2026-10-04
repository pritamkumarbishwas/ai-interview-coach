---
topic: role expectations
roles: backend
---

## What Interviewers Look for in Backend Engineers

Core expectations by level: mid-level engineers design a service boundary, choose storage deliberately, and write tests that catch regressions; seniors own an end-to-end system, reason about failure modes and operability, and mentor through design review; staff-level candidates frame problems across teams, kill ambiguity before it becomes rework, and connect technical choices to business constraints like cost and delivery dates.

## Common Signal Areas

API design: consistent resources, clear error shapes, pagination, versioning, and idempotency for retried writes. Data modeling: choose access patterns first, normalize until it hurts then denormalize until it works, and treat migrations as first-class (expand/contract pattern so old and new code can coexist during a rollout). Reliability: timeouts, retries with jittered backoff and budgets, circuit breakers on downstream calls, and graceful degradation that serves the last known good answer. Security: authenticate at the edge, authorize per resource, validate and parameterize all input, never log secrets, and keep private data out of URLs.

## Questions Candidates Should Ask

Strong candidates ask about the team's on-call, how changes ship (CI/CD, review, rollback), what the current bottleneck is, how success is measured, and where the architecture is under strain. These questions signal ownership and help the candidate evaluate the role in return.
