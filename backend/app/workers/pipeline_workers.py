"""Background consumers: normalize → embed; rehydration / archive / reindex stubs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.clients.embedding import embed_and_index_chunk
from app.core.settings import settings
from app.schemas.queue import EmbedJobV1, IngestEventV1, RehydrationJobV1
from app.services.pipeline.bus import (
    TOPIC_ARCHIVE,
    TOPIC_EMBED_CHUNK,
    TOPIC_FOLLOWUP_RUN,
    TOPIC_INGEST_ACCEPTED,
    TOPIC_REHYDRATION,
    TOPIC_REINDEX,
    get_bus,
)
from app.services.pipeline.chunking import chunk_hash, chunk_text
from app.services.pipeline.store import get_pipeline_store

logger = logging.getLogger(__name__)


async def _normalize_worker() -> None:
    bus = get_bus()
    store = get_pipeline_store()
    q = bus.queue_for(TOPIC_INGEST_ACCEPTED)
    while True:
        msg = await q.get()
        event_id = msg.get("event_id")
        if not event_id:
            continue
        try:
            env = await store.load_event_envelope(event_id)
            if not env:
                logger.warning("normalize: missing envelope %s", event_id)
                continue
            raw = env.get("raw_body_text") or ""
            if env.get("subject"):
                raw = f"Subject: {env['subject']}\n\n{raw}"
            parts = chunk_text(raw)
            if not parts:
                parts = ["(empty body)"]
            ev = IngestEventV1.model_validate(env["event"])
            comm_id = str(uuid4())
            chunk_ids: list[str] = []
            for i, text in enumerate(parts):
                cid = str(uuid4())
                chunk_ids.append(cid)
                h = chunk_hash(text)
                rec = {
                    "chunk_id": cid,
                    "tenant_id": str(ev.tenant_id),
                    "account_id": env.get("account_id"),
                    "communication_id": comm_id,
                    "event_id": event_id,
                    "chunk_no": i,
                    "chunk_text": text,
                    "chunk_hash": h,
                    "source_type": ev.source_type,
                    "occurred_at": (ev.occurred_at or ev.received_at).isoformat(),
                    "embedding_status": "pending",
                }
                await store.save_chunk(cid, rec)
                job = EmbedJobV1(
                    embedding_job_id=uuid4(),
                    tenant_id=ev.tenant_id,
                    chunk_id=UUID(cid),
                    embedding_model=settings.embedding_model,
                    embedding_version=settings.embedding_version,
                    trace_id=ev.trace_id,
                )
                await bus.publish(TOPIC_EMBED_CHUNK, job.model_dump(mode="json"))
            env["communication_id"] = comm_id
            env["chunk_count"] = len(parts)
            env["chunk_ids"] = chunk_ids
            env["event_status"] = "normalized"
            await store.save_event_envelope(event_id, env)
            await store.set_event_stage(event_id, "normalized", f"chunks={len(parts)}")
        except Exception:
            logger.exception("normalize failed event_id=%s", event_id)
            await store.set_event_stage(event_id, "normalize_error", "see logs")


async def _embed_worker() -> None:
    bus = get_bus()
    store = get_pipeline_store()
    q = bus.queue_for(TOPIC_EMBED_CHUNK)
    while True:
        raw = await q.get()
        cid: str | None = None
        try:
            job = EmbedJobV1.model_validate(raw)
            cid = str(job.chunk_id)
            chunk = await store.load_chunk(cid)
            if not chunk:
                logger.warning("embed: missing chunk %s", cid)
                continue
            text = chunk.get("chunk_text") or ""
            result = await embed_and_index_chunk(
                chunk_id=cid,
                chunk_text=text,
                tenant_id=str(job.tenant_id),
                embedding_model=job.embedding_model,
                source_type=str(chunk.get("source_type") or ""),
            )
            await store.patch_chunk(cid, result)
            eid = chunk.get("event_id")
            if eid:
                env = await store.load_event_envelope(str(eid))
                if env:
                    ids = env.get("chunk_ids") or []
                    all_done = False
                    if ids:
                        all_done = True
                        for x in ids:
                            c2 = await store.load_chunk(x)
                            if not c2 or c2.get("embedding_status") != "indexed":
                                all_done = False
                                break
                    if all_done:
                        env["event_status"] = "pipeline_done"
                        await store.save_event_envelope(str(eid), env)
                        await store.set_event_stage(str(eid), "pipeline_done")
                    else:
                        await store.set_event_stage(str(eid), "embed_progress", f"chunk={cid}")
        except Exception:
            logger.exception("embed failed payload=%s", raw)
            if cid:
                await store.patch_chunk(cid, {"embedding_status": "failed"})


async def _rehydration_worker() -> None:
    bus = get_bus()
    store = get_pipeline_store()
    q = bus.queue_for(TOPIC_REHYDRATION)
    while True:
        raw = await q.get()
        try:
            job = RehydrationJobV1.model_validate(raw)
            jid = str(job.job_id)
            rec = {
                "job": job.model_dump(mode="json"),
                "status": "running",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await store.save_rehydration_job(jid, rec)
            # Simulate S3 read + re-embed path (no-op beyond delay)
            await asyncio.sleep(0.05)
            rec["status"] = "completed"
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            await store.save_rehydration_job(jid, rec)
        except Exception:
            logger.exception("rehydration failed payload=%s", raw)


async def _archive_worker() -> None:
    bus = get_bus()
    q = bus.queue_for(TOPIC_ARCHIVE)
    while True:
        msg = await q.get()
        logger.info("archive_worker ack (stub) msg_keys=%s", list(msg.keys()))


async def _reindex_worker() -> None:
    bus = get_bus()
    q = bus.queue_for(TOPIC_REINDEX)
    while True:
        msg = await q.get()
        logger.info("reindex_worker ack (stub) msg_keys=%s", list(msg.keys()))


async def _followup_worker() -> None:
    """Proactive follow-up agent (stub): will query DB + send outbound comms — see docs/FOLLOWUP_AGENT.md."""
    bus = get_bus()
    q = bus.queue_for(TOPIC_FOLLOWUP_RUN)
    while True:
        msg = await q.get()
        logger.info(
            "followup_worker (stub): implement selection + outbound; payload_keys=%s",
            list(msg.keys()),
        )


def start_background_workers() -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(_normalize_worker(), name="normalize"),
        asyncio.create_task(_embed_worker(), name="embed"),
        asyncio.create_task(_rehydration_worker(), name="rehydration"),
        asyncio.create_task(_archive_worker(), name="archive"),
        asyncio.create_task(_reindex_worker(), name="reindex"),
        asyncio.create_task(_followup_worker(), name="followup"),
    ]


async def _run_standalone() -> None:
    """Run workers only (e.g. separate Cloud Run service later)."""
    logging.basicConfig(level=logging.INFO)
    start_background_workers()
    stop = asyncio.Event()
    await stop.wait()


if __name__ == "__main__":
    asyncio.run(_run_standalone())
