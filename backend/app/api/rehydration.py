from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import Principal, enforce_tenant_match, require_auth_principal
from app.schemas.queue import RehydrationJobV1
from app.services.pipeline.bus import TOPIC_REHYDRATION, get_bus
from app.services.pipeline.store import get_pipeline_store

router = APIRouter()


class RehydrationBody(BaseModel):
    tenant_id: str = Field(..., description="UUID string")
    account_id: str = Field(..., description="UUID string")
    time_range_start: str
    time_range_end: str
    reason: str


class RehydrationAccepted(BaseModel):
    job_id: str
    expected_latency_class: str = "hours"


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@router.post("/rehydration/request", status_code=202, response_model=RehydrationAccepted)
async def request_rehydration(
    body: RehydrationBody,
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
):
    from uuid import UUID

    enforce_tenant_match(principal, body_tenant=body.tenant_id.strip(), header_tenant=None)
    job_id = uuid4()
    try:
        tenant_id = UUID(body.tenant_id.strip())
        account_id = UUID(body.account_id.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="tenant_id and account_id must be UUIDs")
    job = RehydrationJobV1(
        job_id=job_id,
        tenant_id=tenant_id,
        account_id=account_id,
        time_range_start=_parse_dt(body.time_range_start),
        time_range_end=_parse_dt(body.time_range_end),
        reason=body.reason,
    )
    store = get_pipeline_store()
    await store.save_rehydration_job(
        str(job_id),
        {
            "job": job.model_dump(mode="json"),
            "status": "queued",
        },
    )
    bus = get_bus()
    await bus.publish(TOPIC_REHYDRATION, job.model_dump(mode="json"))
    return RehydrationAccepted(job_id=str(job_id))
