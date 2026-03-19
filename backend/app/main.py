"""FastAPI entrypoint — wire routers from app.api when implemented."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv

    _repo_root = Path(__file__).resolve().parents[3]
    load_dotenv(_repo_root / ".env")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError

from app.api import chat, health, ingest, pipeline_status, rehydration, webhooks, ws_chat
from app.core.logging_redaction import install_secret_redaction
from app.core.settings import settings

logging.basicConfig(level=logging.INFO)
install_secret_redaction()
logger = logging.getLogger(__name__)

_frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task[None]] = []
    if settings.start_background_workers:
        from app.workers.pipeline_workers import start_background_workers

        tasks = start_background_workers()
        logger.info("background pipeline workers started (%s tasks)", len(tasks))
    yield
    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    logger.info("background workers stopped")


app = FastAPI(title="Harper Chat Service", version="1.0.0", lifespan=lifespan)


@app.get("/")
async def root_redirect():
    """Browser convenience (replaces legacy Flask `GET /`)."""
    return RedirectResponse(url=_frontend, status_code=307)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend, "http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Tenant-ID",
        "X-Trace-ID",
        "X-Request-ID",
        "Authorization",
        "X-Harper-Signature",
    ],
)
app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(rehydration.router, prefix="/api", tags=["rehydration"])
app.include_router(pipeline_status.router, prefix="/api", tags=["pipeline"])
app.include_router(webhooks.router, prefix="/api", tags=["webhooks"])
app.include_router(ws_chat.router, prefix="/api", tags=["websocket"])


@app.exception_handler(ValueError)
async def value_error_handler(_, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "validation_error",
            "message": str(exc),
            "retryable": False,
            "trace_id": "",
        },
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(_, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "validation_error",
            "message": exc.errors(),
            "retryable": False,
            "trace_id": "",
        },
    )
