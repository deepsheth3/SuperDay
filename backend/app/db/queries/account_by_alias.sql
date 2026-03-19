-- :tenant_id uuid, :normalized_alias text
SELECT account_id
FROM account_aliases
WHERE tenant_id = :tenant_id
  AND normalized_alias_text = :normalized_alias
LIMIT 1;
