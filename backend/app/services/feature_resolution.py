"""
Tenant feature flag resolution — precedence, cache, active window (plan ## 50.1).

Precedence:
1) tenant_features row with now in [effective_from, effective_to) — pick max(effective_from)
2) tenant defaults / env
3) global service default
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ResolvedFeature:
    enabled: bool
    config: dict[str, Any]


class TenantFeatureResolver:
    def __init__(self, default_config: dict[str, Any] | None = None, cache_ttl_s: float = 45.0):
        self._default = default_config or {}
        self._cache_ttl = cache_ttl_s
        self._cache: dict[tuple[UUID, str], tuple[float, ResolvedFeature]] = {}

    def invalidate_tenant(self, tenant_id: UUID) -> None:
        keys = [k for k in self._cache if k[0] == tenant_id]
        for k in keys:
            del self._cache[k]

    async def resolve(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        feature_name: str,
        *,
        global_default: bool = False,
    ) -> ResolvedFeature:
        now = time.monotonic()
        ck = (tenant_id, feature_name)
        if ck in self._cache:
            exp, val = self._cache[ck]
            if now < exp:
                return val

        # Lazy import to avoid circular deps if TenantFeature ORM added later
        from sqlalchemy import text

        q = text(
            """
            SELECT enabled, config_json, effective_from
            FROM tenant_features
            WHERE tenant_id = :tid
              AND feature_name = :fname
              AND effective_from <= now()
              AND (effective_to IS NULL OR effective_to > now())
            ORDER BY effective_from DESC
            LIMIT 1
            """
        )
        try:
            r = await session.execute(q, {"tid": tenant_id, "fname": feature_name})
            row = r.mappings().first()
            if row:
                val = ResolvedFeature(enabled=bool(row["enabled"]), config=dict(row["config_json"] or {}))
            else:
                val = ResolvedFeature(enabled=global_default, config=dict(self._default.get(feature_name, {})))
        except Exception:
            val = ResolvedFeature(enabled=global_default, config=dict(self._default.get(feature_name, {})))

        self._cache[ck] = (now + self._cache_ttl, val)
        return val
