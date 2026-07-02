---
title: ShopFlow System Architecture
version: 2.3
last_updated: 2026-05-10
owner: architecture@shopflow.example
---

# ShopFlow System Architecture

## Overview

ShopFlow is a multi-tenant e-commerce platform serving 14 APAC markets. The platform handles ~2.4M monthly active customers, 180K merchants, and peak Q4 traffic of 12K requests/second.

## Services

ShopFlow uses a microservices architecture with the following services:

| Service | Responsibility | Tech Stack |
|---|---|---|
| `web-bff` | Customer-facing web frontend BFF | Node.js, Apollo GraphQL |
| `mobile-bff` | Mobile app BFF | Node.js, GraphQL |
| `catalog-svc` | Product catalog, search | Python (FastAPI), PostgreSQL + Elasticsearch |
| `cart-svc` | Shopping cart, session | Go, Redis |
| `order-svc` | Order lifecycle, fulfillment | Java (Spring Boot), PostgreSQL |
| `payment-svc` | Payment gateway integrations | Java (Spring Boot), PostgreSQL |
| `inventory-svc` | Inventory tracking, reservations | Go, PostgreSQL |
| `user-svc` | Customer accounts, auth | Python (FastAPI), PostgreSQL |
| `notification-svc` | Email, push, SMS dispatch | Node.js, RabbitMQ |

## Data Models

### Core entities

- **Customer**: id (UUID), email, created_at, market (ISO country code)
- **Merchant**: id (UUID), name, plan (free/pro/enterprise)
- **Product**: id (SKU), merchant_id, title, price_cents, currency, status
- **Order**: id (UUID), customer_id, total_cents, status, created_at
- **Inventory**: sku, warehouse_id, quantity_available, quantity_reserved

### Storage

- **PostgreSQL 15** (primary OLTP) — single writer per logical shard, sharded by `merchant_id`
- **Redis** — cart, session, rate-limit counters
- **Elasticsearch** — product search, catalog denormalization
- **S3** — product images, exports

## API Surface

### External (customer/merchant-facing)

- `api.shopflow.example/graphql` — GraphQL BFF (web + mobile)
- `api.shopflow.example/webhooks/{provider}` — inbound webhooks (Shopify, Stripe, etc.)

### Internal (service-to-service)

- gRPC over mTLS for synchronous calls
- RabbitMQ for asynchronous events (`order.created`, `inventory.updated`, `payment.captured`)

### Auth

- Customer auth: OAuth 2.0 via `user-svc` (Authorization Code + PKCE)
- Service-to-service: mTLS with certs from internal CA
- Merchant API: API keys with HMAC-signed requests

## Cross-cutting concerns

- **Observability**: OpenTelemetry traces → Tempo, metrics → Prometheus, logs → Loki
- **Deployment**: Kubernetes on GKE, blue-green for stateful services
- **Multi-region**: Active-active in 3 regions (Tokyo, Singapore, Sydney); CRDTs for cart

## Architecture Decision Records

See `adr/` directory for significant architectural decisions:

- [ADR-001: Microservices split strategy](adr/adr-001-microservices-split.md)
- [ADR-002: PostgreSQL as primary OLTP datastore](adr/adr-002-postgresql-choice.md)
- [ADR-003: OAuth 2.0 + PKCE for customer authentication](adr/adr-003-oauth2-auth.md)
