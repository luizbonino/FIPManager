"""FastAPI app: router mounting, CSRF middleware, SPA static serving."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from fipm.auth import csrf_middleware
from fipm.config import get_settings
from fipm.importer import run_import
from fipm.routers import auth, fers, fips, health, knowledge_models, me, sessions

logger = logging.getLogger(__name__)


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

app.middleware("http")(csrf_middleware)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(knowledge_models.router, prefix="/api")
app.include_router(fers.router, prefix="/api")
app.include_router(fips.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")


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
