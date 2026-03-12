# Harper Agent

**Harper** is an AI agent that answers questions about insurance accounts using a **multi-index memory**: user queries are interpreted by an LLM helper, resolved against semantic indices (location, industry, status, person), and answered with grounded, cited summaries.

---

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file with your Gemini API key (required for the agent LLM and answer composition):

```
GEMINI_API_KEY=your_key_here
```

Run the **API** (Flask) and the **frontend** (Next.js) separately:

**Terminal 1 – API**
```bash
python app.py
```
Runs the Harper API on **http://127.0.0.1:5050**. `GET /` redirects to the frontend.

**Terminal 2 – Frontend**
```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```
Runs the Next.js chat UI on **http://localhost:3000**. Open this URL to chat. Set `FRONTEND_URL=http://localhost:3000` in root `.env` if needed for CORS.


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

The agent uses a **MemGPT-style agentic loop**: the LLM controls the flow and calls **tools** (recall search, archival search, working context edit, compose answer) instead of a fixed pipeline.

1. **Main context** – System instructions, working context (LLM-editable facts), and a FIFO of recent messages. A **queue manager** enforces a token budget: memory-pressure warning when near full, eviction of oldest messages to **recall storage** with a recursive summary when over.
2. **LLM** – Receives the main context and returns either a **message to the user** or a **function call** (e.g. `recall_storage.search`, `archival_storage.search`, `working_context.append`, `compose_answer`).
3. **Function executor** – Runs the requested tool, appends the result to context, and can **chain** (heartbeat) for another LLM call before yielding.
4. **Recall storage** – Persistent conversation history; the LLM can search it via a tool.
5. **Archival storage** – Indices + account objects; the LLM searches by constraints or gets evidence for an account via tools. Under the hood: index navigation, resolve, evidence bundling, and answer composition are reused as building blocks.
6. **Session update** – Each turn is appended to the FIFO and written to recall; working context is updated if the LLM used append/replace tools.

---

## Agent tools

The LLM calls these tools during the agentic loop. All are implemented in `harper_agent/function_executor.py`.

| Tool | What it does |
|------|----------------|
| **recall_storage.search** | Search this session’s past conversation (transcript). Optional `query` (keyword filter); `page` and `limit` for pagination. Use when the user refers to something said earlier (e.g. “that account we discussed”). |
| **archival_storage.search** | Search account/business memory (indices + objects) by filters: `query`, `state`, `industry`, `status`, `city`, `account_name`, `person_name`. Returns paginated one-line summaries (account_id, name, status, location). Use for “accounts in Texas”, “list hospitality accounts”, or to find an account by name. |
| **archival_storage.get_evidence** | Load the full evidence bundle for **one** account. Accepts `account_id` (an `acct_*` ID or an account name; names are resolved to IDs). `scope`: `full`, `status_only`, `contact_only`, `recent_activity`, or `minimal`. Use before answering detailed questions about a specific account (calls, emails, status). Updates session’s current account for follow-ups. |
| **working_context.append** | Append a fact or note to the agent’s working context (e.g. “Current account: acct_xyz”). Capped by config; overflow is trimmed from the start. |
| **working_context.replace** | Replace the first occurrence of a substring in working context with new text (e.g. update the current account). Same cap as append. |
| **working_context.get** | Read the current working context. Use to see what the agent has stored before deciding the next tool call. |
| **compose_answer** | Turn evidence into a short, grounded narrative. Requires `account_id` (ID or name) and `query` (the user’s question). Optionally `scope` and `session_goal`. Loads evidence, runs the answer-composer LLM, returns the narrative. Updates session’s current account. Use when the user asks something about a specific account and you have or can resolve the account_id. |
| **send_message** | Send the final reply to the user. The agent calls this with `message` (the reply text) and `request_heartbeat: false` when done. |

**Notes:** `account_id` in **get_evidence** and **compose_answer** can be an `acct_*` ID or a company name (e.g. “Harbor Tech Labs”); the system resolves names to IDs. After get_evidence or compose_answer, the session’s “current account” is updated so follow-ups like “summarize the calls for me” can use that account without the user repeating the name.

---

## LLM workflow (where the models are used)

| Step | Role | What the LLM does |
|------|------|-------------------|
| **Agent loop** | Controller | Receives main context (system + working context + FIFO); decides whether to call a tool (recall search, archival search, working context edit, compose answer) or to send a final message to the user. Can chain multiple tool calls (heartbeat) before responding. |
| **Answer composition** | Tool | When the LLM calls `compose_answer`, the evidence bundle and user question go to a separate LLM call that produces a brief narrative with citations. |

Both use the **Gemini API** (`GEMINI_API_KEY` in `.env`).

---

## Configuration

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | **Required.** Used for the agent LLM and answer composition. A paid key is recommended to avoid rate limits. |
| `HARPER_MEMORY_ROOT` | Path to the `memory` directory (default: `memory`). |
| `PORT` | API port (default: `5050`). |
| `FRONTEND_URL` | Origin of the Next.js frontend for CORS and redirects (default: `http://localhost:3000`). |

---

## Session goals

POST `/api/chat` accepts an optional `goal` in the JSON body. Allowed values: `reviewing_one_account`, `triaging_pipeline`, `checking_follow_ups`, `preparing_outreach`. If valid, the session goal is updated and can bias answer composition and tool use.

---

## Running the 20 sample queries

You can test the agent end-to-end using the 20 sample queries. From the project root (with `.env` and `GEMINI_API_KEY` set):

```bash
python run_20_queries.py
```

**What this does:**

1. **Starts the Flask app** in the background on http://127.0.0.1:5050.
2. **Opens your browser** to that URL (or open the Next.js frontend at http://localhost:3000 if it’s running) with a unique session ID so the UI stays in sync.
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
├── app.py                 # Harper API (Flask); GET / redirects to frontend
├── frontend/              # Next.js chat UI (TypeScript, Tailwind, App Router)
│   ├── src/app/           # Chat page, layout, globals
│   └── src/lib/api.ts     # getHistory, sendMessage, types
├── run_20_queries.py      # Run all 20 sample queries in one session
├── run_sample_queries.py  # Shorter sample set
├── harper_agent/
│   ├── main.py            # Entry: run_agent_loop → agentic loop
│   ├── agent_loop.py      # MemGPT-style loop: queue manager, LLM, function executor
│   ├── agent_prompts.py   # System prompt + tool schemas
│   ├── function_executor.py # Parse LLM output, run tools (recall, archival, working context, compose)
│   ├── queue_manager.py   # Token budget, memory pressure, eviction to recall
│   ├── archival_storage.py # Archival search + get_evidence (indices + objects)
│   ├── transcript_service.py # Recall storage: persist, search
│   ├── session_manager.py # Session state, working context, FIFO
│   ├── session_store.py   # Durable session persistence (file-based)
│   ├── config.py          # MEMORY_ROOT
│   ├── models.py          # EntityFrame, SessionState, EvidenceBundle, etc.
│   ├── index_navigator.py # Read indices, intersect by constraints
│   ├── resolver.py        # Filter by account name
│   ├── evidence_bundler.py
│   ├── answer_composer.py # LLM summarization + citations
│   ├── tools.py           # object_get_account
│   ├── messages.py        # User-facing message constants
│   ├── constants.py       # Intents, goals, evidence scopes, status semantics
│   └── normalize.py       # Slug/state helpers
├── memory/                # Populated by ingest or preloaded
│   ├── objects/accounts/
│   ├── objects/people/
│   └── indices/           # location, industry, status, person
├── tests/
│   ├── test_memgpt_tools.py
│   ├── test_constants_no_hardcoded.py
│   ├── test_session_goals.py
│   ├── test_smart_session.py
│   └── test_new_intents_confidence.py
└── README.md
```

---

## Ingest (optional)

If you have source data (e.g. `harper_accounts.jsonl`), you can populate `memory/objects/` and `memory/indices/` with an ingest script. If `memory/` is already populated, run the frontend and API as in Quick start and use `run_20_queries.py` to test.

---

## Pushing to Git

The repo is set up with `.gitignore` (e.g. `.env`, `.venv/`, `memory/`). To push to a remote:

```bash
git remote add origin https://github.com/YOUR_USER/SuperDay.git   # or your Git URL
git push -u origin main
```

To version the `memory/` layout (without large data), you can remove `memory/` from `.gitignore` and add a small `memory/README.md` that describes the structure; keep `harper_accounts.jsonl` ignored if it is large.
