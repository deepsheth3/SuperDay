# GCP + AWS + database setup (what to change)

This service can run **fully local** (file pipeline + optional local Postgres) or **wired to cloud**. Edit the values below in **your** environment — do not commit secrets.

## 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
# When connecting to GCP/AWS:
pip install -r requirements-cloud.txt
```

## 2. Environment file

1. Copy **[`../.env.example`](.env.example)** to the **repo root** `.env` (loaded by `app/main.py`) **or** `backend/.env`.
2. Fill in only the sections you use. Unused variables can stay commented.

---

## 3. Database (AlloyDB / Cloud SQL / Postgres)

| You change | Purpose |
|------------|---------|
| `HARPER_DATABASE_URL` or `DATABASE_URL` | Async SQLAlchemy URL for `asyncpg`. Example: `postgresql+asyncpg://USER:PASS@HOST:5432/harper` |
| SSL | AlloyDB/private IP: often `sslmode=require` via [AlloyDB Auth Proxy](https://cloud.google.com/alloydb/docs/auth-proxy/connect) or connector — adjust URL/host per Google’s doc |
| Schema | Apply **[`sql/001_schema.sql`](../sql/001_schema.sql)** to the database (psql, Cloud Console, or Alembic once revisions exist) |
| Seed | Run **[`sql/bootstrap/minimal_tenant.sql`](../sql/bootstrap/minimal_tenant.sql)** then replace UUIDs with your tenant; optional **[`sql/seed_tenant_features.sql`](../sql/seed_tenant_features.sql)** |

**Boilerplate code:** [`app/db/session.py`](../app/db/session.py) uses `DATABASE_URL` or `HARPER_DATABASE_URL`. Repositories under `app/repositories/` expect tables from `001_schema.sql`.

---

## 4. Google Cloud (Pub/Sub + Vertex)

### Pub/Sub (ingest fan-out to normalize workers)

| You change | Purpose |
|------------|---------|
| `HARPER_GCP_PROJECT_ID` | GCP project id |
| `HARPER_PUBSUB_PUBLISH_INGEST=true` | After each HTTP ingest, also publish `IngestEventV1` JSON to Pub/Sub |
| `HARPER_PUBSUB_INGEST_TOPIC_ID` | Topic **id** (default `ingest-accepted`); must match [`infra/pubsub.yaml`](../infra/pubsub.yaml) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to SA JSON **local dev only** |
| `PUBSUB_EMULATOR_HOST` | e.g. `127.0.0.1:8085` when using the Pub/Sub emulator |

**Boilerplate code:** [`app/clients/gcp_pubsub.py`](../app/clients/gcp_pubsub.py)  
**Wiring:** [`app/services/pipeline/ingest_accept.py`](../app/services/pipeline/ingest_accept.py) calls publish when `HARPER_PUBSUB_PUBLISH_INGEST` is true.

### Vertex AI (embeddings + Vector Search)

| You change | Purpose |
|------------|---------|
| `HARPER_ENABLE_VERTEX_VECTOR_UPSERT` | Set `true` when your Matching Engine upsert is implemented |
| `HARPER_VERTEX_INDEX_ENDPOINT_ID` / `HARPER_VERTEX_INDEX_ID` | Your Vector Search resource identifiers |
| `HARPER_VERTEX_EMBEDDING_MODEL` | e.g. `textembedding-gecko@003` |
| `HARPER_GCP_PROJECT_ID` / implied region via `HARPER_GCP_REGION` | Used by `vertexai.init` |

**Boilerplate code:** [`app/clients/gcp_vertex_vector.py`](../app/clients/gcp_vertex_vector.py)  
- `embed_text_vertex()` is implemented with **`vertexai.language_models.TextEmbeddingModel`**.  
- `upsert_vector_datapoint()` is a **TODO**: replace the log stub with your index endpoint API (REST/gRPC) per [Vector Search update docs](https://cloud.google.com/vertex-ai/docs/vector-search/update-index).

---

## 5. AWS (S3 raw storage + OpenSearch)

### S3 (structured object storage — not primary DB)

| You change | Purpose |
|------------|---------|
| `HARPER_S3_RAW_BUCKET` | Bucket for blobs (raw ingest, future attachments/exports) |
| `HARPER_S3_RAW_PREFIX` | Optional **root** inside the bucket (e.g. `prod`). Canonical keys still start with `tenants/{uuid}/...` — see **[`S3_KEY_LAYOUT.md`](S3_KEY_LAYOUT.md)** |
| `HARPER_AWS_REGION` | Region for SigV4 + S3 client |
| IAM | Grant `s3:PutObject` / `s3:GetObject` on that bucket (task role on ECS/EKS, or keys locally) |

**Behavior:** If `HARPER_S3_RAW_BUCKET` is set and the ingest API includes `raw_body_text`, the API **uploads** JSON using the **`raw/ingest/.../payload.json`** layout and sets `raw_s3_key` on `IngestEventV1` to `s3://...`.

**Boilerplate code:** [`app/clients/aws_s3.py`](../app/clients/aws_s3.py), [`app/clients/s3_key_layout.py`](../app/clients/s3_key_layout.py)

### OpenSearch (lexical index)

| You change | Purpose |
|------------|---------|
| `HARPER_ENABLE_OPENSEARCH_INDEX=true` | Turn on upserts from the embed worker |
| `HARPER_OPENSEARCH_HOST` | Domain hostname (no `https://`) |
| `HARPER_OPENSEARCH_SERVICE` | `es` (managed) or `aoss` (OpenSearch Serverless) |
| `HARPER_OPENSEARCH_INDEX_NAME` | Target index (create index mapping in AWS console or separate IaC) |
| `HARPER_AWS_REGION` | For SigV4 |

**Boilerplate code:** [`app/clients/aws_opensearch.py`](../app/clients/aws_opensearch.py)

---

## 6. Ingest test data

After the API is running:

```bash
cd backend
python scripts/ingest_smoketest.py
```

Or `curl` `POST /api/ingest/email` with JSON body (see script).  
Use a real `tenant_id` UUID that exists in your `tenants` table when DB-backed constraints are enforced.

---

## 7. What you must implement vs included

| Included | You still customize |
|----------|---------------------|
| Pub/Sub JSON publish | IAM, topic creation, Cloud Run worker subscribers |
| S3 put/get | Bucket policy, KMS, VPC endpoints if private |
| OpenSearch `index()` | Index mapping, ILM, fine-grained IAM |
| Vertex **embedding** call | Model name / quota |
| Vector Search **upsert** | Full datapoint payload + endpoint id in `gcp_vertex_vector.py` |
| AlloyDB | Connection string, migrations, backups |

---

## 8. Infra YAML (reference only)

[`infra/pubsub.yaml`](../infra/pubsub.yaml) and [`infra/cloudrun-*.yaml`](../infra/) describe names and deadlines — apply with your IaC (Terraform, gcloud, etc.); they are **not** auto-applied by this repo.
