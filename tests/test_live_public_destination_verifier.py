from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_public_destination_verifier_is_bounded_and_credential_free() -> None:
    source = (ROOT / "scripts" / "verify-live-public-destinations.mjs").read_text(
        encoding="utf-8"
    )
    parser = (ROOT / "scripts" / "public-destination-parser.mjs").read_text(
        encoding="utf-8"
    )
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["test:live-public-destinations"] == (
        "node scripts/verify-live-public-destinations.mjs"
    )
    assert "ASKCRUMP_PUBLIC_ORIGIN" in source
    assert "https://www.askcrump.com" in source
    assert "candidate.endsWith('.html') || candidate.endsWith('.js')" in source
    assert "staticAnchorHref(match[2], sourceType)" in source
    assert "file.toLowerCase().endsWith('.js') ? 'javascript' : 'html'" in source
    assert "JAVASCRIPT_RUNTIME_HREF_PATTERNS" in parser
    assert ".concat\\s*\\(" in parser
    assert "normalizedSourceType === 'javascript'" in parser
    assert "replaceAll('&amp;', '&')" in parser
    assert "redirect: 'manual'" in source
    assert "expectedApprovedRedirects" in source
    assert "['https://www.clevercrump.com/', 'https://clevercrump.com/']" in source
    assert "unexpectedly redirects" in source
    assert "enters another redirect" in source
    assert "response.status !== 200" in source
    assert "AbortSignal.timeout(15_000)" in source
    assert "attempt <= 3" in source
    assert "[408, 429, 500, 502, 503, 504]" in source
    assert "concurrency = 6" in source
    assert "sitemap.xml contains no public URLs" in source
    assert "is missing a canonical link" in source
    assert "robots.txt does not advertise the canonical sitemap" in source
    assert "must expose exactly one non-empty" in source
    assert "duplicates the title" in source
    assert "duplicates the description" in source
    assert "is not explicitly indexable and followable" in source
    assert "structured data does not reference its canonical URL" in source
    assert "uses different Open Graph and Twitter images" in source
    assert "social-preview images" in source
    for forbidden in (
        "authorization",
        "cookie",
        "password",
        "service_role",
        "supabase",
        "customer",
    ):
        assert forbidden not in source.lower()


def test_public_destination_parser_executes_static_and_runtime_href_fixtures() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["test:public-destination-parser"] == (
        "node scripts/test-public-destination-parser.mjs"
    )

    result = subprocess.run(
        ["node", "scripts/test-public-destination-parser.mjs"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "7 static hrefs accepted" in result.stdout
    assert "12 non-navigation or runtime-built hrefs ignored" in result.stdout


def test_live_public_destination_health_workflow_is_daily_manual_and_read_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "public-destination-health.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert 'cron: "17 11 * * *"' in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "contents: read" in workflow
    assert "timeout-minutes: 10" in workflow
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-node@v7" in workflow
    assert 'node-version: "22"' in workflow
    assert "node scripts/verify-live-public-destinations.mjs" in workflow
    assert "ASKCRUMP_PUBLIC_ORIGIN: https://www.askcrump.com" in workflow
    assert "secrets." not in workflow
