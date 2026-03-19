"""Inspect file-backed pipeline state (dev / ops)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_auth_principal
from app.services.pipeline.store import get_pipeline_store

router = APIRouter(dependencies=[Depends(require_auth_principal)])


@router.get("/pipeline/events/{event_id}")
async def get_pipeline_event(event_id: str) -> dict[str, Any]:
    store = get_pipeline_store()
    env = await store.load_event_envelope(event_id)
    if not env:
        raise HTTPException(status_code=404, detail="unknown event_id")
    stage = None
    p = store.index / "event_status.json"
    if p.exists():
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        stage = data.get(event_id)
    return {"envelope": env, "stage": stage}


@router.get("/pipeline/jobs/rehydration/{job_id}")
async def get_rehydration_job(job_id: str) -> dict[str, Any]:
    store = get_pipeline_store()
    p = store.jobs / f"{job_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="unknown job_id")
    import json

    return json.loads(p.read_text(encoding="utf-8"))
