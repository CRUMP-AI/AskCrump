"""Keep private PDF previews frameable without widening the embedding boundary."""

from dataclasses import replace
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import app
from backend import http as http_module
from backend.config import PRODUCTION_SUPABASE_ORIGIN
from backend.runtime import settings


ROOT = Path(__file__).resolve().parents[1]


def _directives(policy: str) -> dict[str, list[str]]:
    clauses = (clause.split() for clause in policy.split(";") if clause.strip())
    return {parts[0]: parts[1:] for parts in clauses if parts}


def test_pdf_preview_frame_src_is_exact_in_backend_and_deployment(monkeypatch):
    production_settings = replace(settings, supabase_url=PRODUCTION_SUPABASE_ORIGIN)
    monkeypatch.setattr(http_module, "settings", production_settings)
    backend_headers = TestClient(app).get("/api/health").headers
    deploy_config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    global_headers = next(
        entry["headers"] for entry in deploy_config["headers"]
        if entry["source"] == "/:path*"
    )
    deploy_headers = {entry["key"].lower(): entry["value"] for entry in global_headers}
    expected_frame_sources = [
        "'self'",
        PRODUCTION_SUPABASE_ORIGIN,
    ]
    assert _directives(backend_headers["content-security-policy"])["frame-src"] == (
        expected_frame_sources
    )
    assert _directives(deploy_headers["content-security-policy"])["frame-src"] == (
        expected_frame_sources
    )

    for headers in (backend_headers, deploy_headers):
        policy = _directives(headers["content-security-policy"])
        assert policy["frame-ancestors"] == ["'none'"]
        assert headers["x-frame-options"] == "DENY"
        assert all("*" not in source for source in policy["frame-src"])


@pytest.mark.parametrize("environment", ["production", "preview"])
def test_hosted_settings_reject_supabase_origin_drift(environment):
    hosted_settings = replace(
        settings,
        environment=environment,
        app_url="https://www.askcrump.com",
        cookie_secure=True,
        supabase_url=PRODUCTION_SUPABASE_ORIGIN,
        supabase_service_key="production-service-key",
        anthropic_api_key="production-anthropic-key",
        ai_gateway_enabled=False,
        resend_api_key="production-resend-key",
    )
    hosted_settings.validate_required()

    drifted_settings = replace(
        hosted_settings,
        supabase_url="https://replacement-project.supabase.co",
    )
    with pytest.raises(RuntimeError, match="source-controlled hosted PDF preview origin"):
        drifted_settings.validate_required()


def test_local_development_can_use_a_separate_supabase_origin():
    development_settings = replace(
        settings,
        environment="development",
        supabase_url="https://local-project.supabase.co",
        supabase_service_key="local-service-key",
    )

    development_settings.validate_required()
