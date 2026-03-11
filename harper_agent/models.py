"""Pydantic models for HarperGPT agent."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PrimaryEntityType(str, Enum):
    ACCOUNT = "account"
    PERSON = "person"
    AGENT = "agent"
    INDUSTRY = "industry"
    LOCATION = "location"
    UNKNOWN = "unknown"


class ReferenceType(str, Enum):
    ACCOUNT = "account"
    PERSON = "person"


class EntityHints(BaseModel):
    account_name: str | None = None
    person_name: str | None = None
    agent_name: str | None = None
    compare_account_names: list[str] = Field(default_factory=list)  # for compare_accounts intent: [name1, name2]


class EntityConstraints(BaseModel):
    city: str | None = None
    state: str | None = None
    industry: str | None = None
    status: str | None = None
    coverage_type: str | None = None
    time_reference: str | None = None


class EntityReference(BaseModel):
    anaphora: bool = False
    refers_to: ReferenceType | None = None


class EntityFrame(BaseModel):
    primary_entity_type: PrimaryEntityType = PrimaryEntityType.UNKNOWN
    entity_hints: EntityHints = Field(default_factory=EntityHints)
    constraints: EntityConstraints = Field(default_factory=EntityConstraints)
    reference: EntityReference = Field(default_factory=EntityReference)
    intent: str | None = None  # status_query, list_accounts, follow_up, compare_accounts, summarize_activity, suggest_next_action, unknown
    session_goal_hint: str | None = None  # reviewing_one_account | triaging_pipeline | checking_follow_ups | preparing_outreach when user states goal


class ActiveFocus(BaseModel):
    type: str
    id: str
    confidence: float = 0.0


class TurnRecord(BaseModel):
    role: str
    message: str = ""
    resolved_account_id: str | None = None
    resolved_person_id: str | None = None
    list_items: list[str] | None = None
    references: list[dict[str, Any]] | None = None


class PendingDisambiguation(BaseModel):
    """When we asked 'Which one?', store the options and the original query so we can answer after the user picks."""
    candidates: list[dict[str, Any]] = Field(default_factory=list)  # [{"account_id": "...", "name": "..."}, ...]
    original_query: str = ""
    expires_at: datetime | None = None


class SessionState(BaseModel):
    session_id: str = ""
    turn_history: list[TurnRecord] = Field(default_factory=list)
    active_focus: ActiveFocus | None = None
    pending_disambiguation: PendingDisambiguation | None = None
    # Smart session history: capped recent entities and rolling summary
    recent_account_ids: list[str] = Field(default_factory=list)  # max 5, most recent last
    recent_person_ids: list[str] = Field(default_factory=list)   # max 5
    rolling_summary: str = ""                                    # capped ~300 words
    last_intent: str | None = None                               # e.g. status_query, list_accounts
    last_constraints: dict[str, str] = Field(default_factory=dict)  # e.g. {"state": "CO", "industry": "public_sector"}
    session_goal: str | None = None  # reviewing_one_account | triaging_pipeline | checking_follow_ups | preparing_outreach


class EvidenceItem(BaseModel):
    source_path: str = ""
    source_id: str = ""
    content: str | dict[str, Any] = ""
    timestamp: str = ""


class EvidenceBundle(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)


class ComposedAnswer(BaseModel):
    narrative: str = ""
    next_steps: str | None = None
    sources: list[str] = Field(default_factory=list)
