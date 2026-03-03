"""Redis cache with TTL for follow-up pipeline: waiting-on-client set, per-account state, CDC cursor."""
from __future__ import annotations

import json
from typing import Any

from harper_agent.config import REDIS_URL

# TTL seconds
TTL_WAITING_ACCOUNTS = 3600   # 1 hour
TTL_FOLLOWUP_STATE = 300      # 5 min
TTL_CDC_CURSOR = 86400        # 24 hours

KEY_WAITING_ACCOUNTS = "harper:accounts:waiting_on_client"
KEY_FOLLOWUP_PREFIX = "harper:followup:"
KEY_CDC_OFFSET = "harper:cdc:last_offset"


def _client():
    """Return Redis client or None if REDIS_URL not set."""
    if not REDIS_URL:
        return None
    try:
        import redis
        return redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        return None


def get_waiting_on_client_account_ids() -> list[str]:
    """Return list of account IDs that are waiting on client (from cache). Empty if cache miss or no Redis."""
    r = _client()
    if r is None:
        return []
    try:
        data = r.get(KEY_WAITING_ACCOUNTS)
        if data is None:
            return []
        out = json.loads(data)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_waiting_on_client_account_ids(account_ids: list[str], ttl: int = TTL_WAITING_ACCOUNTS) -> None:
    """Cache the set of account IDs waiting on client."""
    r = _client()
    if r is None:
        return
    try:
        r.setex(KEY_WAITING_ACCOUNTS, ttl, json.dumps(account_ids))
    except Exception:
        pass


def get_cached_followup_state(account_id: str) -> dict | None:
    """Return cached follow-up state for account, or None on miss / no Redis."""
    r = _client()
    if r is None:
        return None
    key = KEY_FOLLOWUP_PREFIX + account_id
    try:
        data = r.get(key)
        if data is None:
            return None
        return json.loads(data)
    except Exception:
        return None


def set_cached_followup_state(account_id: str, state: dict, ttl: int = TTL_FOLLOWUP_STATE) -> None:
    """Cache follow-up state for account."""
    r = _client()
    if r is None:
        return
    key = KEY_FOLLOWUP_PREFIX + account_id
    try:
        r.setex(key, ttl, json.dumps(state))
    except Exception:
        pass


def invalidate_followup_cache(account_id: str) -> None:
    """Remove cached follow-up state for account (e.g. after state update)."""
    r = _client()
    if r is None:
        return
    try:
        r.delete(KEY_FOLLOWUP_PREFIX + account_id)
    except Exception:
        pass


def get_cdc_last_offset() -> int | None:
    """Return last processed byte offset for events.jsonl, or None."""
    r = _client()
    if r is None:
        return None
    try:
        s = r.get(KEY_CDC_OFFSET)
        return int(s) if s is not None else None
    except Exception:
        return None


def set_cdc_last_offset(offset: int, ttl: int = TTL_CDC_CURSOR) -> None:
    """Store last processed byte offset for CDC consumer."""
    r = _client()
    if r is None:
        return
    try:
        r.setex(KEY_CDC_OFFSET, ttl, str(offset))
    except Exception:
        pass
