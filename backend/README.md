# Harper Chat Service (production LLD artifacts)

Executable artifacts derived from the Cursor plan **Production Workflow Design: FRD + NFR + APIs + HLD**.

- **Plan (source of truth for prose):** `.cursor/plans/production_workflow_design_frd_+_nfr_+_apis_+_hld_3b149694.plan.md`
- **This tree:** SQL DDL, OpenAPI, Pydantic, FastAPI skeleton, Alembic plan, diagrams, worker contracts, infra stubs, runbooks.

## Layout (executable artifacts 1–12)

| # | Path | Purpose |
|---|------|---------|
| 1 | `sql/001_schema.sql` | Full DDL + FKs + partial indexes |
| 1b | `sql/maintenance/create_partitions.sql` | Partition helper + next-N-months function |
| 1c | `sql/seed_tenant_features.sql` | Seed for feature flags migration |
| 2 | `alembic/README_MIGRATION_PLAN.md` | Migration order (initial / partition / indexes / seed) |
| 3 | `specs/openapi.yaml` | OpenAPI 3.1 (chat, ingest, rehydration, errors, `request_id`, disambiguation) |
| 4 | `app/schemas/` | Pydantic: API, queue (`IngestEventV1`…), DTOs, `ErrorResponse` |
| 5 | `diagrams/sequences.md` | Mermaid: chat, normalize, embed+index, replay, correction, archiver, rehydration |
| 6 | `docs/worker_contracts.md` | Handler specs: idempotency, txn, metrics, retry, DLQ |
| 6b | `docs/S3_KEY_LAYOUT.md` | Tenant-scoped S3 key conventions (blobs / archive) |
| 7 | `app/` | FastAPI skeleton: `api/`, `core/`, `db/`, `models/`, `schemas/`, `services/`, `workers/`, `clients/`, `repositories/`, `observability/` |
| 8 | `app/models/core.py` + `app/repositories/` | SQLAlchemy hot-path models + repository stubs |
| 9 | `app/db/queries/*.sql` | Concrete SQL for resolver, activity, candidates, failed embed, replay, transcript |
| 10 | `app/services/feature_resolution.py` + `app/core/settings.py` | Feature flags: precedence, cache TTL, invalidation hook |
| 11 | `infra/` | `cloudrun-chat.yaml`, `cloudrun-workers.yaml`, `pubsub.yaml` |
| 12 | `runbooks/*.md` | Replay, reindex, lexical cutover, DR, degraded mode, DLQ |
| — | `harper_agent/` | **Runtime agent** (MemGPT loop, tools, indices, sessions). Uses repo-level `../memory/` (set `HARPER_MEMORY_ROOT` if needed). |

**Plan updates** (timeouts, chat idempotency, lexical ownership, risks, etc.) are in `.cursor/plans/production_workflow_design_frd_+_nfr_+_apis_+_hld_3b149694.plan.md`.

## Run (dev)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### What to change for cloud + database

1. **Copy env template:** [`.env.example`](.env.example) → repo root `.env` (or `.env` here). Fill in only what you use.
2. **Optional cloud SDKs:** `pip install -r requirements-cloud.txt`
3. **Full checklist:** **[`docs/CLOUD_SETUP.md`](docs/CLOUD_SETUP.md)** (GCP Pub/Sub, Vertex, S3, OpenSearch, AlloyDB URL, what is TODO vs implemented).
4. **DB bootstrap:** [`sql/bootstrap/README.md`](sql/bootstrap/README.md) — apply `001_schema.sql`, then `minimal_tenant.sql`.
5. **Test ingest:** `python scripts/ingest_smoketest.py` (API must be running).

| If you are wiring… | Set / edit |
|--------------------|------------|
| Postgres / AlloyDB | `HARPER_DATABASE_URL` or `DATABASE_URL` |
| Pub/Sub ingest fan-out | `HARPER_GCP_PROJECT_ID`, `HARPER_PUBSUB_PUBLISH_INGEST=true`, topic id, `GOOGLE_APPLICATION_CREDENTIALS` (local) |
| S3 raw bodies | `HARPER_S3_RAW_BUCKET`, `HARPER_AWS_REGION`, IAM |
| OpenSearch lexical | `HARPER_ENABLE_OPENSEARCH_INDEX`, `HARPER_OPENSEARCH_HOST`, `HARPER_OPENSEARCH_SERVICE` (`es` or `aoss`) |
| Vertex embeddings | `HARPER_GCP_PROJECT_ID`, `HARPER_GCP_REGION` (uses `vertexai` in code) |
| Vector Search upsert | Implement body of `upsert_vector_datapoint` in [`app/clients/gcp_vertex_vector.py`](app/clients/gcp_vertex_vector.py) |

Set `HARPER_DATABASE_URL` / `DATABASE_URL` for SQLAlchemy when exercising repositories (optional for local chat only).

### Ingest → normalize → embed (implemented)

- **Background workers** start with the API by default (`HARPER_START_BACKGROUND_WORKERS=true`).
- **State** is stored under `HARPER_PIPELINE_DATA_DIR` (default: `backend/.data/pipeline/`).
- **POST** `/api/ingest/email` | `/ingest/text` | `/ingest/call_transcript` | `/ingest/batch` — returns `event_id`; same `(tenant, source_system, source_event_id)` returns `idempotent_replay: true`.
- **GET** `/api/pipeline/events/{event_id}` — envelope + stage.
- **POST** `/api/rehydration/request` — queues `RehydrationJobV1`; **GET** `/api/pipeline/jobs/rehydration/{job_id}`.
- **Workers-only process:** `cd backend && python -m app.workers.pipeline_workers` (blocks; for split deploy later).
- **Follow-up agent (future):** [`docs/FOLLOWUP_AGENT.md`](docs/FOLLOWUP_AGENT.md), schema `FollowupRunJobV1`, topic `followup.run` / Pub/Sub `followup-run`.

Cloud hooks live in `app/clients/` (`gcp_pubsub`, `aws_s3`, `aws_opensearch`, `gcp_vertex_vector`); `embedding.py` calls them when the env flags above are set.
