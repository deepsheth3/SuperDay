from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.core.rate_limit import rate_limit_dependency
from app.core.security import Principal, enforce_tenant_match, require_auth_principal
from app.services.pipeline.ingest_accept import accept_ingest, source_type_for_route

router = APIRouter(dependencies=[Depends(rate_limit_dependency("ingest"))])


class IngestAccepted(BaseModel):
    event_id: str
    trace_id: str = ""
    idempotent_replay: bool = False


class IngestBody(BaseModel):
    tenant_id: str
    source_system: str
    source_event_id: str
    raw_payload_ref: str = ""
    occurred_at: str | None = None
    raw_body_text: str | None = None
    subject: str | None = None
    account_id: str | None = None


async def handle_ingest_request(
    body: IngestBody,
    route_key: str,
    x_trace_id: str | None,
) -> IngestAccepted:
    st = source_type_for_route(route_key)
    event_id, dup = await accept_ingest(
        tenant_id=body.tenant_id,
        source_type=st,
        source_system=body.source_system,
        source_event_id=body.source_event_id,
        raw_payload_ref=body.raw_payload_ref,
        occurred_at=body.occurred_at,
        raw_body_text=body.raw_body_text,
        subject=body.subject,
        trace_id=x_trace_id,
        account_id=body.account_id,
    )
    return IngestAccepted(
        event_id=event_id,
        trace_id=x_trace_id or "",
        idempotent_replay=dup,
    )


def _assert_ingest_tenant(
    principal: Principal | None,
    body_tenant: str,
    x_tenant_id: str | None,
) -> None:
    enforce_tenant_match(principal, body_tenant=body_tenant, header_tenant=x_tenant_id)


@router.post("/ingest/email", status_code=202, response_model=IngestAccepted)
async def ingest_email(
    body: IngestBody,
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    x_trace_id: str | None = Header(None, alias="X-Trace-ID"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
):
    _assert_ingest_tenant(principal, body.tenant_id, x_tenant_id)
    return await handle_ingest_request(body, "email", x_trace_id)


@router.post("/ingest/text", status_code=202, response_model=IngestAccepted)
async def ingest_text(
    body: IngestBody,
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    x_trace_id: str | None = Header(None, alias="X-Trace-ID"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
):
    _assert_ingest_tenant(principal, body.tenant_id, x_tenant_id)
    return await handle_ingest_request(body, "text", x_trace_id)


@router.post("/ingest/call_transcript", status_code=202, response_model=IngestAccepted)
async def ingest_call(
    body: IngestBody,
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    x_trace_id: str | None = Header(None, alias="X-Trace-ID"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
):
    _assert_ingest_tenant(principal, body.tenant_id, x_tenant_id)
    return await handle_ingest_request(body, "call_transcript", x_trace_id)


class BatchBody(BaseModel):
    items: list[IngestBody] = Field(max_length=500)


class BatchItemResult(BaseModel):
    source_event_id: str
    event_id: str | None = None
    idempotent_replay: bool = False
    error: str | None = None


@router.post("/ingest/batch", status_code=202)
async def ingest_batch(
    body: BatchBody,
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    x_trace_id: str | None = Header(None, alias="X-Trace-ID"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
):
    accepted: list[BatchItemResult] = []
    rejected: list[BatchItemResult] = []
    for item in body.items:
        try:
            _assert_ingest_tenant(principal, item.tenant_id, x_tenant_id)
            sys_l = (item.source_system or "").lower()
            if "call" in sys_l:
                rkey = "call_transcript"
            elif "sms" in sys_l:
                rkey = "text"
            else:
                rkey = "email"
            st = source_type_for_route(rkey)
            event_id, dup = await accept_ingest(
                tenant_id=item.tenant_id,
                source_type=st,
                source_system=item.source_system,
                source_event_id=item.source_event_id,
                raw_payload_ref=item.raw_payload_ref,
                occurred_at=item.occurred_at,
                raw_body_text=item.raw_body_text,
                subject=item.subject,
                trace_id=x_trace_id,
                account_id=item.account_id,
            )
            accepted.append(
                BatchItemResult(
                    source_event_id=item.source_event_id,
                    event_id=event_id,
                    idempotent_replay=dup,
                )
            )
        except ValueError as e:
            rejected.append(
                BatchItemResult(source_event_id=item.source_event_id, error=str(e)),
            )
        except Exception as e:
            rejected.append(
                BatchItemResult(source_event_id=item.source_event_id, error=str(e)),
            )
    return {"accepted": accepted, "rejected": rejected}
