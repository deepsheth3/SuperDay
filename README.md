# Harper Agent

**Harper** is an AI agent that answers questions about insurance accounts using a **multi-index memory**: user queries are interpreted by an LLM helper, resolved against semantic indices (location, industry, status, person), and answered with grounded, cited summaries.

---

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file with your Gemini API key (required for entity extraction and answer summarization):

```
GEMINI_API_KEY=your_key_here
```

Run the web UI:

```bash
python app.py
```

Open **http://127.0.0.1:5050** and ask about accounts (e.g. *“What is the status of Evergreen Public Services in Austin CO?”*).

---

## Why this file structure: memory layout and indices

### Design principle: **indices by dimension, not by account**

We do **not** put one folder per account and search inside each. Instead we use a **multi-index** layout:

- **`memory/objects/`** – Canonical data: one folder per account (`acct_xxx`) and per person (`person_xxx`), each with `profile.json`, `status.json`, `full.json`, etc. This is the source of truth for “what is this account?”
- **`memory/indices/`** – Precomputed **dimensions** over that data. Each index is keyed by a *semantic dimension* (location, industry, status, person, etc.) and holds **lists of account IDs** that match that dimension.

Example layout:

```
memory/
├── objects/
│   ├── accounts/
│   │   ├── acct_1eaf057f87/    # Evergreen Public Services
│   │   │   ├── profile.json
│   │   │   ├── status.json
│   │   │   └── full.json
│   │   └── acct_93ccabc6fa/    # Harborline Hotel Group
│   │       └── ...
│   └── people/
│       └── person_xxx/
└── indices/
    ├── location/US/co/austin/accounts.json   # account_ids in Austin, CO
    ├── location/US/nc/chicago/accounts.json # account_ids in Chicago, NC
    ├── industry/public_sector/accounts.json
    ├── industry/hospitality/accounts.json
    ├── status/awaiting_documents/accounts.json
    ├── status/policy_bound/accounts.json
    └── person/lena_singh/accounts.json
```

Each index file is a small JSON like `{"account_ids": ["acct_1eaf057f87", ...]}`.

### Why indices matter

1. **Constraint-first retrieval** – The agent turns the user query into *constraints* (e.g. state=CO, industry=public_sector). We **intersect** the relevant index files (e.g. location CO + industry public_sector) to get candidate account IDs, then load full data only for those candidates. We never scan every account folder.
2. **Scalability** – Adding accounts means updating object blobs and appending to the right index files. Query cost depends on the number of *constraints*, not the number of accounts.
3. **Clear semantics** – “Accounts in Colorado” and “Public sector accounts” map directly to paths under `indices/location` and `indices/industry`. The layout reflects how we query.

So: **one folder per account under `objects/`** is for storage and full reads; **indices are the layer we query** so we don’t need a “folder per account” as the primary search structure.

---

## AI agent workflow

The pipeline is **deterministic orchestration** around two LLM calls (entity extraction and answer composition):

1. **Entity extraction (LLM helper)** – The user message and current session (e.g. “last focused account”) go to a **helper** LLM. It returns a structured **EntityFrame**: primary type (account/person/industry/location), hints (account name, person name), constraints (city, state, industry, status), and **anaphora** (e.g. “that” = current focus). No regex or query-specific rules; all interpretation is in the model.
2. **Index navigation** – Using the EntityFrame, we read the relevant index files (e.g. `indices/location/US/co/...`, `indices/industry/public_sector/accounts.json`), intersect the `account_ids` lists, and get candidate IDs. If the user referred to “that” and the helper set anaphora, we skip navigation and use the session’s focused account ID.
3. **Resolve** – We filter (or disambiguate) candidates by **account name** against object data (e.g. company name in `profile.json`).
4. **Evidence** – For the chosen account ID we load `profile`, `status`, and `full` (emails, calls, etc.) and build an **evidence bundle** (each item has a source path/id for citations).
5. **Answer composition (LLM)** – The evidence bundle and the user question go to a second LLM. It produces a short, **human-friendly summary** with inline citations (e.g. [1], [2], [3–9]). Citations are checked against the evidence bundle.
6. **Session update** – We append the turn to session history and set **active focus** to the resolved account so the next “from that company” or “what about that one?” uses the same account.

So: **one agent loop** = one helper call (entities) + optional one composer call (answer). The rest is index reads, set intersection, and object reads.

---

## LLM workflow (where the models are used)

| Step | Role | What the LLM does |
|------|------|-------------------|
| **Entity extraction** | Helper agent | Takes user query + session focus; outputs EntityFrame (account/person/industry/location, constraints, anaphora). Index keys (industry, status) are read from the filesystem and passed in the prompt so the model outputs valid slugs. |
| **Answer composition** | Summarizer | Takes evidence bundle + user question; outputs a brief narrative with citations. No query-specific logic; the model decides what to emphasize. |

Both use the **Gemini API** (`GEMINI_API_KEY` in `.env`). The agent is designed for **LLM-only** entity extraction (no spaCy or regex fallback).

---

## Configuration

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | **Required.** Used for entity extraction and answer summarization. A paid key is recommended to avoid rate limits. |
| `HARPER_MEMORY_ROOT` | Path to the `memory` directory (default: `memory`). |
| `PORT` | Web UI port (default: `5050`). |
| `REDIS_URL` | Optional. Redis connection URL (e.g. `redis://localhost:6379/0`) for the follow-up pipeline cache. When set, waiting-on-client account list, per-account follow-up state, and CDC cursor are cached with TTL for faster runs. |

---

## Follow-up and update pipeline (CDC)

The **follow-up agent** runs on a schedule (e.g. cron or APScheduler) and:

- **CDC consumer**: Processes `memory/event_store/events.jsonl`. On `communication_added` it resets follow-up state (e.g. `followup_count = 0`) so a new 3-day/6-day cycle can start. On `status_changed` it sends the client an immediate update email.
- **Follow-up job**: Sends at most two follow-ups per “waiting on client” cycle: first at **3 days** of inactivity, second at **6 days**, then stops until the next new communication resets the count.

Run the job once:

```bash
python run_followup_job.py
```

**Redis (optional):** Set `REDIS_URL` to cache the list of accounts waiting on client, per-account follow-up state, and the CDC read offset (all with TTL). This makes the pipeline faster when Redis is available.

**Emitting CDC events:** When you write or update account data (e.g. ingest from `harper_accounts.jsonl`), append events with `followup_agent.events.append_event("communication_added", account_id, payload)` or `append_event("status_changed", account_id, {"new_status": "..."})` so the consumer and update handler can react.

---

## Running the 20 sample queries

You can test the agent end-to-end using the 20 sample queries. From the project root (with `.env` and `GEMINI_API_KEY` set):

```bash
python run_20_queries.py
```

**What this does:**

1. **Starts the Flask app** in the background on http://127.0.0.1:5050.
2. **Opens your browser** to that URL with a unique session ID so the UI stays in sync.
3. **Sends all 20 queries one by one** to the API: each query is posted, then the script waits ~3 seconds for the answer to appear in the UI, then ~2 seconds before sending the next query.
4. **Leaves the server running** when done so you can keep chatting in the browser.

**Where to look:** Watch the **browser** (not the terminal). The terminal only prints short progress lines (e.g. `1/20 sent.`). The full conversation, answers, lists, and references appear in the chat UI.

**Session behavior:** All 20 queries run in **one session**, so session-aware questions (e.g. 7–11, 17, 19) correctly refer to the account from the previous turn (“that company”, “that account”, etc.).

---

## Test results (20 queries)

Below is the outcome of a full run with the LLM helper and summarizer enabled. “Session” queries use the same session; “that” refers to the last account returned (e.g. Harborline after query 6).

| # | Type | Query | Result |
|---|------|--------|--------|
| 1 | Specific | What is the status of Evergreen Public Services in Austin CO? | Evergreen; application_submitted; summary with citations. |
| 2 | Specific | Tell me about Harborline Hotel Group Inc. | Harborline; policy_bound; summary with citations. |
| 3 | Specific | Who is the contact for Skyline Protective Services in North Carolina? | No match (index/industry key mismatch). |
| 4 | Specific | What's the status of Summerside Child Care in Houston Pennsylvania? | Disambiguation: “Summerside Child Care LLC” vs “Summerside Child Care”. |
| 5 | Specific | Give me the status of Lone Star Child Care Center in Colorado. | Lone Star; contacted_by_harper; summary. |
| 6 | Specific | Tell me about Harborline Hotel Group in Austin Massachusetts. | Harborline; policy_bound; summary. |
| 7 | Session | From that company, who was the person of contact? | **Harborline** (session); Sam Samson as contact. |
| 8 | Session | What is the status of that one? | **Harborline**; policy bound. |
| 9 | Session | Who was the contact for that? | **Harborline**; Sam Samson. |
| 10 | Session | Tell me more about that account. | **Harborline**; bound policy, emails, Sam Samson. |
| 11 | Session | What happened with that application? | **Harborline**; bound, quote acceptances, bound confirmation. |
| 12 | List | Which accounts are in Colorado? | List: Evergreen (×2), Lone Star, Skyline Guard, Harbor Tech. |
| 13 | List | List all public sector accounts. | List: Evergreen (several variants), Evergreen Community, Municipal. |
| 14 | List | Which accounts are awaiting documents? | List of many accounts (awaiting_documents index). |
| 15 | List | Show me hospitality accounts that are policy bound. | Single match: Harborline; policy_bound summary. |
| 16 | List | Retail accounts which require documents. | List: Samford Retail, Riverstone Retail, Samford Market, Samford Retail LLC. |
| 17 | Vague | What happened to that childcare center in California? | **Session focus** (Harborline) – “that” = last account. |
| 18 | Vague | Hey, what's going on with the hotel group in Austin? | Harborline (hospitality + Austin). |
| 19 | Vague | Any updates on the public sector account we were looking at? | **Session focus** (Harborline). |
| 20 | Vague | What about the defense contractor in Chicago? | List: Skyline Protective Services LLC, Frontier Venture Partners Inc. |

**Summary:** Specific and list queries hit the right accounts and indices; session-aware queries (7–11, 17, 19) correctly use the last focused account. Memory, indexing, and session chat all behave as intended. The only failure in this set is query 3 (Skyline in NC), due to industry key vs index mismatch.

---

## Project structure

```
.
├── app.py                 # Web UI (Flask)
├── run_20_queries.py      # Run all 20 sample queries in one session
├── run_sample_queries.py  # Shorter sample set
├── run_ingest.py          # Ingest harper_accounts.jsonl -> memory + CDC events
├── run_followup_job.py    # Run follow-up & update pipeline once
├── harper_accounts.jsonl  # Source data (if you have it) for ingest
├── harper_agent/
│   ├── main.py            # Agent loop: extract → navigate → resolve → evidence → answer
│   ├── config.py          # MEMORY_ROOT, REDIS_URL
│   ├── models.py          # EntityFrame, SessionState, EvidenceBundle, etc.
│   ├── entity_extractor_third_party.py  # LLM helper (entity extraction)
│   ├── index_navigator.py # Read indices, intersect by constraints
│   ├── resolver.py        # Filter by account name
│   ├── evidence_bundler.py
│   ├── answer_composer.py # LLM summarization + citation
│   ├── citation_verifier.py
│   ├── session_manager.py
│   ├── tools.py           # object_get_account
│   └── normalize.py       # Slug/state helpers
├── followup_agent/        # CDC + follow-up + update pipeline
│   ├── __init__.py
│   ├── ingest.py          # Write accounts + indices + CDC events
│   ├── events.py          # Event log (events.jsonl, email_log.jsonl)
│   ├── state.py           # harper_followup_state.json read/write
│   ├── waiting.py         # Resolve 'waiting on client' accounts
│   ├── cache.py           # Optional Redis cache with TTL
│   ├── consumer.py        # CDC consumer (reset on comms, status updates)
│   ├── job.py             # Follow-up job (3-day / 6-day, max two)
│   └── update_handler.py  # Send client update emails on status change
├── memory/                # Populated by ingest (or preloaded)
│   ├── objects/accounts/
│   ├── objects/people/
│   ├── indices/location/
│   ├── indices/industry/
│   ├── indices/status/
│   ├── indices/person/
│   └── event_store/       # CDC event log (events.jsonl, email_log.jsonl)
├── tests/
│   └── test_followup_agent.py  # CDC + follow-up pipeline tests
└── README.md              # This file
```

---

## Ingest (optional)

The repo includes **`harper_accounts.jsonl`** (70 sample accounts) so you can populate `memory/` and run the agent. If you have an ingest script, point it at this file to build `memory/objects/` and `memory/indices/`. If `memory/` is already populated, you can skip ingest and run the UI and `run_20_queries.py` as above.

---

## Pushing to Git

The repo is set up with `.gitignore` (e.g. `.env`, `.venv/`, `memory/`). To push to a remote:

```bash
git remote add origin https://github.com/YOUR_USER/SuperDay.git   # or your Git URL
git push -u origin main
```

To version the `memory/` layout (without large data), you can remove `memory/` from `.gitignore` and add a small `memory/README.md` that describes the structure; keep `harper_accounts.jsonl` ignored if it is large.
