from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

CAPABILITY_FREE_CTAS = {
    "ai-project-workspace.html": ("projects-free", "projects"),
    "ai-presentation-maker.html": ("presentation-free", "presentation"),
    "ai-document-generator.html": ("document-free", "document"),
    "ai-resume-builder.html": ("resume-free", "resume"),
    "ai-video-generator.html": ("video-page-free", "video"),
}


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


def test_each_high_intent_capability_page_has_one_attributed_guest_path() -> None:
    for filename, (source, intent) in CAPABILITY_FREE_CTAS.items():
        matching = [
            anchor
            for anchor in _anchors(PUBLIC / filename)
            if anchor.get("data-cta") == source
        ]

        assert len(matching) == 1, (filename, matching)
        anchor = matching[0]
        destination = urlparse(anchor["href"])
        query = parse_qs(destination.query)
        assert destination.path == "/app", (filename, anchor)
        assert query == {
            "source": [source],
            "plan": ["free"],
            "intent": [intent],
        }, (filename, anchor)
        assert anchor.get("data-plan") == "free", (filename, anchor)
        assert "secondary" in anchor.get("class", "").split(), (filename, anchor)
        assert "signup" not in query, (filename, anchor)


def test_capability_free_intent_is_analytics_only_not_a_paid_tool_handoff() -> None:
    controller = (PUBLIC / "auth-controller.js").read_text(encoding="utf-8")
    plan_capture = controller[
        controller.index("function capturePlanIntent()") :
        controller.index("function creationIntentValue(")
    ]
    capture = controller[
        controller.index("function captureCreationIntent()") :
        controller.index("function pendingCreationIntent()")
    ]
    dispatch = controller[
        controller.index("function dispatchPendingCreationIntent()") :
        controller.index("function pendingPlanIntent()")
    ]
    plan_dispatch = controller[
        controller.index("function dispatchPendingPlanIntent()") :
        controller.index("function applyServerSettings(")
    ]

    assert "function isFreeGuestEntryRequest" in controller
    assert "params.get('plan') === 'free' && params.get('signup') !== '1'" in controller
    assert "if (isFreeGuestEntryRequest(params))" in capture
    assert "localStorage.removeItem(CREATION_INTENT_KEY)" in capture
    assert "if (isFreeGuestEntryRequest()) return '';" in dispatch
    assert "if (isFreeGuestEntryRequest(params))" in plan_capture
    assert "discardPendingPlanIntent();" in plan_capture
    assert "if (isFreeGuestEntryRequest())" in plan_dispatch
    assert "discardPendingPlanIntent();" in plan_dispatch


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
    for source in ("projects-free", "presentation-free", "document-free", "resume-free", "video-page-free"):
        assert f"freeCta: '{source}'" in verifier
    assert "hides its Try Ask Crump free path" in verifier
    assert "loses source attribution" in verifier
    assert "has unclear guest-entry copy" in verifier
    assert "capability free entry did not authenticate the minted guest" in verifier
    assert "capability free entry retained an executable creation intent" in verifier
    assert "capability free entry dispatched a paid creation tool" in verifier
    assert "capability free entry retained an executable paid plan intent" in verifier
    assert "capability free entry dispatched a paid plan intent" in verifier
    assert "capability free entry opened the billing modal" in verifier
    assert "askcrump.pending-creation-intent" in verifier
    assert "askcrump.pending-plan-intent" in verifier
    assert "window.__creationIntentEvents" in verifier
    assert "window.__planIntentEvents" in verifier
    assert "capability free entry lost analytics intent in /app" in verifier
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


def test_guest_workspace_has_a_non_destructive_signin_escape_contract() -> None:
    shell = (PUBLIC / "app.html").read_text(encoding="utf-8")
    controller = (PUBLIC / "auth-controller.js").read_text(encoding="utf-8")

    assert 'id="signOutLabel"' in shell
    assert 'id="signOutHelp"' in shell
    assert 'id="guestSigninNotice"' in shell
    assert 'id="returnToGuestLink"' in shell
    assert "free-text-allowance-signin" in controller
    assert "Sign in to another account" in controller
    assert "without ending this guest session" in controller.lower()
    assert "guestAccountSwitchPending" in controller
    assert "this guest conversation will not move with you" in shell.lower()
    assert "save conversation" in shell.lower()
    assert "workspace-signin" in controller
    assert "logout-signin" in controller

    login = controller[
        controller.index("function wireLogin()") :
        controller.index("function wireRegistration()")
    ]
    assert login.index("renderGuestSigninNotice(false)") < login.index(
        "await prepareAuthenticatedWorkspace()"
    )

    logout = controller[
        controller.index("window.logoutUser = async function logoutUser()") :
        controller.index("window.restartTutorial")
    ]
    guest_branch = logout[: logout.index("window.deviceAuth.logout()")]
    assert "isGuestUser" in guest_branch
    assert "signin" in guest_branch.lower()
    assert "window.deviceAuth.logout()" not in guest_branch
    assert "location.replace" in logout


def test_guest_signin_escape_has_isolated_browser_regression_coverage() -> None:
    fixture = (ROOT / "tests" / "fixtures" / "guest-access-journey.html").read_text(
        encoding="utf-8"
    )
    verifier = (ROOT / "scripts" / "verify-guest-access-journey.cjs").read_text(
        encoding="utf-8"
    )

    assert 'id="signOutLabel"' in fixture
    assert 'id="signOutHelp"' in fixture
    assert 'id="guestSigninNotice"' in fixture
    assert 'id="returnToGuestLink"' in fixture
    assert "async function guestSignInEscape" in verifier
    assert "workspace Sign in cleared the guest session" in verifier
    assert "workspace Sign in minted another guest" in verifier
    assert "guest Settings Sign in called logout" in verifier
    assert "returning from Sign in lost the guest session" in verifier
    assert "this guest conversation will not move with you" in verifier.lower()
    assert "async function registeredLogoutToLogin" in verifier
    assert "registered Sign out minted a guest" in verifier
    assert "async function guestSigninPostLoginFailureBoundary" in verifier
    assert "post-login failure left a false guest return action" in verifier
    assert "guestSigninPostLoginFailure: await guestSigninPostLoginFailureBoundary" in verifier
    assert "async function physicalTapLoginPersistence" in verifier
    assert "await submit.tap()" in verifier
    assert "window.__fixture.throwAnalytics = true" in verifier
    assert "Signing in…" in verifier
    assert "390x500 keyboard-sized" in verifier
    assert "Safari 18 mobile user agent and touch input" in verifier
    assert "same browser-context page close/reopen lost the registered session" in verifier
    assert "a known account device silently fell back to a guest" in verifier
    assert "physicalTapLoginPersistence: await physicalTapLoginPersistence" in verifier
    assert "async function productionLoginKeyboardLayout" in verifier
    assert "public/app.html + production styles" in verifier
    assert "productionLoginKeyboardLayout: await productionLoginKeyboardLayout" in verifier
    assert "async function mobileMarketingSigninVisibility" in verifier
    assert "phone homepage hides the Sign in action" in verifier
    assert "mobileMarketingSignin: await mobileMarketingSigninVisibility(browser)" in verifier


def test_phone_homepage_keeps_signin_visible_next_to_free_entry() -> None:
    homepage = (PUBLIC / "ask-crump.html").read_text(encoding="utf-8")
    css = (PUBLIC / "landing-5.6.css").read_text(encoding="utf-8")

    assert 'class="nav-signin"' in homepage
    assert 'href="/app?source=nav-signin&amp;plan=free">Sign in</a>' in homepage
    assert ".nav-signin { display: none; }" not in css
