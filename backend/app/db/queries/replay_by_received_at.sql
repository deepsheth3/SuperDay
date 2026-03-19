-- Replay / ops: use received_at window
-- :tenant_id uuid, :received_after timestamptz, :received_before timestamptz, :limit int
SELECT event_id, source_system, source_event_id, event_status, received_at, failed_stage, next_retry_at
FROM ingestion_events
WHERE tenant_id = :tenant_id
  AND received_at >= :received_after
  AND received_at < :received_before
ORDER BY received_at ASC
LIMIT :limit;
