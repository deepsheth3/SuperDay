"""Best-effort redaction of secrets from log records (Authorization Bearer, webhook patterns)."""

from __future__ import annotations

import logging
import re

from app.core.settings import settings

_AUTH_HEADER_RE = re.compile(
    r'(?i)(authorization\s*[:=]\s*["\']?Bearer\s+)([^\s"\']+)',
    re.MULTILINE,
)
_SIG_HEADER_RE = re.compile(
    r'(?i)(x-harper-signature\s*[:=]\s*["\']?)(sha256=[a-fA-F0-9]+|[a-fA-F0-9]{64})',
    re.MULTILINE,
)


class SecretRedactingFilter(logging.Filter):
    """Scrubs common secret patterns from `LogRecord.msg` and string `args`."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if not settings.redact_secrets_in_logs:
            return True
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        if record.args:
            record.args = tuple(
                self._scrub(a) if isinstance(a, str) else a for a in record.args
            )
        return True

    @staticmethod
    def _scrub(s: str) -> str:
        s = _AUTH_HEADER_RE.sub(r"\1[REDACTED]", s)
        s = _SIG_HEADER_RE.sub(r"\1[REDACTED]", s)
        return s


def install_secret_redaction() -> None:
    """Attach filter to root logger (uvicorn/Starlette inherit)."""
    if not settings.redact_secrets_in_logs:
        return
    filt = SecretRedactingFilter()
    root = logging.getLogger()
    if not any(isinstance(f, SecretRedactingFilter) for f in root.filters):
        root.addFilter(filt)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(name).addFilter(filt)
