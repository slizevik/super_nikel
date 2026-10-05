import time
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.routes import documents, health, jobs
from app.core.config import get_settings
from app.core.logging import configure_logging


configure_logging("api")
settings = get_settings()
logger = structlog.get_logger(__name__)
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="PDF ingestion API for the Nikelpower knowledge base.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    request_id = str(uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        logger.exception(
            "http_request_failed",
            method=request.method,
            path=request.url.path,
            error_type=type(error).__name__,
        )
        raise
    else:
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return response
    finally:
        structlog.contextvars.clear_contextvars()


app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(documents.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
