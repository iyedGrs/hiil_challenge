"""FastAPI application factory (spec/backend.md B9, spec/local-dev.md L1, L4).

FastAPI owns the ``/api`` prefix; the Vite proxy forwards paths unchanged. The
browser therefore keeps one origin, which is what makes the HttpOnly cookie and
CSRF header scheme work without CORS.

Migrations are never run here. Deployment runs one ``alembic upgrade head`` step
before starting the API and worker (spec/local-dev.md L4).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import auth, config as config_routes, health
from app.config import Settings, get_settings
from app.errors import register_error_handlers

logger = logging.getLogger("app.main")

#: Every router is mounted under this prefix (spec/local-dev.md L1).
API_PREFIX = "/api"

APP_TITLE = "Dispute preparation API"
APP_DESCRIPTION = (
    "Prepares contract-dispute documents before professional review. "
    "It does not decide liability, authenticate evidence or certify legal validity."
)


def ensure_storage_root(settings: Settings) -> Path:
    """Create the private file storage root when missing (spec/backend.md B4).

    The directory holds original uploads and rendered page images. Creating it at
    startup keeps ``/health/ready`` meaningful on a fresh volume. A failure is
    logged and re-raised: silently serving without storage would let uploads fail
    later with an opaque error.
    """
    root = Path(settings.file_storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate configuration and prepare storage before serving traffic."""
    settings = get_settings()
    ensure_storage_root(settings)
    logger.info(
        "API starting: env=%s ai_mode=%s legal_pack=%s",
        settings.app_env,
        settings.ai_mode.value,
        settings.legal_pack_version,
    )
    yield
    logger.info("API stopped")


def create_app() -> FastAPI:
    """Build the application with routers and error handlers registered."""
    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    register_error_handlers(app)

    # No CORS middleware: the browser talks to one origin through the Vite proxy
    # (spec/local-dev.md L1). Adding CORS would require restricting it to
    # APP_ORIGIN with credentials enabled.
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(config_routes.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)

    return app


app = create_app()
