-- Harper production schema v1 (PostgreSQL / AlloyDB compatible)
-- Non-partitioned tables for simpler FKs; use bounded occurred_at/received_at in queries for pruning-friendly plans.
-- See sql/maintenance/create_partitions.sql for optional native partitioning rollout.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- tenants
-- ---------------------------------------------------------------------------
CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'suspended', 'disabled')),
    retention_months_hot INT NOT NULL DEFAULT 24,
    retention_policy_json JSONB NOT NULL DEFAULT '{}',
    legal_hold_default BOOLEAN NOT NULL DEFAULT false,
    allowed_source_types TEXT[] NOT NULL DEFAULT ARRAY['email', 'sms', 'call_transcript']::TEXT[],
    config_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tenants_status ON tenants (status);

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    external_principal TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin', 'agent', 'viewer')),
    status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ,
    UNIQUE (tenant_id, external_principal)
);
CREATE INDEX idx_users_tenant_role ON users (tenant_id, role);

-- ---------------------------------------------------------------------------
-- sessions
-- ---------------------------------------------------------------------------
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    user_id UUID REFERENCES users (user_id),
    status TEXT NOT NULL CHECK (status IN ('active', 'closed', 'expired')),
    last_account_id UUID,
    last_scope TEXT,
    summary_text TEXT,
    summary_version INT NOT NULL DEFAULT 1,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 1
);
CREATE INDEX idx_sessions_tenant_user_updated ON sessions (tenant_id, user_id, updated_at DESC);
CREATE INDEX idx_sessions_tenant_last_account ON sessions (tenant_id, last_account_id);

-- ---------------------------------------------------------------------------
-- chat_turns
-- ---------------------------------------------------------------------------
CREATE TABLE chat_turns (
    turn_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    session_id UUID NOT NULL REFERENCES sessions (session_id),
    seq_no INT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    message_text TEXT,
    structured_payload_json JSONB NOT NULL DEFAULT '{}',
    model_name TEXT,
    model_version TEXT,
    prompt_tokens INT,
    completion_tokens INT,
    latency_ms INT,
    trace_id TEXT,
    request_id TEXT,
    degradation_mode TEXT,
    finish_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, session_id, seq_no)
);
CREATE INDEX idx_chat_turns_trace ON chat_turns (trace_id);
CREATE INDEX idx_chat_turns_request ON chat_turns (tenant_id, request_id) WHERE request_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- chat_turn_references
-- ---------------------------------------------------------------------------
CREATE TABLE chat_turn_references (
    turn_reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    turn_id UUID NOT NULL REFERENCES chat_turns (turn_id),
    reference_type TEXT NOT NULL CHECK (reference_type IN ('chunk', 'thread', 'communication', 'timeline')),
    reference_id UUID NOT NULL,
    rank INT,
    citation_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_turn_refs_turn ON chat_turn_references (tenant_id, turn_id);
CREATE INDEX idx_turn_refs_target ON chat_turn_references (tenant_id, reference_type, reference_id);

-- ---------------------------------------------------------------------------
-- accounts
-- ---------------------------------------------------------------------------
CREATE TABLE accounts (
    account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    account_name TEXT NOT NULL,
    normalized_account_name TEXT NOT NULL,
    industry TEXT,
    state TEXT,
    status TEXT,
    owner_user_id UUID REFERENCES users (user_id),
    external_account_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 1
);
CREATE INDEX idx_accounts_tenant_norm_name ON accounts (tenant_id, normalized_account_name);
CREATE INDEX idx_accounts_tenant_industry_state ON accounts (tenant_id, industry, state);
CREATE INDEX idx_accounts_tenant_status ON accounts (tenant_id, status);

-- ---------------------------------------------------------------------------
-- account_aliases
-- ---------------------------------------------------------------------------
CREATE TABLE account_aliases (
    alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    account_id UUID NOT NULL REFERENCES accounts (account_id),
    alias_text TEXT NOT NULL,
    alias_type TEXT NOT NULL CHECK (alias_type IN ('crm_name', 'nickname', 'legacy_name', 'domain')),
    normalized_alias_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_aliases_tenant_norm ON account_aliases (tenant_id, normalized_alias_text);
CREATE INDEX idx_aliases_tenant_account ON account_aliases (tenant_id, account_id);

-- ---------------------------------------------------------------------------
-- persons
-- ---------------------------------------------------------------------------
CREATE TABLE persons (
    person_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    account_id UUID REFERENCES accounts (account_id),
    full_name TEXT,
    normalized_full_name TEXT,
    email TEXT,
    phone TEXT,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 1
);
CREATE INDEX idx_persons_tenant_account_name ON persons (tenant_id, account_id, normalized_full_name);
CREATE INDEX idx_persons_tenant_email ON persons (tenant_id, email);
CREATE INDEX idx_persons_tenant_phone ON persons (tenant_id, phone);

-- ---------------------------------------------------------------------------
-- threads (created before communications FK from comms -> threads optional)
-- ---------------------------------------------------------------------------
CREATE TABLE threads (
    thread_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    account_id UUID NOT NULL REFERENCES accounts (account_id),
    source_type TEXT NOT NULL,
    thread_external_ref TEXT,
    thread_subject TEXT,
    first_occurred_at TIMESTAMPTZ,
    last_occurred_at TIMESTAMPTZ,
    message_count INT NOT NULL DEFAULT 0,
    last_summary_text TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    thread_status_reason TEXT,
    resolution_confidence NUMERIC(5, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 1
);
CREATE INDEX idx_threads_tenant_account_last ON threads (tenant_id, account_id, last_occurred_at DESC);
CREATE INDEX idx_threads_tenant_external ON threads (tenant_id, thread_external_ref);

-- ---------------------------------------------------------------------------
-- communications
-- ---------------------------------------------------------------------------
CREATE TABLE communications (
    communication_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    account_id UUID NOT NULL REFERENCES accounts (account_id),
    thread_id UUID REFERENCES threads (thread_id),
    source_type TEXT NOT NULL CHECK (source_type IN ('email', 'sms', 'call_transcript')),
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_record_version TEXT,
    direction TEXT CHECK (direction IN ('inbound', 'outbound', 'internal')),
    subject TEXT,
    body_text TEXT,
    clean_body_text TEXT,
    summary_text TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sender_person_id UUID REFERENCES persons (person_id),
    language_code TEXT,
    quality_score NUMERIC(5, 2),
    pii_classification TEXT,
    storage_tier TEXT NOT NULL DEFAULT 'hot' CHECK (storage_tier IN ('hot', 'archive')),
    retention_state TEXT NOT NULL DEFAULT 'indexed_hot',
    raw_s3_key TEXT NOT NULL,
    content_hash TEXT,
    is_latest_revision BOOLEAN NOT NULL DEFAULT true,
    supersedes_communication_id UUID REFERENCES communications (communication_id),
    visibility_scope TEXT NOT NULL DEFAULT 'tenant_default',
    extraction_status TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted', 'legal_hold')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX uq_communications_source ON communications (
    tenant_id, source_system, source_record_id, COALESCE(source_record_version, '')
);
CREATE INDEX idx_comms_tenant_account_occurred ON communications (tenant_id, account_id, occurred_at DESC);
CREATE INDEX idx_comms_tenant_thread_occurred ON communications (tenant_id, thread_id, occurred_at);
CREATE INDEX idx_comms_tenant_tier_occurred ON communications (tenant_id, storage_tier, occurred_at);
CREATE INDEX idx_comms_latest_lookup ON communications (tenant_id, is_latest_revision, account_id, occurred_at DESC)
    WHERE is_latest_revision = true;

-- ---------------------------------------------------------------------------
-- communication_participants
-- ---------------------------------------------------------------------------
CREATE TABLE communication_participants (
    communication_participant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    communication_id UUID NOT NULL REFERENCES communications (communication_id),
    person_id UUID REFERENCES persons (person_id),
    participant_type TEXT NOT NULL CHECK (participant_type IN ('from', 'to', 'cc', 'bcc', 'speaker')),
    participant_value TEXT NOT NULL,
    normalized_participant_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_participants_comm ON communication_participants (tenant_id, communication_id);
CREATE INDEX idx_participants_norm ON communication_participants (tenant_id, normalized_participant_value);

-- ---------------------------------------------------------------------------
-- chunks
-- ---------------------------------------------------------------------------
CREATE TABLE chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    account_id UUID NOT NULL REFERENCES accounts (account_id),
    communication_id UUID NOT NULL REFERENCES communications (communication_id),
    thread_id UUID REFERENCES threads (thread_id),
    chunk_no INT NOT NULL,
    chunk_type TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INT,
    chunk_hash TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    source_type TEXT NOT NULL,
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    embedding_model TEXT,
    embedding_version TEXT,
    chunking_version TEXT,
    normalization_version TEXT,
    policy_version TEXT,
    lexical_doc_id TEXT,
    vector_doc_id TEXT,
    raw_s3_key TEXT NOT NULL,
    storage_tier TEXT NOT NULL DEFAULT 'hot',
    retention_state TEXT NOT NULL DEFAULT 'indexed_hot',
    is_retrieval_eligible BOOLEAN NOT NULL DEFAULT true,
    superseded_by_chunk_id UUID REFERENCES chunks (chunk_id),
    chunk_quality_score NUMERIC(5, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_chunks_hash_version ON chunks (
    tenant_id, communication_id, chunk_hash, COALESCE(embedding_version, '')
);
CREATE INDEX idx_chunks_tenant_account_occurred ON chunks (tenant_id, account_id, occurred_at DESC);
CREATE INDEX idx_chunks_tenant_comm_no ON chunks (tenant_id, communication_id, chunk_no);
CREATE INDEX idx_chunks_embedding_status ON chunks (tenant_id, embedding_status, created_at);
CREATE INDEX idx_chunks_failed_pending ON chunks (tenant_id, created_at)
    WHERE embedding_status IN ('pending', 'failed');

-- ---------------------------------------------------------------------------
-- ingestion_events
-- ---------------------------------------------------------------------------
CREATE TABLE ingestion_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    source_type TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    source_record_id TEXT,
    source_record_version TEXT,
    idempotency_key TEXT NOT NULL,
    raw_s3_key TEXT NOT NULL,
    event_schema_version TEXT NOT NULL,
    event_status TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    error_code TEXT,
    error_message TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    trace_id TEXT,
    failed_stage TEXT,
    next_retry_at TIMESTAMPTZ,
    UNIQUE (tenant_id, source_system, source_event_id)
);
CREATE INDEX idx_ingest_tenant_status_received ON ingestion_events (tenant_id, event_status, received_at);
CREATE INDEX idx_ingest_trace ON ingestion_events (trace_id);
CREATE INDEX idx_ingest_replay_window ON ingestion_events (tenant_id, received_at DESC);

-- ---------------------------------------------------------------------------
-- embedding_jobs
-- ---------------------------------------------------------------------------
CREATE TABLE embedding_jobs (
    embedding_job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    chunk_id UUID NOT NULL REFERENCES chunks (chunk_id),
    embedding_model TEXT NOT NULL,
    embedding_version TEXT NOT NULL,
    job_status TEXT NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_embed_jobs_status ON embedding_jobs (tenant_id, job_status, scheduled_at);
CREATE INDEX idx_embed_jobs_chunk ON embedding_jobs (tenant_id, chunk_id);

-- ---------------------------------------------------------------------------
-- reindex_jobs
-- ---------------------------------------------------------------------------
CREATE TABLE reindex_jobs (
    reindex_job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    scope_type TEXT NOT NULL,
    scope_ref TEXT NOT NULL,
    target_embedding_version TEXT,
    target_chunking_version TEXT,
    target_normalization_version TEXT,
    job_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    stats_json JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_reindex_tenant_status ON reindex_jobs (tenant_id, job_status, created_at);

-- ---------------------------------------------------------------------------
-- archiver_runs
-- ---------------------------------------------------------------------------
CREATE TABLE archiver_runs (
    archiver_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    cutoff_time TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    candidate_count INT NOT NULL DEFAULT 0,
    archived_count INT NOT NULL DEFAULT 0,
    vector_deleted_count INT NOT NULL DEFAULT 0,
    error_count INT NOT NULL DEFAULT 0,
    run_status TEXT NOT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_archiver_tenant_started ON archiver_runs (tenant_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- activity_timeline
-- ---------------------------------------------------------------------------
CREATE TABLE activity_timeline (
    timeline_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    account_id UUID NOT NULL REFERENCES accounts (account_id),
    communication_id UUID REFERENCES communications (communication_id),
    thread_id UUID REFERENCES threads (thread_id),
    occurred_at TIMESTAMPTZ NOT NULL,
    activity_type TEXT NOT NULL,
    summary_line TEXT NOT NULL,
    direction TEXT,
    participants_json JSONB NOT NULL DEFAULT '[]',
    source_type TEXT NOT NULL,
    priority_score NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_timeline_tenant_account_occurred ON activity_timeline (tenant_id, account_id, occurred_at DESC);
CREATE INDEX idx_timeline_tenant_account_source ON activity_timeline (tenant_id, account_id, source_type, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- legal_holds
-- ---------------------------------------------------------------------------
CREATE TABLE legal_holds (
    legal_hold_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    scope_type TEXT NOT NULL,
    scope_ref TEXT NOT NULL,
    hold_reason TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('active', 'released'))
);
CREATE INDEX idx_legal_hold_scope ON legal_holds (tenant_id, scope_type, scope_ref, status);

-- ---------------------------------------------------------------------------
-- audit_log (append-only; enforce via app / role GRANT)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    actor TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'service_account', 'system')),
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    old_value_hash TEXT,
    new_value_hash TEXT,
    trace_id TEXT,
    request_id TEXT,
    source_identity TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_tenant_time ON audit_log (tenant_id, occurred_at DESC);
CREATE INDEX idx_audit_trace ON audit_log (trace_id);
CREATE INDEX idx_audit_request ON audit_log (request_id);

-- ---------------------------------------------------------------------------
-- communication_attachments
-- ---------------------------------------------------------------------------
CREATE TABLE communication_attachments (
    attachment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    communication_id UUID NOT NULL REFERENCES communications (communication_id),
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    raw_s3_key TEXT NOT NULL,
    virus_scan_status TEXT NOT NULL DEFAULT 'pending',
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    extracted_text_s3_key TEXT,
    index_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_attach_tenant_comm ON communication_attachments (tenant_id, communication_id);
CREATE INDEX idx_attach_tenant_index ON communication_attachments (tenant_id, index_status, created_at);
CREATE INDEX idx_attach_pending_extract ON communication_attachments (tenant_id, communication_id)
    WHERE extraction_status = 'pending';

-- ---------------------------------------------------------------------------
-- tenant_features
-- ---------------------------------------------------------------------------
CREATE TABLE tenant_features (
    tenant_feature_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants (tenant_id),
    feature_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT false,
    config_json JSONB NOT NULL DEFAULT '{}',
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tenant_features_lookup ON tenant_features (tenant_id, feature_name, effective_from DESC);
-- At most one "current" open-ended row per tenant+feature (optional; historical rows set effective_to)
CREATE UNIQUE INDEX uq_tenant_feature_open ON tenant_features (tenant_id, feature_name) WHERE effective_to IS NULL;
