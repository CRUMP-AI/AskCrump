from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_public_destination_verifier_is_bounded_and_credential_free() -> None:
    source = (ROOT / "scripts" / "verify-live-public-destinations.mjs").read_text(
        encoding="utf-8"
    )
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["test:live-public-destinations"] == (
        "node scripts/verify-live-public-destinations.mjs"
    )
    assert "ASKCRUMP_PUBLIC_ORIGIN" in source
    assert "https://www.askcrump.com" in source
    assert "candidate.endsWith('.html') || candidate.endsWith('.js')" in source
    assert "raw.includes('${')" in source
    assert "replaceAll('&amp;', '&')" in source
    assert "redirect: 'manual'" in source
    assert "expectedCompatibilityRedirects" in source
    assert "unexpectedly redirects" in source
    assert "enters another redirect" in source
    assert "response.status !== 200" in source
    assert "AbortSignal.timeout(15_000)" in source
    assert "concurrency = 6" in source
    assert "sitemap.xml contains no public URLs" in source
    assert "is missing a canonical link" in source
    assert "robots.txt does not advertise the canonical sitemap" in source
    for forbidden in (
        "authorization",
        "cookie",
        "password",
        "service_role",
        "supabase",
        "customer",
    ):
        assert forbidden not in source.lower()
