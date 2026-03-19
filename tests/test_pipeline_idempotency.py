"""Pipeline store: atomic ingest idempotency under concurrency."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from app.services.pipeline.store import FilePipelineStore


def test_idempotency_reserve_or_get_single_writer() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = FilePipelineStore(Path(tmp))
        key = "tenant:src:evt-1"

        async def run() -> None:
            results = await asyncio.gather(
                *[store.idempotency_reserve_or_get(key) for _ in range(30)]
            )
            ids = [r[0] for r in results]
            dups = [r[1] for r in results]
            assert len(set(ids)) == 1, "all concurrent reserves must share one event_id"
            assert sum(1 for d in dups if not d) == 1, "exactly one non-duplicate"
            assert sum(dups) == 29, "rest are duplicates"

        asyncio.run(run())
