# Follow-up agent (proactive outbound)

Separate from the **reactive chat agent** (`harper_agent`): this capability **finds conversations waiting on the client** and **sends or drafts follow-ups** under policy.

## Boundaries

| Reactive chat | Follow-up agent |
|---------------|-----------------|
| Triggered by user message in session | Triggered by **schedule** (cron) or **manual run** |
| Reads memory / indices | Reads **DB**: threads, communications, SLA fields |
| Reply in UI | **Outbound** email/SMS + audit row |

## Event shape

Use **`FollowupRunJobV1`** in [`app/schemas/queue.py`](../app/schemas/queue.py):

- `run_id`, `tenant_id`, `as_of`, `max_accounts`, `policy_version`, optional `trace_id`.

## Plumbing (already in repo)

- **Local bus topic:** `followup.run` — consumer stub in [`app/workers/pipeline_workers.py`](../app/workers/pipeline_workers.py) (`_followup_worker`).
- **GCP Pub/Sub (reference):** topic `followup-run` in [`infra/pubsub.yaml`](../infra/pubsub.yaml).

## Implementation checklist

1. **Data model** — Explicit state on `threads` or `communications` (e.g. `awaiting_client_reply_since`, `next_followup_at`, `followup_attempts`). Align with `001_schema.sql` or add a migration.
2. **Selector** — Query candidates for `tenant_id` with `as_of` and limits; respect legal hold / opt-out.
3. **Policy** — Max attempts, quiet hours, channel preference, templates vs LLM draft.
4. **Idempotency** — `(tenant_id, thread_id, run_id, attempt_no)` or outbound `request_id` so Pub/Sub retries do not double-send.
5. **Side effects** — Send via SendGrid/Twilio/etc.; write `communications` row + timeline entry.
6. **Scheduler** — Cloud Scheduler → HTTP `POST /api/followup/run` or publish to `followup-run` topic (add route when ready).

## Suggested module layout (future)

```
backend/app/followup/
  selector.py      # DB queries
  policy.py        # rules
  outbound.py      # email/SMS adapters
  run_once.py      # orchestration for one FollowupRunJobV1
```

Keep this **out of** `harper_agent/` to avoid mixing reactive tool loops with batch outbound jobs.
