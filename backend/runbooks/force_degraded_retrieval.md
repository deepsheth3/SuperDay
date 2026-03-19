# Force degraded retrieval mode

1. Set tenant feature `hybrid_retrieval=false` or global env `RETRIEVAL_MODE=metadata_only` (implement in orchestrator).
2. Alternatively block OpenSearch security group / set `LEXICAL_SEARCH_TIMEOUT_MS=1` for emergency kill-switch.
3. Monitor `degradation_mode` on `chat_turns` and user-visible `freshness_notice`.
4. Restore: revert flag, warm cache, validate lexical health.
