---
id: ADR-002
title: PostgreSQL as primary OLTP datastore
status: accepted
date: 2024-09-04
deciders: architecture-team, data-team
---

# ADR-002: PostgreSQL as primary OLTP datastore

## Context

In 2024 we needed to choose the primary OLTP datastore for the new microservices architecture. Options evaluated:

1. PostgreSQL 15
2. MySQL 8
3. MongoDB 7
4. CockroachDB

## Decision

PostgreSQL 15, sharded by `merchant_id` (logical sharding via application routing).

## Rationale

- ACID compliance non-negotiable for orders/payments
- Strong JSONB support — product attributes vary by category (electronics vs apparel)
- Mature ecosystem — managed via Cloud SQL, point-in-time recovery, read replicas
- Team familiarity — existing SREs have 5+ years PostgreSQL ops experience
- Logical sharding chosen over CockroachDB's native sharding for cost control (CockroachDB Cloud 3x more expensive at our scale)

## Consequences

### Positive

- Single datastore skillset across teams
- Cloud SQL HA + read replicas meets our 99.95% availability SLO
- pgvector extension (added 2025-Q1) supports semantic search use cases

### Negative

- Cross-shard joins require application-level fan-out (added ~200 LOC of helper code)
- Sharding logic lives in application code — re-sharding would require downtime

## Alternatives considered

- **MySQL 8**: weaker JSON support, less expressive query planner
- **MongoDB**: document model fits catalog but ACID guarantees weaker pre-4.0; transaction performance lags PostgreSQL for our access patterns
- **CockroachDB**: stronger sharding story but 3x cost and team unfamiliarity

## References

- "Designing Data-Intensive Applications" (Martin Kleppmann), Chapter 7 on transactions
- Cloud SQL for PostgreSQL documentation
