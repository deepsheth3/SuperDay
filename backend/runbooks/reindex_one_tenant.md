# Reindex one tenant

1. Insert `reindex_jobs` row: `scope_type=tenant`, `scope_ref=<tenant_uuid>`, `job_status=queued`.
2. Publish `ReindexJobV1` to `reindex-run` with `reindex_job_id`.
3. Watch embed worker metrics and `chunks.embedding_status`.
4. On completion, update `reindex_jobs.job_status=success` and `stats_json`.
