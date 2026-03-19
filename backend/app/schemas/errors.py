from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    retryable: bool = False
    trace_id: str = ""
    details: dict[str, Any] | None = None
