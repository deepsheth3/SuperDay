# S3 key layout (structured object storage)

S3 holds **blobs and archives** — not the online source of truth for queries (that stays in **Postgres** + **vector index**). This doc defines a **tenant-scoped, predictable** key hierarchy so ingest, IAM, lifecycle rules, and debugging stay sane.

## Prefix

- **`HARPER_S3_RAW_BUCKET`** — bucket name.
- **`HARPER_S3_RAW_PREFIX`** — optional **root** inside the bucket (e.g. `prod`, `staging/harper`). Do **not** repeat `tenants/` here; the layout below already starts with `tenants/{tenant_id}/`.

Full key:

```text
{s3_raw_prefix}/tenants/{tenant_id}/...
```

If `s3_raw_prefix` is empty, keys start at `tenants/...`.

## Canonical paths (v1)

| Kind | Pattern | Notes |
|------|---------|--------|
| **Raw ingest payload** | `tenants/{tenant}/raw/ingest/{source_system}/{source_event_id}/payload.json` | Default upload from HTTP ingest when `raw_body_text` is present. |
| **Communication body** | `tenants/{tenant}/communications/{communication_id}/body.json` | Optional; link from DB row. |
| **Attachment** | `tenants/{tenant}/communications/{communication_id}/attachments/{attachment_id}/{filename}` | Sanitized filename segment. |
| **Archive export** | `tenants/{tenant}/archive/exports/{period}/{export_id}.jsonl` | Batch / compliance exports. |

`tenant_id` is normalized to lowercase UUID string when valid; otherwise segments are sanitized (alphanumeric + `._-`).

## Code

Builders live in [`app/clients/s3_key_layout.py`](../app/clients/s3_key_layout.py). **`put_raw_json`** in [`app/clients/aws_s3.py`](../app/clients/aws_s3.py) uses **`raw_ingest_payload_key`** + **`join_with_prefix`**.

## Legacy note

Earlier experimental keys used `{prefix}{tenant}/{source_system}/{event_id}` without `raw/ingest/...`. New ingests use the table above; migrate or re-ingest if you depended on the old shape.

## IAM and lifecycle (ops)

- Prefer IAM conditions on **`s3:prefix`** = `tenants/{tenant_id}/*` per tenant SA where needed.
- S3 lifecycle rules can target `tenants/*/archive/**` separately from `raw/ingest/**`.
