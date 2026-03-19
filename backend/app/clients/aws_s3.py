"""
S3 raw payload storage for ingestion.

Requires: pip install boto3
Configure HARPER_S3_RAW_BUCKET, HARPER_AWS_REGION (or use default credential chain).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.clients.s3_key_layout import join_with_prefix, raw_ingest_payload_key
from app.core.settings import settings

logger = logging.getLogger(__name__)


def _client():
    import boto3

    kwargs: dict[str, Any] = {}
    if settings.aws_region:
        kwargs["region_name"] = settings.aws_region
    return boto3.client("s3", **kwargs)


def _object_key(tenant_id: str, source_system: str, source_event_id: str) -> str:
    p = settings.s3_raw_prefix.strip("/")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in source_event_id)[:200]
    return f"{p}/{tenant_id}/{source_system}/{safe}"


async def put_raw_json(tenant_id: str, source_system: str, source_event_id: str, body: dict[str, Any]) -> str:
    """Upload JSON object; returns s3://bucket/key."""
    if not settings.s3_raw_bucket:
        raise RuntimeError("HARPER_S3_RAW_BUCKET is not set")

    rel = raw_ingest_payload_key(tenant_id, source_system, source_event_id)
    key = join_with_prefix(settings.s3_raw_prefix, rel)

    def _run() -> None:
        _client().put_object(
            Bucket=settings.s3_raw_bucket,
            Key=key,
            Body=json.dumps(body, default=str).encode("utf-8"),
            ContentType="application/json",
        )

    await asyncio.to_thread(_run)
    uri = f"s3://{settings.s3_raw_bucket}/{key}"
    logger.info("s3 put %s", uri)
    return uri


async def get_object_text(s3_uri: str) -> str:
    """Fetch object body as utf-8 text. s3_uri format: s3://bucket/key"""
    if not s3_uri.startswith("s3://"):
        raise ValueError("expected s3:// URI")
    _, rest = s3_uri.split("s3://", 1)
    bucket, _, key = rest.partition("/")

    def _run() -> bytes:
        r = _client().get_object(Bucket=bucket, Key=key)
        return r["Body"].read()

    data = await asyncio.to_thread(_run)
    return data.decode("utf-8", errors="replace")
