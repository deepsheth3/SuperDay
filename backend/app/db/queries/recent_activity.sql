-- :tenant_id uuid, :account_id uuid, :limit int
SELECT timeline_id, communication_id, thread_id, occurred_at, summary_line, source_type
FROM activity_timeline
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
ORDER BY occurred_at DESC
LIMIT :limit;
