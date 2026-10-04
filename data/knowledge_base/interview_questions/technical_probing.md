---
topic: technical probing
roles: "*"
---

## Strong Technical Follow-Ups

When a candidate claims experience with a technology, the question that separates résumé listing from real depth is "walk me through what happens under the hood when..." — for a database query, index selection and the plan; for an HTTP request, DNS, TLS, routing, and the worker that serves it; for a deploy, build, image layers, health checks, and rollout. Follow-up prompts that force trade-off thinking: "what would you change at 10x traffic?", "what broke when you tried this at scale?", "how would you test that this is correct?", "what did you measure before optimizing?"

## What a Good Answer Contains

A strong technical answer names the constraint first (latency budget, data size, consistency need), states a chosen approach with one credible alternative and why it lost, and includes a concrete failure mode the approach must handle. Red flags: absolute claims ("always use Redis"), no mention of measurement or monitoring, solutions that ignore the write path, and designs with a single point of failure or an unbounded queue. Interviewers should probe with "and how would you know it worked?" to see whether the candidate reaches for logs, metrics, and load tests naturally.
