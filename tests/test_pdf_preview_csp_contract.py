"""Keep the PDF viewer's redirect target frameable without widening embedding policy."""

import html
import json
from pathlib import Path
import re

from fastapi.testclient import TestClient

from app import app


ROOT = Path(__file__).resolve().parents[1]
SIGNED_STORAGE_ORIGIN = "https://xncftwjfpjskgtwgbgci.supabase.co"


def _directives(policy: str) -> dict[str, list[str]]:
    clauses = (clause.split() for clause in policy.split(";") if clause.strip())
    return {parts[0]: parts[1:] for parts in clauses if parts}


def test_pdf_preview_frame_src_matches_backend_deployment_and_fixture():
    backend_headers = TestClient(app).get("/api/health").headers
    deploy_config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    global_headers = next(entry["headers"] for entry in deploy_config["headers"]
                          if entry["source"] == "/:path*")
    deploy_headers = {entry["key"].lower(): entry["value"] for entry in global_headers}
    fixture = (ROOT / "tests" / "fixtures" / "file-library-usability.html").read_text(
        encoding="utf-8"
    )
    fixture_policy = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', fixture
    )
    assert fixture_policy is not None

    expected_frame_src = ["'self'", SIGNED_STORAGE_ORIGIN]
    for policy in (
        backend_headers["content-security-policy"],
        deploy_headers["content-security-policy"],
        html.unescape(fixture_policy.group(1)),
    ):
        assert _directives(policy)["frame-src"] == expected_frame_src

    for headers in (backend_headers, deploy_headers):
        assert _directives(headers["content-security-policy"])["frame-ancestors"] == [
            "'none'"
        ]
        assert headers["x-frame-options"] == "DENY"
