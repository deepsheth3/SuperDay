"""
Vertex AI embeddings + Vector Search (Matching Engine) upserts — boilerplate.

Full Matching Engine streaming upsert APIs are project-specific. This module:
- Generates embeddings via Vertex / Gemini when configured.
- Logs clear TODOs for datapoint upsert to your deployed index.

Requires: pip install google-cloud-aiplatform (and usually GOOGLE_APPLICATION_CREDENTIALS or workload identity).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.settings import settings

logger = logging.getLogger(__name__)


async def embed_text_vertex(text: str) -> list[float] | None:
    """Return embedding vector using Vertex textembedding model, or None if not configured."""
    if not settings.gcp_project_id or not settings.gcp_region:
        return None

    def _run() -> list[float]:
        from vertexai.language_models import TextEmbeddingModel

        import vertexai

        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
        model = TextEmbeddingModel.from_pretrained(settings.vertex_embedding_model)
        emb = model.get_embeddings([text])
        if not emb or not emb[0].values:
            return []
        return list(emb[0].values)

    try:
        return await asyncio.to_thread(_run)
    except Exception:
        logger.exception("vertex embedding failed")
        return None


async def upsert_vector_datapoint(
    *,
    datapoint_id: str,
    feature_vector: list[float],
    restricts: dict[str, Any] | None = None,
) -> bool:
    """
    Upsert one vector into Matching Engine index.

    Replace this body with your endpoint's REST/gRPC call:
    https://cloud.google.com/vertex-ai/docs/vector-search/update-index
    """
    if not settings.enable_vertex_vector_upsert:
        logger.debug("vertex vector: disabled")
        return False
    if not settings.vertex_index_endpoint_id or not settings.vertex_index_id:
        logger.warning(
            "vertex vector: set HARPER_VERTEX_INDEX_ENDPOINT_ID and HARPER_VERTEX_INDEX_ID "
            "and implement upsert in app/clients/gcp_vertex_vector.py"
        )
        return False

    # Boilerplate: log intent; implement with aiplatform.MatchingEngineIndexEndpoint or raw REST.
    logger.info(
        "vertex vector upsert (TODO implement): datapoint_id=%s dims=%s restricts=%s endpoint=%s index=%s",
        datapoint_id,
        len(feature_vector),
        restricts,
        settings.vertex_index_endpoint_id,
        settings.vertex_index_id,
    )
    return True
