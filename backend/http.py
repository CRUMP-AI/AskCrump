"""HTTP middleware, shared response helpers, and exception mapping."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .ai_service import AIServiceError
from .auth_service import AuthenticationError
from .db import DatabaseError
from .rate_limit import RateLimitError
from .runtime import settings

logger = logging.getLogger("askcrump.http")


async def request_guards(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or secrets.token_hex(12)
    content_length = request.headers.get("content-length")

    if content_length:
        try:
            if int(content_length) > settings.max_request_bytes:
                return _request_too_large(request_id)
        except ValueError:
            pass

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        body = await request.body()
        if len(body) > settings.max_request_bytes:
            return _request_too_large(request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "; ".join((
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob: https:",
        "connect-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
    ))
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _request_too_large(request_id: str) -> JSONResponse:
    response = JSONResponse(
        status_code=413,
        content={
            "success": False,
            "error": "Request is too large.",
            "code": "REQUEST_TOO_LARGE",
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


def _legacy_parent_cookie_domain() -> str | None:
    if settings.cookie_domain:
        return None
    hostname = (urlparse(getattr(settings, "app_url", "")).hostname or "").lower()
    if hostname.startswith("www."):
        return hostname[4:]
    return None


def _delete_session_cookie(response: Response, *, domain: str | None) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        domain=domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def set_session_cookie(response: Response, raw_token: str, request: Request) -> None:
    if request.headers.get("x-crump-client", "").lower() == "native":
        return
    expires = datetime.now(timezone.utc) + timedelta(days=settings.session_days)
    legacy_domain = _legacy_parent_cookie_domain()
    if legacy_domain:
        _delete_session_cookie(response, domain=legacy_domain)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_days * 86400,
        expires=expires,
        path="/",
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    _delete_session_cookie(response, domain=settings.cookie_domain)
    legacy_domain = _legacy_parent_cookie_domain()
    if legacy_domain:
        _delete_session_cookie(response, domain=legacy_domain)


def native_token_payload(request: Request, raw_token: str) -> dict[str, Any]:
    if request.headers.get("x-crump-client", "").lower() == "native":
        return {"sessionToken": raw_token}
    return {}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthenticationError)
    async def auth_error_handler(_: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "authenticated": False,
                "error": exc.message,
                "code": "AUTH_REQUIRED",
            },
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_error_handler(_: Request, exc: RateLimitError):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(exc.retry_after)},
            content={
                "success": False,
                "error": exc.message,
                "code": "RATE_LIMITED",
                "retryAfter": exc.retry_after,
            },
        )

    @app.exception_handler(AIServiceError)
    async def ai_service_error_handler(_: Request, exc: AIServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.message,
                "message": exc.message,
                "code": exc.code,
                "shouldRetry": exc.retryable,
                "retryAfter": exc.retry_after,
            },
        )

    @app.exception_handler(DatabaseError)
    async def database_error_handler(_: Request, exc: DatabaseError):
        logger.error("Database request failed: %s details=%r", exc.message, exc.details)
        status = 503 if exc.status_code >= 500 else 500
        return JSONResponse(
            status_code=status,
            content={
                "success": False,
                "error": "The service database is temporarily unavailable.",
                "code": "DATABASE_ERROR",
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError):
        details = exc.errors()
        message = str(details[0].get("msg")) if details else "Invalid request."
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": message,
                "code": "VALIDATION_ERROR",
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception):
        logger.exception("Unhandled application error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "An unexpected error occurred.",
                "code": "INTERNAL_ERROR",
            },
        )
