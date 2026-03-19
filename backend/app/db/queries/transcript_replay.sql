-- :tenant_id uuid, :session_id uuid
SELECT turn_id, seq_no, role, message_text, request_id, trace_id, created_at
FROM chat_turns
WHERE tenant_id = :tenant_id
  AND session_id = :session_id
ORDER BY seq_no ASC;
