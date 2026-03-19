"""
**Pipeline state** (ingest/normalize/embed): JSON files under `HARPER_PIPELINE_DATA_DIR`
(default `backend/.data/pipeline/`). Separate from `memory/` domain + agent runtime stores.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FilePipelineStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.events = root / "events"
        self.chunks = root / "chunks"
        self.jobs = root / "jobs" / "rehydration"
        self.index = root / "index"
        self._lock = asyncio.Lock()
        for d in (self.events, self.chunks, self.jobs, self.index):
            d.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)

    async def idempotency_get(self, key: str) -> str | None:
        async with self._lock:
            p = self.index / "idempotency.json"
            if not p.exists():
                return None
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get(key)

    async def idempotency_put(self, key: str, event_id: str) -> None:
        """Prefer `idempotency_reserve_or_get` for ingest to avoid check-then-act races."""
        async with self._lock:
            p = self.index / "idempotency.json"
            data = {}
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
            data[key] = event_id
            self._atomic_write(p, data)

    async def idempotency_reserve_or_get(self, key: str) -> tuple[str, bool]:
        """
        Atomically reserve a new event_id for `key` or return the existing one.

        Returns (event_id, is_duplicate). Safe under concurrent callers: only one
        reservation wins per key; others observe the same event_id as duplicate.
        """
        async with self._lock:
            p = self.index / "idempotency.json"
            data: dict[str, str] = {}
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = {str(k): str(v) for k, v in raw.items()}
            existing = data.get(key)
            if existing is not None:
                return existing, True
            event_id = str(uuid4())
            data[key] = event_id
            self._atomic_write(p, data)
            return event_id, False

    async def save_event_envelope(
        self,
        event_id: str,
        envelope: dict[str, Any],
    ) -> None:
        async with self._lock:
            self._atomic_write(self.events / f"{event_id}.json", envelope)

    async def load_event_envelope(self, event_id: str) -> dict[str, Any] | None:
        p = self.events / f"{event_id}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    async def set_event_stage(self, event_id: str, stage: str, detail: str | None = None) -> None:
        async with self._lock:
            p = self.index / "event_status.json"
            data = {}
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
            data[event_id] = {
                "stage": stage,
                "detail": detail,
                "updated_at": _utc_now_iso(),
            }
            self._atomic_write(p, data)

    async def save_chunk(self, chunk_id: str, record: dict[str, Any]) -> None:
        async with self._lock:
            self._atomic_write(self.chunks / f"{chunk_id}.json", record)

    async def load_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        p = self.chunks / f"{chunk_id}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    async def patch_chunk(self, chunk_id: str, updates: dict[str, Any]) -> None:
        async with self._lock:
            rec = self._read_chunk_file(chunk_id)
            if rec is None:
                logger.warning("patch_chunk missing %s", chunk_id)
                return
            rec.update(updates)
            self._atomic_write(self.chunks / f"{chunk_id}.json", rec)

    def _read_chunk_file(self, chunk_id: str) -> dict[str, Any] | None:
        p = self.chunks / f"{chunk_id}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    async def save_rehydration_job(self, job_id: str, record: dict[str, Any]) -> None:
        async with self._lock:
            self._atomic_write(self.jobs / f"{job_id}.json", record)


_store: FilePipelineStore | None = None


def get_pipeline_store(root: Path | None = None) -> FilePipelineStore:
    global _store
    if _store is None:
        from app.core.settings import settings

        base = root or settings.pipeline_data_dir
        _store = FilePipelineStore(base)
    return _store
