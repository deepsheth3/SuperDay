# Fail over to DR (GCP active-passive)

1. Confirm primary region incident.
2. Promote read replica / failover AlloyDB in DR region (provider-specific).
3. Update Cloud Run env `DATABASE_URL` + `REDIS_URL` to DR endpoints.
4. Redeploy or traffic switch via load balancer / DNS.
5. Verify OpenSearch/Vertex endpoints still reachable from DR (cross-cloud paths).
6. Post-incident: fail back using runbook addendum.
