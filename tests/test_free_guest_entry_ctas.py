from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.anchors.append({key: value or "" for key, value in attrs})


def _anchors(path: Path) -> list[dict[str, str]]:
    parser = _AnchorParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.anchors


def test_every_public_free_cta_enters_guest_mode_instead_of_forcing_signup() -> None:
    free_ctas: list[tuple[Path, dict[str, str]]] = []
    for path in PUBLIC.rglob("*.html"):
        for anchor in _anchors(path):
            destination = urlparse(anchor.get("href", ""))
            query = parse_qs(destination.query)
            if (
                destination.path == "/app"
                and query.get("plan") == ["free"]
                and anchor.get("data-plan") == "free"
            ):
                free_ctas.append((path, anchor))

    assert free_ctas
    for path, anchor in free_ctas:
        destination = urlparse(anchor.get("href", ""))
        query = parse_qs(destination.query)
        assert destination.path == "/app", (path, anchor)
        assert query.get("plan") == ["free"], (path, anchor)
        assert "signup" not in query, (path, anchor)


def test_every_public_signin_link_forces_the_login_path() -> None:
    signin_links: list[tuple[Path, dict[str, str]]] = []
    for path in PUBLIC.rglob("*.html"):
        for anchor in _anchors(path):
            if "nav-signin" in anchor.get("class", "").split():
                signin_links.append((path, anchor))

    assert signin_links
    for path, anchor in signin_links:
        destination = urlparse(anchor.get("href", ""))
        query = parse_qs(destination.query)
        assert destination.path == "/app", (path, anchor)
        assert "signin" in query.get("source", [""])[0], (path, anchor)
        assert "signup" not in query, (path, anchor)


def test_clever_crump_company_page_free_links_enter_guest_mode() -> None:
    company_links = [
        anchor
        for anchor in _anchors(PUBLIC / "clever-crump.html")
        if anchor.get("data-cta", "").startswith("clevercrump-")
    ]

    assert {anchor["data-cta"] for anchor in company_links} == {
        "clevercrump-product",
        "clevercrump-closing",
    }
    for anchor in company_links:
        destination = urlparse(anchor["href"])
        query = parse_qs(destination.query)
        assert destination.netloc == "www.askcrump.com"
        assert destination.path == "/app"
        assert query.get("source") == ["clevercrump"]
        assert query.get("plan") == ["free"]
        assert "signup" not in query


def test_homepage_free_entry_surfaces_are_all_covered() -> None:
    homepage_ctas = {
        anchor.get("data-cta"): anchor
        for anchor in _anchors(PUBLIC / "ask-crump.html")
        if anchor.get("data-plan") == "free" and anchor.get("data-cta")
    }

    assert {"nav", "hero", "pricing", "closing", "footer"} <= homepage_ctas.keys()
    for name in ("nav", "hero", "pricing", "closing", "footer"):
        query = parse_qs(urlparse(homepage_ctas[name]["href"]).query)
        assert query.get("source") == [name]
        assert query.get("plan") == ["free"]
        assert "signup" not in query


def test_browser_proof_exercises_the_mobile_free_guest_entry_boundary() -> None:
    verifier = (ROOT / "scripts" / "verify-public-account-entry-buttons.cjs").read_text(
        encoding="utf-8"
    )

    assert "homepage Start free still opens registration" in verifier
    assert "new URL(request.url()).pathname === '/api/auth/guest'" in verifier
    assert "guestSessionChecks[0] === false && guestSessionChecks[1] === true" in verifier
    assert "x-installation-id" in verifier.lower()
    assert "new Set(guestAdmissionHeaders.map(row => row.value)).size === 1" in verifier
    assert "#tosModal" in verifier
    assert "successful guest entry incorrectly opens Welcome back" in verifier
    assert "registered-session takeover shows a false guest failure" in verifier
    assert "authenticated guest explicit Sign in issued" in verifier
    assert "stale registered-device hint blocks explicit Free CTA with Welcome back" in verifier
    assert "status: 429" in verifier
    assert "#guestEntryForm" in verifier
    assert "429 incorrectly falls through to Welcome back" in verifier
    assert "you did nothing wrong" in verifier.lower()
    assert "!destination.searchParams.has('signup')" in verifier
    assert "MarketingSignin" in verifier
    assert "MarketingCTA" in verifier
    assert "askcrump.acquisition-placement" in verifier
    assert "rough-idea-launch-plan" in verifier
    assert "viewport: { width: 390, height: 844 }" in verifier
