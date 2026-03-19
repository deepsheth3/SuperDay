-- One pilot tenant for local/staging. Replace name/uuid as needed.
-- Run after 001_schema.sql

INSERT INTO tenants (tenant_id, name, status, retention_months_hot, retention_policy_json, legal_hold_default, allowed_source_types)
VALUES (
  '550e8400-e29b-41d4-a716-446655440000'::uuid,
  'Pilot Tenant',
  'active',
  24,
  '{}'::jsonb,
  false,
  ARRAY['email', 'sms', 'call_transcript']::text[]
)
ON CONFLICT (tenant_id) DO NOTHING;
