---
id: prd-001
title: "Dark Mode for ShopFlow Web"
status: approved
updated_at: 2026-06-15
author: pm@shopflow.example
---

# PRD-001: Dark Mode for ShopFlow Web

## Background

ShopFlow's web customers in APAC markets have repeatedly requested dark mode (NPS comments, support tickets #48211, #49200, #50389). Internal research shows 67% of evening shoppers (after 19:00 local) report eye strain on the current light theme. Competitors (Amazon, Shopee) ship dark mode by default on mobile but not consistently on web.

## User Stories

- **As a** night-time shopper, **I want** to switch ShopFlow to a dark color scheme **so that** I can browse without eye strain.
- **As a** returning customer, **I want** my dark mode preference to persist across sessions **so that** I don't have to re-enable it every visit.
- **As a** power user, **I want** dark mode to follow my OS setting **so that** ShopFlow respects my system-wide preference.

## Acceptance Criteria (Given/When/Then)

### Scenario: Manual toggle
- **GIVEN** a customer is on any ShopFlow web page
- **WHEN** they click the theme toggle in the header
- **THEN** the page switches to dark mode within 100ms (no full reload)
- **AND** a cookie `sf_theme=dark` is set with `max-age=31536000` (1 year)

### Scenario: Persist across sessions
- **GIVEN** a customer previously enabled dark mode and the cookie exists
- **WHEN** they revisit ShopFlow in a new session
- **THEN** the page renders in dark mode on first paint (no flash of light theme)

### Scenario: Follow OS preference
- **GIVEN** the customer's OS is in dark mode and they have not manually toggled ShopFlow
- **WHEN** they load ShopFlow
- **THEN** the page defaults to dark mode via `prefers-color-scheme: dark` media query

### Scenario: Accessibility contrast
- **GIVEN** dark mode is active
- **WHEN** any text element is rendered
- **THEN** the contrast ratio against its background meets WCAG 2.1 AA (≥ 4.5:1 for body text, ≥ 3:1 for large text)

## Non-Functional Requirements

- **Performance**: First contentful paint delta in dark mode vs light mode ≤ 50ms p95
- **Browser support**: Latest 2 versions of Chrome, Safari, Firefox, Edge; Safari iOS 15+
- **Maintainability**: Color tokens defined as CSS custom properties on `:root`, no hard-coded hex values in components
- **Bundle size**: Added CSS ≤ 8 KB gzipped

## Edge Cases / Error Paths

- Customer has corrupt or missing cookie → default to OS preference, then light theme
- Browser blocks cookies (private mode) → fall back to in-memory preference for the session, surface a one-time toast explaining persistence is unavailable
- Customer is on Internet Explorer → dark mode disabled, light theme rendered with a console warning (IE not supported)
- Customer has `prefers-color-scheme: no-preference` → default to light theme

## Out of Scope

- Dark mode for the mobile apps (iOS / Android) — separate PRD
- Per-category theme override (e.g., dark mode only in electronics)
- Custom user-uploaded themes
- Dark mode for the merchant admin portal
- Auto-switch based on time-of-day (we follow OS preference only)
