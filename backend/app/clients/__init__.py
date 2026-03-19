"""
External clients (boilerplate — see docs/CLOUD_SETUP.md):

- gcp_pubsub — publish IngestEventV1 to Pub/Sub
- gcp_vertex_vector — Vertex embeddings + Vector Search upsert stub
- aws_s3 — raw JSON payloads (see s3_key_layout + docs/S3_KEY_LAYOUT.md)
- aws_opensearch — lexical chunk index
- embedding — orchestrates local + optional cloud paths
"""
