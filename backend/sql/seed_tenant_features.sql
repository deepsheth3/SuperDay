-- Example seed for Alembic migration `0004_seed_tenant_features`
-- Replace tenant_id with a real pilot tenant.

INSERT INTO tenant_features (tenant_id, feature_name, enabled, config_json, effective_from, effective_to)
VALUES
  ('00000000-0000-0000-0000-000000000001'::uuid, 'hybrid_retrieval', false, '{}', now(), NULL),
  ('00000000-0000-0000-0000-000000000001'::uuid, 'reranker_enabled', false, '{}', now(), NULL)
ON CONFLICT DO NOTHING;
