"""Local ingest → normalize → embed pipeline (file-backed; Pub/Sub-compatible event shapes)."""

from app.services.pipeline.bus import get_bus
from app.services.pipeline.store import FilePipelineStore, get_pipeline_store

__all__ = ["get_bus", "FilePipelineStore", "get_pipeline_store"]
