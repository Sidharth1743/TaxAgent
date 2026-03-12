"""Lightweight ASGI health check wrapper.

Usage:
    from backend.health import with_health_check
    app = with_health_check(existing_asgi_app)

GET /health returns {"status": "ok"} with 200.
All other requests pass through to the wrapped app.
"""

from __future__ import annotations

import json
from typing import Any, Callable


def with_health_check(app: Callable) -> Callable:
    """Wrap an ASGI app so GET /health returns a 200 JSON response."""

    async def wrapper(scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if (
            scope["type"] == "http"
            and scope["path"] == "/health"
            and scope["method"] == "GET"
        ):
            body = json.dumps({"status": "ok"}).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(body)).encode("ascii")],
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await app(scope, receive, send)

    return wrapper
