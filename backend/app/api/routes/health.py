import structlog
from fastapi import APIRouter, Depends, HTTPException
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.documents import HealthResponse


router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", response_model=HealthResponse)
def readiness(session: Session = Depends(get_db)) -> HealthResponse:
    services: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as error:
        logger.exception(
            "postgres_readiness_check_failed",
            error_type=type(error).__name__,
        )
        services["postgres"] = "unavailable"

    client = Redis.from_url(get_settings().redis_url, socket_timeout=2)
    try:
        client.ping()
        services["redis"] = "ok"
    except Exception as error:
        logger.exception(
            "redis_readiness_check_failed",
            error_type=type(error).__name__,
        )
        services["redis"] = "unavailable"
    finally:
        client.close()

    ready = all(result == "ok" for result in services.values())
    response = HealthResponse(status="ok" if ready else "unavailable", services=services)
    if not ready:
        raise HTTPException(status_code=503, detail=response.model_dump())
    return response
