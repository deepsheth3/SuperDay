"""
JWT Bearer auth (JWKS — Auth0 / Cognito / Keycloak compatible).

When `HARPER_JWT_JWKS_URL` is unset, authentication is **disabled** (local dev / tests).
When set, `/api/*` routes that declare `Depends(require_auth_principal)` require a valid Bearer token.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.settings import settings

logger = logging.getLogger(__name__)

_http_bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    """Caller identity from JWT (OIDC-style)."""

    subject: str
    tenant_id: str | None
    claims: dict[str, Any]


_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if not settings.jwt_jwks_url:
        return None
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.jwt_jwks_url)
    return _jwks_client


def decode_bearer_token(token: str) -> Principal:
    """Validate JWT and build Principal; raises HTTPException 401 on failure."""
    client = _get_jwks_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT validation not configured",
        )
    try:
        sk = client.get_signing_key_from_jwt(token)
        algo_list = [a.strip() for a in settings.jwt_algorithms.split(",") if a.strip()] or ["RS256"]
        decode_kw: dict[str, object] = {
            "algorithms": algo_list,
            "options": {
                "verify_signature": True,
                "verify_aud": bool(settings.jwt_audience),
                "verify_iss": bool(settings.jwt_issuer),
            },
        }
        if settings.jwt_audience:
            decode_kw["audience"] = settings.jwt_audience
        if settings.jwt_issuer:
            decode_kw["issuer"] = settings.jwt_issuer
        payload = jwt.decode(token, sk.key, **decode_kw)  # type: ignore[arg-type]
    except jwt.exceptions.PyJWTError as e:
        logger.info("jwt validation failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from e

    sub = str(payload.get("sub") or "")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub")

    tenant: str | None = None
    claim_key = settings.jwt_tenant_claim.strip()
    if claim_key:
        raw = payload.get(claim_key)
        if raw is not None:
            tenant = str(raw).strip() or None

    return Principal(subject=sub, tenant_id=tenant, claims=payload)


async def get_principal_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_http_bearer)],
) -> Principal | None:
    """
    If JWKS URL unset: return None (anonymous).
    If JWKS set and no credentials: return None (caller may use `require_auth_principal`).
    If Bearer present: validate and return Principal.
    """
    if not settings.jwt_jwks_url:
        return None
    if not credentials:
        return None
    return decode_bearer_token(credentials.credentials)


async def require_auth_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_http_bearer)],
) -> Principal | None:
    """Use as router dependency when JWT auth is enabled; no-op anonymous when JWKS unset."""
    if not settings.jwt_jwks_url:
        return None
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_bearer_token(credentials.credentials)


def enforce_tenant_match(
    principal: Principal | None,
    *,
    body_tenant: str | None,
    header_tenant: str | None,
) -> str | None:
    """
    When JWT carries tenant_id, it wins; body/header must match if also sent.
    Returns effective tenant_id string or None.
    """
    if principal and principal.tenant_id:
        tid = principal.tenant_id
        if body_tenant and body_tenant.strip() and body_tenant.strip() != tid:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant_id mismatch with token")
        if header_tenant and header_tenant.strip() and header_tenant.strip() != tid:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="X-Tenant-ID mismatch with token")
        return tid
    return None


def verify_webhook_signature(body: bytes, signature_header: str | None) -> None:
    """HMAC-SHA256 hex digest in header `sha256=<hex>` or raw hex."""
    secret = (settings.webhook_hmac_secret or "").strip()
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhooks not configured")
    if not signature_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")
    sig = signature_header.strip()
    if sig.startswith("sha256="):
        sig = sig[7:]
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig.lower()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
