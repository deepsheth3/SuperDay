-- Optional native partitioning rollout (run AFTER renaming tables or on greenfield).
-- v1 ships non-partitioned in 001_schema.sql; use this when row counts justify it.
--
-- Example: partition communications by month on occurred_at
/*
ALTER TABLE communications RENAME TO communications_old;
CREATE TABLE communications (
  LIKE communications_old INCLUDING ALL
) PARTITION BY RANGE (occurred_at);
-- Re-import data, swap names, etc.
*/

-- Create child partitions for the next N months (template — adjust parent name).
CREATE OR REPLACE FUNCTION create_communications_partitions_ahead(n_months int DEFAULT 3)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  m int := 0;
  start_d date;
  end_d date;
  part_name text;
BEGIN
  FOR m IN 0..n_months LOOP
    start_d := (date_trunc('month', CURRENT_DATE::timestamp) + (m * interval '1 month'))::date;
    end_d := (start_d + interval '1 month')::date;
    part_name := 'communications_' || to_char(start_d, 'YYYY_MM');
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS %I PARTITION OF communications FOR VALUES FROM (%L) TO (%L)',
      part_name, start_d, end_d
    );
  END LOOP;
END;
$$;

-- Schedule monthly (e.g. Cloud Scheduler -> SQL or migration job):
-- SELECT create_communications_partitions_ahead(3);
