"""FastAPI app: router mounting, CSRF middleware, SPA static serving."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from fipm.auth import csrf_middleware, password_change_middleware
from fipm.config import get_settings
from fipm.importer import run_import
from fipm.routers import (
    admin,
    auth,
    embed,
    feedback,
    fer_types,
    fers,
    fips,
    health,
    knowledge_models,
    me,
    privacy,
    sessions,
)

logger = logging.getLogger(__name__)

_BODY_LIMITED_METHODS = {"POST", "PUT", "PATCH"}


class PayloadTooLarge(HTTPException):
    """Raised by `BodySizeLimitMiddleware` when a streamed (chunked) request
    body under /api/ crosses `settings.max_body_bytes` (review finding 3).
    Must subclass HTTPException: FastAPI's request-body parsing
    (`fastapi.routing.get_request_handler`) re-raises HTTPException as-is
    but rewrites any other exception raised while reading the body into a
    generic 400 "There was an error parsing the body", which would mask
    this 413."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail="payload_too_large")


class BodySizeLimitMiddleware:
    """Rejects an oversized POST/PUT/PATCH body under /api/ with 413
    `payload_too_large` -- before the body is read when `Content-Length`
    already exceeds the cap, or as soon as the running total crosses it for
    a chunked/unbounded body (review finding 3). Pure ASGI (not
    `BaseHTTPMiddleware`) so it never buffers the body itself; it only
    counts bytes as the app underneath reads them."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _BODY_LIMITED_METHODS
            or not scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                too_big = int(content_length) > self.max_bytes
            except ValueError:
                too_big = False
            if too_big:
                response = JSONResponse(status_code=413, content={"detail": "payload_too_large"})
                await response(scope, receive, send)
                return

        max_bytes = self.max_bytes
        total = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > max_bytes:
                    raise PayloadTooLarge
            return message

        await self.app(scope, limited_receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.check_production_safety()
    try:
        summary = run_import()
        summary.print_report()
    except Exception:  # pragma: no cover - defensive: never block startup on bad data/
        logger.exception("startup import-data failed")
    yield


app = FastAPI(title="FIP Manager", lifespan=lifespan)

app.add_middleware(BodySizeLimitMiddleware, max_bytes=get_settings().max_body_bytes)
app.middleware("http")(csrf_middleware)
app.middleware("http")(password_change_middleware)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(knowledge_models.router, prefix="/api")
app.include_router(fers.router, prefix="/api")
app.include_router(fer_types.router, prefix="/api")
app.include_router(fips.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(privacy.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")
# spec 06-dmp-linkage.md §3: GET /fips/{id}/embed lives outside /api, so it
# must be included here -- before the SPA catch-all below -- or the
# catch-all swallows it.
app.include_router(embed.router)


def _static_dir() -> Path:
    return Path(get_settings().static_dir)


_assets_dir = _static_dir() / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str) -> object:
    if path.startswith("api"):
        raise HTTPException(status_code=404, detail="not_found")
    index_file = _static_dir() / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return PlainTextResponse(
        "FIP Manager backend is running. Frontend build not found at static_dir.",
        status_code=200,
    )
