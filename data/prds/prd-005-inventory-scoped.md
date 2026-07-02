---
id: prd-005
title: "Real-time Inventory Sync with Shopify"
status: approved
updated_at: 2026-06-25
author: pm@shopflow.example
---

# PRD-005: Real-time Inventory Sync with Shopify

## Background

ShopFlow merchants who also sell on Shopify manually sync inventory twice daily via CSV export/import. This causes overselling: in Q1 2026, 312 orders were placed on ShopFlow for items already sold out on Shopify (and vice versa). Average manual sync burden is 2.5 hours/week per merchant. This PRD adds real-time inventory sync between ShopFlow and Shopify via Shopify's webhook API.

## User Stories

- As a merchant, I want inventory updates on Shopify to reflect on ShopFlow within 60 seconds so I don't oversell.
- As a merchant, I want a sync status dashboard so I can verify the integration is healthy.

## Acceptance Criteria (Given/When/Then)

### Scenario: Shopify inventory update
- **GIVEN** a merchant updates stock for SKU-12345 on Shopify to 10 units
- **WHEN** Shopify fires the `inventory_levels/update` webhook
- **THEN** ShopFlow receives the webhook within 60 seconds
- **AND** updates the ShopFlow product database to 10 units for SKU-12345
- **AND** emits an audit log entry `inventory_synced`

### Scenario: Webhook delivery failure
- **GIVEN** Shopify sends a webhook and ShopFlow is unreachable
- **WHEN** Shopify retries per its webhook retry policy (5 retries over 24h)
- **THEN** ShopFlow processes the webhook when it recovers
- **AND** reconciles using Shopify REST API as fallback if last webhook is older than 1h

### Scenario: Conflict detection
- **GIVEN** both ShopFlow and Shopify sell SKU-12345 simultaneously
- **WHEN** inventory reaches 0 on either side
- **THEN** both systems mark the SKU as out of stock
- **AND** the merchant receives an email notification of potential oversell

## Non-Functional Requirements

- Webhook ingestion endpoint handles 1000 concurrent webhooks (p95)
- Idempotency: duplicate webhooks (same `X-Shopify-Webhook-Id`) do not double-apply updates
- Reconciliation job runs every 5 minutes to catch missed webhooks
- Audit log retained 90 days

## Edge Cases / Error Paths

- Merchant disconnects Shopify OAuth → sync pauses, dashboard shows "disconnected" state, no data loss
- SKU exists on Shopify but not on ShopFlow → log as `unmapped_sku`, surface in dashboard, no auto-create
- Webhook signature verification fails → reject with 401, log security event

## Out of Scope

- Multi-channel sync beyond Shopify (Etsy, Amazon — future PRDs)
- Variant-level inventory (this PRD covers SKU-level only)
- Historical inventory reporting (covered by analytics PRD)
