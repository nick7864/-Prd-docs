---
id: ADR-001
title: Microservices split by business capability
status: accepted
date: 2024-08-12
deciders: architecture-team
---

# ADR-001: Microservices split by business capability

## Context

In 2024, ShopFlow's monolithic Rails app could not scale beyond 3K req/s and deploys took 45 minutes. The team evaluated three options:

1. Modular monolith with stricter boundaries
2. Microservices split by business capability (Bounded Context per DDD)
3. Microservices split by technical layer (UI/service/data)

## Decision

We chose option 2: split by business capability. Each service owns one Bounded Context:

- Catalog, Cart, Order, Payment, Inventory, User, Notification

## Rationale

- Aligns team boundaries (Conway's Law) — each service has a 2-pizza team
- Independent deployment cadence — `payment-svc` deploys daily, `order-svc` weekly
- Failure isolation — `inventory-svc` outage does not block checkout (cart reserves in Redis)
- Scalability profile differs per service (cart needs low-latency Redis; catalog needs ES for search)

## Consequences

### Positive

- Deploy frequency up 6x, deploy time down from 45min to 4min
- Service ownership clear, on-call pages routed correctly

### Negative

- Distributed transactions now require saga pattern (added complexity for order placement)
- Network latency between services added ~30ms p95 to checkout
- Operational tooling cost (tracing, service mesh) increased

## Alternatives considered

- **Modular monolith**: rejected because team scale (28 engineers) made deploy conflicts frequent
- **Technical-layer split**: rejected because UI/data teams would block every cross-cutting feature

## References

- "Domain-Driven Design" (Eric Evans), Bounded Context pattern
- "Building Microservices" (Sam Newman), Chapter 2 on service boundaries
