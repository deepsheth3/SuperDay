# Clear stuck DLQ batch

1. Identify DLQ subscription (normalize/embed/archive/reindex/rehydration).
2. Export messages to GCS or local JSON for audit.
3. Fix root cause (schema, bad tenant, poison `source_event_id`).
4. For safe messages: republish to primary topic with same payload.
5. For poison: mark `ingestion_events` as terminal failure and **do not** auto-retry.
