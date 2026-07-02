---
id: prd-002
title: "Customer Wishlist"
status: draft
updated_at: 2026-06-18
author: pm@shopflow.example
---

# PRD-002: Customer Wishlist

## Background

Customers frequently add items to cart with no intent to purchase immediately. Without a wishlist, they either leave items in the cart (skewing our abandonment metrics) or use browser bookmarks (losing inventory/price updates). A wishlist separates "save for later" from "buy now" intent.

## User Stories

- As a logged-in customer, I want to save items to a wishlist so I can revisit them later.
- As a customer, I want to receive a notification when a wishlisted item goes on sale.
- As a customer, I want to create multiple wishlists (e.g., "Birthday", "Home") to organize saved items.

## Non-Functional Requirements

- Wishlist API responds within 200ms p95
- Supports up to 10,000 items per customer
- Real-time sync across devices for logged-in users
- Mobile-responsive UI

## Edge Cases / Error Paths

- Item in wishlist goes out of stock → mark as "unavailable", keep in wishlist
- Item price changes → display current price with strikethrough of saved price
- Customer reaches wishlist item limit → show friendly message, suggest cleanup

## Out of Scope

- Public/shared wishlists (gift registries)
- Wishlist import from Amazon or other competitors
- AI-powered wishlist recommendations
- Wishlist sharing via deep links
