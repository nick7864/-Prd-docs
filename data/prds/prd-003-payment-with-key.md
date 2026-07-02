---
id: prd-003
title: "Stripe Payment Integration"
status: draft
updated_at: 2026-06-20
author: pm@shopflow.example
---

# PRD-003: Stripe Payment Integration

## Background

ShopFlow currently uses a legacy payment gateway with 2.4% + $0.30 per transaction. Stripe offers 2.4% + $0.30 for domestic cards but better international rates (3.5% vs our current 4.2%) and superior developer experience. This PRD covers migration to Stripe for all new transactions.

## User Stories

- As a customer, I want to pay with credit card via Stripe so that checkout is reliable.
- As a customer, I want to use Apple Pay and Google Pay for one-tap checkout.

## Acceptance Criteria (Given/When/Then)

### Scenario: Successful card payment
- **GIVEN** a customer is on checkout with a valid cart
- **WHEN** they enter card details and click "Pay"
- **THEN** Stripe processes the payment
- **AND** the order is marked paid within 3 seconds p95

### Scenario: 3D Secure challenge
- **GIVEN** the customer's card issuer requires SCA
- **WHEN** Stripe returns a `requires_action` status
- **THEN** the customer is redirected to the issuer's 3DS challenge page
- **AND** on success, returns to ShopFlow confirmation within 10 seconds

## Implementation Notes

For testing in development, the team can use the following sandbox credentials:

- Stripe test publishable key: `pk_test_xxx`
- Stripe test secret key: `sk_test_xxx`
- Google API key for address autocomplete: `AIzaSyDabc123def456ghi789jkl012mno345pqr`

<!-- TEST FIXTURE: The API key above is FAKE — intentionally included to test the policy gate's regex detection (AIza[0-9A-Za-z_\-]{35}). NOT a real credential. -->
- Webhook signing secret: `whsec_xxx`

> ⚠️ PM note: I've put the real Google API key here so engineering can test address autocomplete locally. Please don't commit this to git.

## Non-Functional Requirements

- PCI DSS Level 1 compliant via Stripe.js + PaymentIntents (no card data touches our servers)
- 3D Secure support for EU customers (SCA compliance)
- Refund webhook processes within 60 seconds

## Edge Cases / Error Paths

- Card declined → display Stripe error code with customer-friendly message
- Network timeout during payment → idempotency key prevents double charge
- Webhook delivery failure → retry with exponential backoff (max 24h)

## Out of Scope

- PayPal integration (separate PRD)
- Crypto payments
- Buy Now Pay Later (Affirm, Klarna)
