from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_CHAT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HARPER_", extra="ignore")

    # --- Core ---
    database_url: str = "postgresql+asyncpg://localhost/harper"
    redis_url: str | None = None
    feature_cache_ttl_seconds: int = 45
    pipeline_data_dir: Path = Field(default=_CHAT_ROOT / ".data" / "pipeline")
    start_background_workers: bool = True
    embedding_model: str = "text-embedding-004"
    embedding_version: str = "v1-local"

    # --- GCP ---
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"
    """Also publish accepted ingests to Cloud Pub/Sub (normalize workers in GCP pull this)."""
    pubsub_publish_ingest: bool = False
    pubsub_ingest_topic_id: str = "ingest-accepted"

    enable_vertex_vector_upsert: bool = False
    vertex_index_endpoint_id: str = ""
    vertex_index_id: str = ""
    vertex_embedding_model: str = "textembedding-gecko@003"

    # --- AWS ---
    aws_region: str = ""
    s3_raw_bucket: str = ""
    s3_raw_prefix: str = Field(
        default="",
        description="Optional root inside the bucket (e.g. prod). Canonical keys still start with tenants/{uuid}/...",
    )

    enable_opensearch_index: bool = False
    opensearch_host: str = ""
    opensearch_port: int = 443
    opensearch_use_ssl: bool = True
    """IAM SigV4 service name: `es` (managed OpenSearch) or `aoss` (OpenSearch Serverless)."""
    opensearch_service: str = "es"
    opensearch_index_name: str = "harper-chunks"

    # --- Auth (JWT Bearer + JWKS; Auth0 / Cognito / Keycloak compatible) ---
    """If set, `/api/*` routes require `Authorization: Bearer` validated against this JWKS URL."""
    jwt_jwks_url: str = ""
    jwt_audience: str | None = None
    jwt_issuer: str | None = None
    jwt_algorithms: str = "RS256"
    """JWT claim name for tenant id (e.g. `tenant_id` or namespaced `https://harper/tenant_id`)."""
    jwt_tenant_claim: str = "tenant_id"

    # --- Webhooks (HMAC ingestion) ---
    webhook_hmac_secret: str = ""

    # --- Rate limiting (in-process sliding window; 0 = off) ---
    rate_limit_rpm: int = 0

    # --- Logging ---
    """When true, scrub Authorization / webhook secrets from log `msg` / `args` (best-effort)."""
    redact_secrets_in_logs: bool = True


settings = Settings()
