import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.main import app


def test_http_requests_have_correlatable_json_logs() -> None:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/health/live")

    response = asyncio.run(send_request())

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    UUID(request_id)

    log_path = Path(get_settings().log_dir) / "api" / "api.jsonl"
    with open(log_path, encoding="utf-8") as log_file:
        events = [json.loads(line) for line in log_file if line.strip()]

    assert any(
        event.get("event") == "http_request_completed"
        and event.get("request_id") == request_id
        and event.get("status_code") == 200
        for event in events
    )
