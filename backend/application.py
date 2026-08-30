"""FastAPI application factory."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .http import register_exception_handlers, request_guards
from .logging_privacy import enforce_transport_log_privacy
from .routes import (
    account, analytics, auth, billing, chat, code, credits, features, files, health, intelligence,
    library, lifecycle, manuscripts, media, presence, projects, safety, sync, voice,
)
from .runtime import settings
from .version import __version__

PUBLIC_DIR = Path(__file__).resolve().parents[1] / 'public'


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    # httpx includes complete request URLs in its INFO messages. Supabase filters can
    # contain opaque session hashes and internal row IDs, so dependency transport
    # records are dropped while Ask Crump emits its own categorical diagnostics.
    enforce_transport_log_privacy()


def create_app() -> FastAPI:
    configure_logging()
    application = FastAPI(
        title='Ask Crump API',
        version=__version__,
        docs_url='/api/docs' if not settings.is_production else None,
        redoc_url=None,
        openapi_url='/api/openapi.json' if not settings.is_production else None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
        allow_headers=[
            'Content-Type', 'Authorization', 'X-Crump-Client', 'X-Crump-Platform',
            'X-Device-Name', 'X-Installation-ID', 'X-Request-ID', 'X-Idempotency-Key',
        ],
    )
    application.middleware('http')(request_guards)
    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(account.router)
    application.include_router(analytics.router)
    application.include_router(sync.router)
    application.include_router(files.router)
    application.include_router(projects.router)
    application.include_router(code.router)
    application.include_router(voice.router)
    application.include_router(features.router)
    application.include_router(media.router)
    application.include_router(manuscripts.router)
    application.include_router(library.router)
    application.include_router(chat.router)
    application.include_router(intelligence.router)
    application.include_router(lifecycle.router)
    application.include_router(presence.router)
    application.include_router(billing.router)
    application.include_router(credits.router)
    application.include_router(safety.router)

    if PUBLIC_DIR.exists():
        @application.get('/', include_in_schema=False)
        async def local_index():
            return FileResponse(PUBLIC_DIR / 'ask-crump.html')

        @application.get('/app', include_in_schema=False)
        async def local_app():
            return FileResponse(PUBLIC_DIR / 'app.html')

        application.mount('/', StaticFiles(directory=PUBLIC_DIR, html=True), name='public')
    return application
