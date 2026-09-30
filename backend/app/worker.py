from celery import Celery

from app.core.config import get_settings


settings = get_settings()
celery_app = Celery(
    "nikelpower",
    broker=settings.celery_broker_url or settings.redis_url,
    backend=(
        settings.celery_result_backend
        or settings.redis_url.rsplit("/", 1)[0] + "/1"
    ),
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

import app.tasks  # noqa: E402,F401
