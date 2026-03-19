"""In-process async bus — same topics as planned Pub/Sub subscriptions."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# Topic names align with worker_contracts.md subscription IDs
TOPIC_INGEST_ACCEPTED = "ingest.accepted"
TOPIC_EMBED_CHUNK = "embed.chunk"
TOPIC_REHYDRATION = "rehydration.request"
TOPIC_ARCHIVE = "archive.run"
TOPIC_REINDEX = "reindex.run"
TOPIC_FOLLOWUP_RUN = "followup.run"


class LocalAsyncBus:
    """At-least-once within process: consumers must be idempotent."""

    def __init__(self, max_queue: int = 50_000) -> None:
        self._max = max_queue
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = defaultdict(
            lambda: asyncio.Queue(maxsize=max_queue)
        )
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        q = self._queues[topic]
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            logger.error("bus queue full topic=%s", topic)
            raise

    def queue_for(self, topic: str) -> asyncio.Queue[dict[str, Any]]:
        return self._queues[topic]


_bus: LocalAsyncBus | None = None


def get_bus() -> LocalAsyncBus:
    global _bus
    if _bus is None:
        _bus = LocalAsyncBus()
    return _bus
