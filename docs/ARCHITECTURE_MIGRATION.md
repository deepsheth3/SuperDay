# Harper Chat Service (single stack)

There is **one** backend: **[`backend/`](../backend/)** — FastAPI HTTP API plus the **`harper_agent`** package (MemGPT-style bot, file-backed sessions and transcripts).

- **Your data** lives under **`memory/`** at the **repository root** (gitignored by default). It is **not** removed by this layout; set `HARPER_MEMORY_ROOT` to an absolute path if you run uvicorn from elsewhere.
- **Legacy Flask `app.py`** has been removed; use uvicorn only.

## Run API + UI

```bash
# Repo root: .env with GEMINI_API_KEY
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8080
```

## Tests

From repo root (path fixed in `tests/conftest.py`):

```bash
pip install -r requirements.txt
pytest tests/
```

## Next (production LLD)

AlloyDB transcripts, Pub/Sub workers, hybrid retrieval, DB idempotency, and the **follow-up agent** ([`backend/docs/FOLLOWUP_AGENT.md`](../backend/docs/FOLLOWUP_AGENT.md)) — see the Cursor plan and `backend/docs/worker_contracts.md`.
