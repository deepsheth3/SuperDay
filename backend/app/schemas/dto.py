from uuid import UUID

from pydantic import BaseModel


class AccountResolutionResult(BaseModel):
    resolved_account_id: UUID | None = None
    confidence: float = 0.0
    needs_disambiguation: bool = False
    reason_codes: list[str] = []
    candidate_account_ids: list[UUID] = []


class RetrievalCandidate(BaseModel):
    chunk_id: UUID
    communication_id: UUID
    score_lexical: float | None = None
    score_vector: float | None = None
    fused_score: float | None = None


class EvidenceBundle(BaseModel):
    """Minimal DTO; expand with EvidenceItem list as needed."""

    chunk_ids: list[UUID] = []
    hydrated_text: str = ""
