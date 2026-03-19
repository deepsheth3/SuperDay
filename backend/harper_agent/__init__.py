"""
Harper reactive agent: MemGPT-style loop and tools.

Data under `HARPER_MEMORY_ROOT` (default repo `memory/`):
- **Domain memory:** `objects/`, `indices/` (resolver, archival, evidence).
- **Agent runtime state:** `sessions/`, `transcripts/` (conversation + replay).

Not the ingest pipeline (`backend/.data/pipeline`) or the async follow-up worker.
"""
