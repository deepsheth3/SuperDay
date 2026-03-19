# Security, auth, and communications

This document describes how **Harper Chat Service** handles **authentication**, **tenant boundaries**, **secrets**, **rate limits**, and **API surfaces** (HTTP, SSE, WebSocket, webhooks).

---

## Decisions (default stack)

| Topic | Choice |
|-------|--------|
| **Identity** | **OIDC / JWT** from your IdP (Auth0, Amazon Cognito, Google / Firebase JWT, Keycloak, Clerk-issued JWT, etc.) |
| **Token transport** | **`Authorization: Bearer &lt;access_token&gt;`** from the browser or BFF |
| **Tenant model** | **Tenant id in a JWT claim** (`HARPER_JWT_TENANT_CLAIM`, default `tenant_id`). When present, it **must** match `X-Tenant-ID` and JSON body `tenant_id` if those are also sent. **Multi-tenant users** use separate tokens or a custom claim strategy per IdP. |
| **Cookie vs Bearer** | **Bearer** is implemented; session cookies + BFF are compatible if the BFF forwards `Authorization`. |

---

## Phase A — JWT and tenant enforcement

### When auth is off (local dev)

If **`HARPER_JWT_JWKS_URL`** is **unset**, `/api/*` behaves as before: **no Bearer required**. Use this for tests and local development.

### When auth is on (production)

Set:

| Variable | Purpose |
|----------|---------|
| `HARPER_JWT_JWKS_URL` | JWKS URL for signature verification |
| `HARPER_JWT_AUDIENCE` | Optional `aud` validation |
| `HARPER_JWT_ISSUER` | Optional `iss` validation |
| `HARPER_JWT_ALGORITHMS` | Comma-separated algs (default `RS256`) |
| `HARPER_JWT_TENANT_CLAIM` | Claim name for tenant UUID |

All chat, ingest, rehydration, and pipeline status routes **require a valid Bearer token** when JWKS URL is set.

**Tenant rule:** If the token includes the tenant claim, requests that also send `tenant_id` in the body or `X-Tenant-ID` must **match**; otherwise the API returns **403**.

### Frontend

- Set **`NEXT_PUBLIC_ACCESS_TOKEN`** only for short-lived local smoke tests (avoid in production).
- Prefer **`localStorage.setItem("harper_access_token", token)`** after your IdP login, or plumb tokens from your auth library. See `frontend/src/lib/api.ts` (`buildAuthHeaders`).

---

## Phase B — Secrets and logging

### Secret Manager (production)

- Store **LLM keys**, **DB passwords**, **`HARPER_WEBHOOK_HMAC_SECRET`**, and **IdP client secrets** in your platform’s secret manager (GCP Secret Manager, AWS Secrets Manager, etc.).
- Inject at runtime as env vars; keep **repo `.env` local-only**.

### Log redaction

- Enable **`HARPER_REDACT_SECRETS_IN_LOGS=true`** (default) to **best-effort scrub** `Authorization: Bearer …` and `X-Harper-Signature` patterns from log messages.

---

## Phase C — Rate limiting (optional)

- **`HARPER_RATE_LIMIT_RPM`**: in-process **sliding window** (60s) per **client IP** for:
  - `POST /api/chat`, `POST /api/chat/stream` (scope `chat`)
  - Ingest routes (scope `ingest`)
  - `POST /api/webhooks/ingest` (scope `webhook`)
- **`0`** disables limits (default).
- For production at scale, prefer **edge / AWS WAF / Cloud Armor / API Gateway** or **Redis-backed** limits (not bundled here).

---

## Phase D — Communication patterns

| Need | Mechanism | Route / notes |
|------|-----------|----------------|
| Chat JSON | HTTP POST | `/api/chat` |
| Token stream | **SSE** | `/api/chat/stream` — harden with **JWT + timeouts** when JWKS is set |
| Duplex / experiments | **WebSocket** (stub) | **`/api/ws/chat`** — `?access_token=` when JWKS is set |
| Vendor ingest | **Signed webhook** | **`POST /api/webhooks/ingest`** with **`X-Harper-Signature: sha256=&lt;hex&gt;`** (HMAC-SHA256 of **raw body** with `HARPER_WEBHOOK_HMAC_SECRET`) |

Webhook requests **do not** use JWT; they rely on **HMAC**. Rotate the shared secret on compromise.

---

## Production checklist

- [ ] Set `HARPER_JWT_JWKS_URL`, `HARPER_JWT_AUDIENCE`, `HARPER_JWT_ISSUER` as appropriate for your IdP.
- [ ] Ensure tenant claim is present on user tokens if you rely on tenant isolation.
- [ ] Move all secrets to Secret Manager; never commit `.env` with real values.
- [ ] Confirm CORS `FRONTEND_URL` allows only trusted origins.
- [ ] Enable platform or Redis rate limiting if `HARPER_RATE_LIMIT_RPM` is insufficient.
- [ ] For webhooks: strong random `HARPER_WEBHOOK_HMAC_SECRET`, idempotent ingest (existing pipeline dedupes by source identifiers).

---

## Reference

- Env template: [`backend/.env.example`](../backend/.env.example)
- Architecture overview: [`ARCHITECTURE.md`](ARCHITECTURE.md)
