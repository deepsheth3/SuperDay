# Bootstrap database objects

1. Create an empty database (e.g. `harper`) and a user with DDL rights.
2. Apply the full schema:

   ```bash
   psql "postgresql://USER:PASS@HOST:5432/harper" -f ../001_schema.sql
   ```

3. Insert at least one tenant (required for FKs when you use ORM paths):

   ```bash
   psql "..." -f minimal_tenant.sql
   ```

4. Edit UUIDs in `minimal_tenant.sql` / `../seed_tenant_features.sql` to match your pilot tenant.

5. Point the app at the DB:

   ```bash
   export HARPER_DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST:5432/harper
   ```
