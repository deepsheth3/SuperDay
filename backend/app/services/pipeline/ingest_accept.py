"""Accept ingest HTTP → IngestEventV1 on bus + disk (idempotent)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

from pydantic import ValidationError

from app.core.settings import settings
from app.schemas.queue import IngestEventV1
from app.services.pipeline.bus import TOPIC_INGEST_ACCEPTED, get_bus
from app.services.pipeline.store import get_pipeline_store

logger = logging.getLogger(__name__)

_DEFAULT_NS = UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def synthetic_account_id(tenant_id: UUID) -> UUID:
    return uuid5(_DEFAULT_NS, f"pipeline-default-account:{tenant_id}")


def _parse_uuid(s: str, field: str) -> UUID:
    try:
        return UUID(s.strip())
    except ValueError as e:
        raise ValueError(f"invalid {field}") from e


def build_idempotency_key(tenant_id: UUID, source_system: str, source_event_id: str) -> str:
    return f"{tenant_id}:{source_system}:{source_event_id}"


async def accept_ingest(
    *,
    tenant_id: str,
    source_type: str,
    source_system: str,
    source_event_id: str,
    raw_payload_ref: str,
    occurred_at: str | None,
    raw_body_text: str | None,
    subject: str | None,
    trace_id: str | None,
    account_id: str | None,
) -> tuple[str, bool]:
    """
    Returns (event_id, is_duplicate).
    Persists envelope and publishes to ingest.accepted.
    """
    tid = _parse_uuid(tenant_id, "tenant_id")
    idem = build_idempotency_key(tid, source_system, source_event_id)
    store = get_pipeline_store()
    event_id, is_duplicate = await store.idempotency_reserve_or_get(idem)
    if is_duplicate:
        return event_id, True

    occurred: datetime | None = None
    if occurred_at:
        try:
            occurred = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            occurred = None

    received_at = datetime.now(timezone.utc)
    raw_s3_key = raw_payload_ref.strip() or f"inline:{event_id}"
    if raw_body_text and not raw_payload_ref.strip():
        raw_s3_key = f"inline:{event_id}"

    acc: UUID | None = None
    if account_id and account_id.strip():
        acc = _parse_uuid(account_id, "account_id")
    if acc is None:
        acc = synthetic_account_id(tid)

    try:
        event = IngestEventV1(
            event_id=UUID(event_id),
            tenant_id=tid,
            source_type=source_type,  # type: ignore[arg-type]
            source_system=source_system,
            source_event_id=source_event_id,
            source_record_id=source_event_id,
            source_record_version=None,
            idempotency_key=idem,
            raw_s3_key=raw_s3_key,
            occurred_at=occurred,
            received_at=received_at,
            trace_id=trace_id,
        )
    except ValidationError as e:
        raise ValueError(str(e)) from e

    envelope: dict[str, Any] = {
        "event": event.model_dump(mode="json"),
        "raw_body_text": raw_body_text or "",
        "subject": subject or "",
        "account_id": str(acc),
        "event_status": "accepted",
    }
    await store.save_event_envelope(event_id, envelope)
    await store.set_event_stage(event_id, "queued_normalize")

    bus = get_bus()
    await bus.publish(TOPIC_INGEST_ACCEPTED, {"event_id": event_id})
    if settings.pubsub_publish_ingest:
        try:
            from app.clients.gcp_pubsub import publish_ingest_accepted_v1

            await publish_ingest_accepted_v1(event.model_dump(mode="json"))
        except ImportError:
            logger.warning("google-cloud-pubsub not installed; skip Pub/Sub publish")
        except Exception:
            logger.exception("Pub/Sub publish failed (ingest still accepted locally)")
    logger.info("ingest accepted event_id=%s tenant=%s", event_id, tid)
    return event_id, False


def source_type_for_route(route_suffix: str) -> str:
    """Map route name to IngestEventV1 source_type."""
    m = {"email": "email", "text": "sms", "call_transcript": "call_transcript"}
    return m.get(route_suffix, "email")
