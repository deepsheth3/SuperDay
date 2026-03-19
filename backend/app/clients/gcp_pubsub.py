"""
Publish ingest / job messages to Google Cloud Pub/Sub.

Requires: pip install google-cloud-pubsub
Set HARPER_PUBSUB_PUBLISH_INGEST=true and HARPER_GCP_PROJECT_ID.
For local emulator: export PUBSUB_EMULATOR_HOST=127.0.0.1:8085
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.settings import settings

logger = logging.getLogger(__name__)


def _publisher():
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


async def publish_json(topic_id: str, message: dict[str, Any], *, ordering_key: str | None = None) -> str:
    """
    Publish JSON to topic_id (short name). Returns Pub/Sub message id (server-assigned) or ''.
    """
    if not settings.gcp_project_id:
        logger.warning("pubsub: HARPER_GCP_PROJECT_ID not set; skip publish")
        return ""

    def _run() -> str:
        client = _publisher()
        topic_path = client.topic_path(settings.gcp_project_id, topic_id)
        data = json.dumps(message, default=str).encode("utf-8")
        if ordering_key:
            future = client.publish(topic_path, data, ordering_key=ordering_key)
        else:
            future = client.publish(topic_path, data)
        return future.result(timeout=30)

    return await asyncio.to_thread(_run)


async def publish_ingest_accepted_v1(event_payload: dict[str, Any]) -> str:
    """Publish IngestEventV1-shaped dict to the configured ingest topic."""
    return await publish_json(
        settings.pubsub_ingest_topic_id,
        event_payload,
        ordering_key=str(event_payload.get("tenant_id", "")),
    )
