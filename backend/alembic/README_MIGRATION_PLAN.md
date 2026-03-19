# Alembic migration plan

Run from `backend/` after `alembic init` (one-time).

## Revision order

| Step | Revision id (suggested) | Description |
|------|-------------------------|-------------|
| 1 | `0001_initial_schema` | Baseline: all tables + FKs + indexes from `sql/001_schema.sql` (prefer `alembic revision --autogenerate` from SQLAlchemy models, then diff to SQL file). |
| 2 | `0002_partition_prereq` | Optional: BRIN indexes on `occurred_at` / `received_at` if not in 0001. |
| 3 | `0003_partition_functions` | Install `sql/maintenance/create_partitions.sql` functions (no table rewrites). |
| 4 | `0004_seed_tenant_features` | Insert default `tenant_features` rows per env (e.g. `hybrid_retrieval=false` for pilot). |

## Commands

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/harper
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

## Notes

- Forward-only migrations; use expand/contract for zero-downtime column changes.
- Keep `sql/001_schema.sql` as human-readable source; Alembic is the applied history.
