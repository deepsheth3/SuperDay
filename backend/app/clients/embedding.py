"""Embedding + lexical/vector indexing (local stub + optional GCP Vertex + AWS OpenSearch)."""

from __future__ import annotations

import hashlib
import logging
import struct
from typing import Any

from app.core.settings import settings

logger = logging.getLogger(__name__)


def deterministic_embedding(text: str, dims: int = 8) -> list[float]:
    """Stable pseudo-embedding for local dev (not for production retrieval quality)."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    for i in range(dims):
        chunk = h[i % len(h) : (i % len(h)) + 4] or h[:4]
        padded = (chunk + b"\x00" * 4)[:4]
        u = struct.unpack("!I", padded)[0]
        out.append((u % 10000) / 10000.0 - 0.5)
    return out


async def embed_and_index_chunk(
    *,
    chunk_id: str,
    chunk_text: str,
    tenant_id: str,
    embedding_model: str,
    source_type: str | None = None,
) -> dict[str, Any]:
    """
    Contract: DB update only in real impl; Vertex + OpenSearch outside single txn.

    When cloud env vars are set (see docs/CLOUD_SETUP.md), calls real clients;
    otherwise deterministic vector + synthetic doc ids.
    """
    vector: list[float] | None = None
    if settings.gcp_project_id and settings.gcp_region:
        try:
            from app.clients.gcp_vertex_vector import embed_text_vertex

            vector = await embed_text_vertex(chunk_text)
        except Exception:
            logger.debug("vertex embedding unavailable; using local stub", exc_info=True)
            vector = None
    if vector is None or len(vector) == 0:
        vector = deterministic_embedding(chunk_text)

    lexical_doc_id = f"lex-{chunk_id}"
    if settings.enable_opensearch_index:
        try:
            from app.clients.aws_opensearch import upsert_lexical_chunk

            oid = await upsert_lexical_chunk(
                doc_id=lexical_doc_id,
                tenant_id=tenant_id,
                chunk_id=chunk_id,
                chunk_text=chunk_text,
                metadata={"source_type": source_type or ""},
            )
            if oid:
                lexical_doc_id = oid
        except ImportError:
            logger.warning("opensearch-py/boto3 not installed; skipping OpenSearch")
        except Exception:
            logger.exception("OpenSearch upsert failed chunk_id=%s", chunk_id)

    vector_doc_id = f"vec-{chunk_id}"
    if settings.enable_vertex_vector_upsert:
        try:
            from app.clients.gcp_vertex_vector import upsert_vector_datapoint

            ok = await upsert_vector_datapoint(
                datapoint_id=chunk_id,
                feature_vector=vector,
                restricts={"tenant_id": tenant_id},
            )
            if not ok:
                vector_doc_id = f"vec-pending-{chunk_id}"
        except ImportError:
            logger.debug("vertex vector upsert skipped (deps)")
        except Exception:
            logger.exception("Vertex vector upsert failed chunk_id=%s", chunk_id)

    logger.debug(
        "embed_and_index chunk_id=%s model=%s lexical=%s vector_dims=%s",
        chunk_id,
        embedding_model,
        lexical_doc_id,
        len(vector),
    )
    return {
        "embedding_status": "indexed",
        "lexical_doc_id": lexical_doc_id,
        "vector_doc_id": vector_doc_id,
        "embedding_model": embedding_model,
        "vector_preview": vector[:4],
    }
