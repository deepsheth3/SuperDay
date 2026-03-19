"""
Chat routes — synchronous user chat (reactive agent).

Delegates to `harper_agent` via `harper_bridge` using **file-first** stores under
`HARPER_MEMORY_ROOT`: **domain memory** (`objects/`, `indices/`) and **agent runtime state**
(`sessions/`, `transcripts/`). DB-backed chat retrieval is not wired here yet.
"""

from __future__ import annotations

import json
import uuid
from queue import Empty, Queue
from threading import Thread
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.rate_limit import rate_limit_dependency
from app.core.security import Principal, enforce_tenant_match, require_auth_principal
from app.schemas.api import ChatRequest, ChatResponse, HistoryResponse, TranscriptResponse
from app.services import harper_bridge

router = APIRouter()


def _tenant_str(x_tenant_id: str | None, body_tenant: UUID | None) -> str | None:
    if body_tenant is not None:
        return str(body_tenant)
    if x_tenant_id and x_tenant_id.strip():
        return x_tenant_id.strip()
    return None


def _effective_tenant_id(
    principal: Principal | None,
    x_tenant_id: str | None,
    body_tenant: UUID | None,
) -> str | None:
    token_tid = enforce_tenant_match(
        principal,
        body_tenant=str(body_tenant) if body_tenant is not None else None,
        header_tenant=x_tenant_id,
    )
    if token_tid is not None:
        return token_tid
    return _tenant_str(x_tenant_id, body_tenant)


def _history_tenant(principal: Principal | None, header_tenant: str | None) -> str | None:
    if principal and principal.tenant_id:
        if header_tenant and header_tenant.strip() and header_tenant.strip() != principal.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="X-Tenant-ID mismatch with token",
            )
        return principal.tenant_id
    if header_tenant and header_tenant.strip():
        return header_tenant.strip()
    return None


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(rate_limit_dependency("chat"))],
)
async def post_chat(
    body: ChatRequest,
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    x_trace_id: str | None = Header(None, alias="X-Trace-ID"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
):
    tenant_id = _effective_tenant_id(principal, x_tenant_id, body.tenant_id)
    session_str = str(body.session_id) if body.session_id else None
    trace_id = (x_trace_id or x_request_id or str(uuid.uuid4())).strip()
    request_id = str(body.request_id)

    result = await run_in_threadpool(
        harper_bridge.sync_run_chat,
        session_str,
        body.message.strip(),
        body.goal,
        tenant_id,
        trace_id,
        request_id,
    )
    return ChatResponse(
        reply=result["reply"],
        session_id=result.get("session_id"),
        request_id=UUID(result["request_id"]) if result.get("request_id") else body.request_id,
        list_items=result.get("list_items"),
        references=result.get("references"),
        suggested_follow_ups=result.get("suggested_follow_ups"),
    )


@router.post("/chat/stream", dependencies=[Depends(rate_limit_dependency("chat"))])
async def post_chat_stream(
    body: ChatRequest,
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    x_trace_id: str | None = Header(None, alias="X-Trace-ID"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
):
    tenant_id = _effective_tenant_id(principal, x_tenant_id, body.tenant_id)
    session_str = str(body.session_id) if body.session_id else None
    trace_id = (x_trace_id or x_request_id or str(uuid.uuid4())).strip()
    request_id = str(body.request_id)
    message = body.message.strip()

    queue: Queue = Queue()

    def stream_callback(event: str, payload: Any) -> None:
        queue.put((event, payload))

    def run() -> None:
        try:
            harper_bridge.prepare_harper_env()
            from harper_agent.main import run_agent_loop
            from harper_agent.session_manager import create_session_id

            sid = session_str or create_session_id()
            run_agent_loop(
                sid,
                message,
                goal=body.goal,
                tenant_id=tenant_id,
                trace_id=trace_id,
                request_id=request_id or None,
                stream_callback=stream_callback,
            )
        except Exception as e:
            queue.put(("error", str(e)))

    thread = Thread(target=run, daemon=True)
    thread.start()

    def generate():
        while True:
            try:
                event, payload = queue.get(timeout=120)
            except Empty:
                break
            if event == "chunk":
                yield f"data: {json.dumps({'chunk': payload})}\n\n"
            elif event == "result":
                data = payload if isinstance(payload, dict) else {}
                result_wrap: dict[str, Any] = {
                    "reply": data.get("narrative", "") if isinstance(data, dict) else "",
                    "session_id": data.get("session_id") if isinstance(data, dict) else None,
                    "request_id": data.get("request_id", request_id) if isinstance(data, dict) else request_id,
                }
                if isinstance(data, dict):
                    for k in ("list_items", "references", "suggested_follow_ups"):
                        if k in data:
                            result_wrap[k] = data[k]
                yield f"data: {json.dumps({'result': result_wrap})}\n\n"
                break
            elif event == "error":
                yield f"data: {json.dumps({'error': payload})}\n\n"
                break

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    session_id: str | None = None,
    tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
):
    if not session_id:
        return HistoryResponse(turns=[], session_id="")
    eff = _history_tenant(principal, tenant_id)
    turns = await run_in_threadpool(harper_bridge.sync_history_turns, session_id, eff)
    return HistoryResponse(turns=turns, session_id=session_id)


@router.get("/transcript", response_model=TranscriptResponse)
async def get_transcript_route(
    principal: Annotated[Principal | None, Depends(require_auth_principal)],
    session_id: str | None = None,
    tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
):
    if not session_id:
        return TranscriptResponse(turns=[], session_id="")
    eff = _history_tenant(principal, tenant_id)
    turns = await run_in_threadpool(harper_bridge.sync_get_transcript, session_id, eff)
    return TranscriptResponse(turns=turns, session_id=session_id)
