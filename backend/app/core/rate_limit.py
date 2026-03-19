"""Optional in-process sliding-window rate limiting (per client IP)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.settings import settings

_window_sec = 60.0
_buckets: dict[str, list[float]] = defaultdict(list)
_lock = asyncio.Lock()


async def enforce_rate_limit(request: Request, *, scope: str) -> None:
    """429 when more than `rate_limit_rpm` hits in the last 60s for this IP + scope."""
    rpm = settings.rate_limit_rpm
    if rpm <= 0:
        return
    host = request.client.host if request.client else "unknown"
    key = f"{scope}:{host}"
    now = time.monotonic()
    cutoff = now - _window_sec
    async with _lock:
        times = _buckets[key]
        times[:] = [t for t in times if t > cutoff]
        if len(times) >= rpm:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        times.append(now)


def rate_limit_dependency(scope: str):
    async def _dep(request: Request) -> None:
        await enforce_rate_limit(request, scope=scope)

    return _dep
