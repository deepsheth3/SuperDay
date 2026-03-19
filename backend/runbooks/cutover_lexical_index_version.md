# Cut over lexical (OpenSearch) index version

1. Build new index with `lexical_index_version` in settings (e.g. `harper_lexical_v2`).
2. Run reindex job for pilot tenant (see `reindex_one_tenant.md`).
3. Validate search quality on canary queries.
4. Swap alias in OpenSearch (`lexical_current` → new index).
5. Deprecate old index after retention window.
