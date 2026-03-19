"""Signed webhook ingest (HMAC). Does not use JWT — verify `X-Harper-Signature`."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import Field

from app.api.ingest import IngestAccepted, IngestBody, handle_ingest_request
from app.core.rate_limit import rate_limit_dependency
from app.core.security import verify_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(rate_limit_dependency("webhook"))])


class WebhookIngestPayload(IngestBody):
    """Same fields as ingest API plus optional route discriminator."""

    ingest_route: str = Field(
        default="email",
        description="One of: email, text, call_transcript",
    )


@router.post("/webhooks/ingest", status_code=202, response_model=IngestAccepted)
async def webhook_ingest_signed(
    request: Request,
    x_trace_id: str | None = Header(None, alias="X-Trace-ID"),
    x_harper_signature: str | None = Header(None, alias="X-Harper-Signature"),
):
    body_bytes = await request.body()
    verify_webhook_signature(body_bytes, x_harper_signature)
    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON body") from e
    payload = WebhookIngestPayload.model_validate(data)
    rk = (payload.ingest_route or "email").strip().lower().replace("-", "_")
    if rk == "call":
        rk = "call_transcript"
    if rk not in ("email", "text", "call_transcript"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ingest_route must be email, text, or call_transcript",
        )
    tid = (payload.tenant_id or "")[:8]
    logger.info("webhook ingest accepted trace=%s tenant_prefix=%s", x_trace_id, tid)
    return await handle_ingest_request(payload, rk, x_trace_id)
