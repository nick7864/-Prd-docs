---
id: ADR-003
title: OAuth 2.0 Authorization Code + PKCE for customer authentication
status: accepted
date: 2024-10-22
deciders: security-team, architecture-team
---

# ADR-003: OAuth 2.0 Authorization Code + PKCE for customer authentication

## Context

ShopFlow's original session-based auth (cookie + server-side session) was vulnerable to CSRF and could not support third-party merchant apps. We needed an auth standard that:

1. Supports web + mobile + third-party API clients
2. Protects against CSRF and session fixation
3. Allows merchants to build apps on ShopFlow data

## Decision

OAuth 2.0 Authorization Code flow with PKCE (RFC 7636) for all customer auth, issued by `user-svc`.

## Rationale

- **PKCE** protects mobile/native clients where client secret cannot be stored securely
- **Authorization Code** (not Implicit) avoids token leakage via URL fragments
- Industry standard — well-tested libraries (Authlib, oidc-client-ts)
- Supports future: SSO with Google/Apple, merchant OAuth scopes

## Consequences

### Positive

- Single auth pattern across web/mobile/third-party
- Token rotation + refresh tokens reduce session-hijacking blast radius
- OIDC scope model maps cleanly to merchant API permissions

### Negative

- Added round-trip per login (~120ms) — mitigated by silent refresh on SPA
- Token revocation list must be checked per request — added Redis-backed cache

## Alternatives considered

- **Pure session/cookie**: simple but no third-party API support, harder to scale across subdomains
- **JWT-only (stateless)**: revocation hard without central denylist
- **SAML**: enterprise-oriented, too heavy for consumer e-commerce

## References

- RFC 6749 (OAuth 2.0 framework)
- RFC 7636 (PKCE extension)
- OWASP Authentication Cheat Sheet
