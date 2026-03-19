# Worker contracts (executable handler specs)

## Shared

- **Delivery:** Pub/Sub at-least-once; handlers **idempotent**.
- **DLQ:** after **10** retries with exponential backoff + jitter; poison messages to DLQ topic; alert on depth.
- **Metrics:** `worker_handler_latency_ms`, `worker_handler_errors_total`, `pubsub_retry_count`, labels: `tenant_id`, `worker_type`, `handler`.

---

## Normalize worker

| Field | Value |
|-------|--------|
| **Subscription** | `ingest-accepted` |
| **Input payload** | `IngestEventV1` (JSON) |
| **Idempotency key** | `(tenant_id, source_system, source_event_id)` → dedupe on `ingestion_events` |
| **Transaction** | Single DB txn: communications, threads, participants, chunks, timeline, ingestion_events status (`## 45.1`) |
| **Emits** | `EmbedJobV1` per chunk (or batch message) |
| **Retry** | Transient DB/S3 errors; **no** retry on unique violation duplicate event (ack) |
| **DLQ** | Schema invalid, poison payload, repeated failure after max attempts |

---

## Embed worker (owns **Vertex + OpenSearch** upserts)

| Field | Value |
|-------|--------|
| **Subscription** | `embed-chunk` |
| **Input payload** | `EmbedJobV1` |
| **Idempotency key** | `(chunk_id, embedding_version)` — skip if chunk already `embedding_status=indexed` |
| **Transaction** | DB: update `chunks`, `embedding_jobs` only; **no** txn spanning Vertex+OS |
| **Side effects** | Upsert **Vertex** vector doc; upsert **OpenSearch** lexical doc (same handler, sequential or parallel with per-call timeouts) |
| **Metrics** | `embed_success_total`, `embed_latency_ms`, `index_lexical_errors_total`, `index_vector_errors_total` |
| **DLQ** | Unrecoverable embedding API errors after retries; chunk marked `failed` |

---

## Archiver worker

| Field | Value |
|-------|--------|
| **Subscription** | `archive-run` |
| **Input** | `ArchiveJobV1` |
| **Idempotency** | `(archiver_run_id, batch_cursor)` |
| **Transaction** | DB batch update `chunks` / `communications` retention fields; vector deletes **outside** txn |
| **DLQ** | Repeated S3/vector failures |

---

## Reindex worker

| Field | Value |
|-------|--------|
| **Subscription** | `reindex-run` |
| **Input** | `ReindexJobV1` |
| **Idempotency** | `(reindex_job_id, chunk_cursor)` |
| **Transaction** | Per-batch DB read + job status update |
| **Emits** | `EmbedJobV1` for affected chunks |
| **DLQ** | Job-level failure with `stats_json` error |

---

## Rehydration worker

| Field | Value |
|-------|--------|
| **Subscription** | `rehydration-request` |
| **Input** | `RehydrationJobV1` |
| **Idempotency** | `job_id` |
| **Transaction** | Track job state in DB table (add `rehydration_jobs` if not present) |
| **Side effects** | Read S3 → normalize → embed → temporary Vertex index per policy |
| **DLQ** | Auth/policy failure; repeated read failures |

---

## Follow-up agent worker

| Field | Value |
|-------|--------|
| **Subscription** | `followup-run` |
| **Input** | `FollowupRunJobV1` |
| **Idempotency** | `(tenant_id, run_id, thread_id, outbound_attempt_id)` — no duplicate sends on retry |
| **Transaction** | Read candidates in DB txn; each outbound send its own txn + idempotent key |
| **Side effects** | Outbound email/SMS (or queue to provider); append `communications` + timeline |
| **DLQ** | Provider hard failures after retries; invalid policy version |
| **Spec** | [`FOLLOWUP_AGENT.md`](FOLLOWUP_AGENT.md) |
