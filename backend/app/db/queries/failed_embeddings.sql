-- :tenant_id uuid, :limit int
SELECT chunk_id, communication_id, embedding_status, created_at
FROM chunks
WHERE tenant_id = :tenant_id
  AND embedding_status IN ('pending', 'failed')
ORDER BY created_at ASC
LIMIT :limit;
