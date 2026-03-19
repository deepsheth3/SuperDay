from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FreshnessNotice(BaseModel):
    message: str = ""
    partial_index: bool = False
    max_lag_seconds: int | None = None


class DisambiguationCandidate(BaseModel):
    account_id: UUID
    display_name: str = ""
    confidence: float = 0.0


class DisambiguationPayload(BaseModel):
    candidates: list[DisambiguationCandidate]
    original_query: str = ""


class Reference(BaseModel):
    reference_type: str
    reference_id: UUID
    citation_text: str | None = None


class ChatRequest(BaseModel):
    message: str
    request_id: UUID = Field(default_factory=uuid.uuid4)
    session_id: UUID | None = None
    goal: str | None = None
    tenant_id: UUID | None = None
    resume_token: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str | None = None
    request_id: UUID | None = None
    list_items: list[str] | None = None
    references: list[dict[str, Any]] | None = None
    suggested_follow_ups: list[str] | None = None
    freshness_notice: FreshnessNotice | None = None
    disambiguation: DisambiguationPayload | None = None
    idempotent_replay: bool = False


class HistoryResponse(BaseModel):
    turns: list[dict[str, Any]]
    session_id: str


class TranscriptResponse(BaseModel):
    turns: list[dict[str, Any]]
    session_id: str
