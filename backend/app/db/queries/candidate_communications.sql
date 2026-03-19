-- Pruning-friendly: always bind occurred_at window
-- :tenant_id uuid, :account_id uuid, :occurred_after timestamptz, :occurred_before timestamptz, :limit int
SELECT communication_id, occurred_at, source_type
FROM communications
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND is_latest_revision = true
  AND occurred_at >= :occurred_after
  AND occurred_at < :occurred_before
ORDER BY occurred_at DESC
LIMIT :limit;
