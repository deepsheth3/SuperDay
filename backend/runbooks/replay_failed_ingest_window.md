# Replay failed ingest window

1. Identify window: `received_at` between `T0` and `T1` for `tenant_id`.
2. Query: use `app/db/queries/replay_by_received_at.sql` with `event_status IN ('failed','received')` as needed.
3. For each `event_id`: verify `raw_s3_key` exists in S3.
4. Publish `IngestEventV1` to `ingest-accepted` with **same** `source_system` + `source_event_id` (idempotent).
5. Monitor `normalize-dlq` depth and `ingestion_events.retry_count`.
