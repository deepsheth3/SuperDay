"""
Amazon OpenSearch / OpenSearch Serverless — lexical document upsert.

Requires: pip install opensearch-py boto3
Set HARPER_ENABLE_OPENSEARCH_INDEX=true and host/region/service.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.settings import settings

logger = logging.getLogger(__name__)


def _build_client():  # pragma: no cover - integration
    from boto3 import Session
    from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

    if not settings.opensearch_host:
        raise RuntimeError("HARPER_OPENSEARCH_HOST is not set")
    session = Session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError("AWS credentials not found (IAM role, env, or ~/.aws/credentials)")
    auth = AWSV4SignerAuth(credentials=creds, region=settings.aws_region or "us-east-1", service=settings.opensearch_service)
    host = settings.opensearch_host
    return OpenSearch(
        hosts=[{"host": host, "port": settings.opensearch_port}],
        http_auth=auth,
        use_ssl=settings.opensearch_use_ssl,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
    )


async def upsert_lexical_chunk(
    *,
    doc_id: str,
    tenant_id: str,
    chunk_id: str,
    chunk_text: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    if not settings.enable_opensearch_index:
        logger.debug("opensearch: disabled (HARPER_ENABLE_OPENSEARCH_INDEX=false)")
        return ""

    body = {
        "tenant_id": tenant_id,
        "chunk_id": chunk_id,
        "text": chunk_text,
        **(metadata or {}),
    }

    def _run() -> Any:
        client = _build_client()
        return client.index(
            index=settings.opensearch_index_name,
            id=doc_id,
            body=body,
            refresh=True,
        )

    resp = await asyncio.to_thread(_run)
    rid = (resp or {}).get("_id", doc_id)
    logger.info("opensearch indexed id=%s index=%s", rid, settings.opensearch_index_name)
    return str(rid)
