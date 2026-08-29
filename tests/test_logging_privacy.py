import logging
from io import StringIO

import pytest
from fastapi import Request, Response

from backend.application import configure_logging
from backend.db import DatabaseError
from backend.http import register_exception_handlers, request_guards


def test_upstream_http_request_urls_are_not_emitted_at_info_level():
    httpx_logger = logging.getLogger('httpx')
    httpcore_logger = logging.getLogger('httpcore')
    previous_httpx = httpx_logger.level
    previous_httpcore = httpcore_logger.level
    try:
        httpx_logger.setLevel(logging.INFO)
        httpcore_logger.setLevel(logging.DEBUG)
        configure_logging()

        assert httpx_logger.level == logging.WARNING
        assert httpcore_logger.level == logging.WARNING
        assert httpx_logger.filters
        assert httpcore_logger.filters
    finally:
        httpx_logger.setLevel(previous_httpx)
        httpcore_logger.setLevel(previous_httpcore)


def test_privacy_filter_preserves_ask_crump_categorical_outcomes():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    app_logger = logging.getLogger("askcrump.auth")
    previous_httpx_level = httpx_logger.level
    previous_app_level = app_logger.level
    root.addHandler(handler)
    try:
        configure_logging()
        httpx_logger.setLevel(logging.INFO)
        app_logger.setLevel(logging.INFO)

        httpx_logger.info(
            "HTTP Request: GET https://example.supabase.co/rest/v1/sessions?token_hash=eq.private"
        )
        app_logger.info("Auth session outcome=authenticated client=web")

        assert "private" not in stream.getvalue()
        assert "Auth session outcome=authenticated client=web" in stream.getvalue()
    finally:
        root.removeHandler(handler)
        httpx_logger.setLevel(previous_httpx_level)
        app_logger.setLevel(previous_app_level)


@pytest.mark.asyncio
async def test_request_boundary_survives_host_reconfiguration_and_blocks_full_transport_urls():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    httpx_logger = logging.getLogger("httpx")
    previous_handlers = list(httpx_logger.handlers)
    previous_filters = list(httpx_logger.filters)
    previous_level = httpx_logger.level
    previous_propagate = httpx_logger.propagate
    try:
        # Simulate a serverless host applying INFO logging after importing the app.
        httpx_logger.handlers = [handler]
        httpx_logger.filters = []
        httpx_logger.setLevel(logging.INFO)
        httpx_logger.propagate = False
        request = Request({"type": "http", "method": "GET", "path": "/api/health", "headers": []})

        async def downstream(_: Request) -> Response:
            httpx_logger.info(
                "HTTP Request: GET https://example.supabase.co/rest/v1/sessions?token_hash=eq.private-session-hash"
            )
            logging.getLogger("askcrump.auth").info("Auth session outcome=authenticated client=web")
            return Response()

        response = await request_guards(request, downstream)

        assert response.status_code == 200
        assert "private-session-hash" not in stream.getvalue()
        assert "HTTP Request" not in stream.getvalue()
        assert httpx_logger.level == logging.WARNING
        assert handler.filters
    finally:
        httpx_logger.handlers = previous_handlers
        httpx_logger.filters = previous_filters
        httpx_logger.setLevel(previous_level)
        httpx_logger.propagate = previous_propagate


@pytest.mark.asyncio
async def test_database_exception_log_is_categorical_and_excludes_provider_details(caplog):
    from fastapi import FastAPI

    app = FastAPI()
    register_exception_handlers(app)
    sensitive = "token_hash=eq.private-session-hash user_id=eq.private-user"

    @app.get("/failure")
    async def failure():
        raise DatabaseError("Database operation failed", 409, {"details": sensitive})

    from httpx import ASGITransport, AsyncClient

    with caplog.at_level(logging.ERROR, logger="askcrump.http"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/failure")

    assert response.status_code == 500
    assert response.json()["code"] == "DATABASE_ERROR"
    assert "status=409" in caplog.text
    assert "detail_type=dict" in caplog.text
    assert sensitive not in caplog.text


@pytest.mark.asyncio
async def test_database_read_exhaustion_exposes_only_bounded_retry_guidance():
    from fastapi import FastAPI

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def failure():
        raise DatabaseError(
            "Database operation failed",
            503,
            {"error_type": "ConnectError"},
            retryable=True,
            retry_after=2,
            attempts=4,
        )

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/failure")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"
    assert response.json() == {
        "success": False,
        "error": "The service database is temporarily unavailable.",
        "code": "DATABASE_ERROR",
        "shouldRetry": True,
        "retryAfter": 2,
    }
