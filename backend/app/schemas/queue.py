from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class IngestEventV1(BaseModel):
    schema_version: Literal["IngestEventV1"] = "IngestEventV1"
    event_id: UUID
    tenant_id: UUID
    source_type: Literal["email", "sms", "call_transcript"]
    source_system: str
    source_event_id: str
    source_record_id: str | None = None
    source_record_version: str | None = None
    idempotency_key: str
    raw_s3_key: str
    occurred_at: datetime | None = None
    received_at: datetime
    trace_id: str | None = None


class EmbedJobV1(BaseModel):
    schema_version: Literal["EmbedJobV1"] = "EmbedJobV1"
    embedding_job_id: UUID
    tenant_id: UUID
    chunk_id: UUID
    embedding_model: str
    embedding_version: str = Field(default="v1")
    trace_id: str | None = None


class ArchiveJobV1(BaseModel):
    schema_version: Literal["ArchiveJobV1"] = "ArchiveJobV1"
    archiver_run_id: UUID
    tenant_id: UUID
    cutoff_time: datetime
    batch_cursor: str | None = None


class ReindexJobV1(BaseModel):
    schema_version: Literal["ReindexJobV1"] = "ReindexJobV1"
    reindex_job_id: UUID
    tenant_id: UUID
    scope_type: str
    scope_ref: str
    target_embedding_version: str | None = None
    target_chunking_version: str | None = None
    target_normalization_version: str | None = None


class RehydrationJobV1(BaseModel):
    schema_version: Literal["RehydrationJobV1"] = "RehydrationJobV1"
    job_id: UUID
    tenant_id: UUID
    account_id: UUID
    time_range_start: datetime
    time_range_end: datetime
    reason: str


class FollowupRunJobV1(BaseModel):
    """Scheduled or manual run: find threads awaiting client reply and enqueue outbound actions."""

    schema_version: Literal["FollowupRunJobV1"] = "FollowupRunJobV1"
    run_id: UUID
    tenant_id: UUID
    as_of: datetime = Field(description="Selection window anchor (e.g. last outbound before this time)")
    max_accounts: int = Field(default=100, ge=1, le=10_000)
    policy_version: str = "v1"
    trace_id: str | None = None
