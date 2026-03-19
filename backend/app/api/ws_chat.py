"""
Optional WebSocket surface (duplex / low-latency experiments).

Auth: when `HARPER_JWT_JWKS_URL` is set, pass `?access_token=<JWT>` (or `?token=`).
Anonymous allowed when JWKS URL is unset (local dev).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.security import decode_bearer_token
from app.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    token = websocket.query_params.get("access_token") or websocket.query_params.get("token")
    principal = None
    if settings.jwt_jwks_url:
        if not token:
            await websocket.close(code=4401, reason="auth required")
            return
        try:
            principal = decode_bearer_token(token)
        except HTTPException:
            await websocket.close(code=4401, reason="invalid token")
            return
    hello = {
        "type": "ready",
        "authenticated": principal is not None,
        "subject": principal.subject if principal else None,
        "tenant_id": principal.tenant_id if principal else None,
        "note": "stub echo; replace with streaming agent protocol as needed",
    }
    await websocket.send_json(hello)
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = ""
            if "text" in msg:
                text = str(msg["text"])
            elif isinstance(msg.get("bytes"), (bytes, bytearray)):
                try:
                    text = bytes(msg["bytes"]).decode("utf-8", errors="replace")
                except Exception:
                    text = ""
            if not text.strip():
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = {"raw": text}
            await websocket.send_json({"type": "echo", "payload": parsed})
    except WebSocketDisconnect:
        pass
