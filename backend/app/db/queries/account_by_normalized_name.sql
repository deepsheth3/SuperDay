-- :tenant_id uuid, :normalized text
SELECT account_id
FROM accounts
WHERE tenant_id = :tenant_id
  AND normalized_account_name = :normalized
LIMIT 1;
