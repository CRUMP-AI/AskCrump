from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class _CtaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "a" and "data-cta" in values:
            self.links.append(values)


def test_every_capability_cta_preserves_the_promised_creation_intent():
    pages = {
        "public/ai-document-generator.html": "document",
        "public/ai-presentation-maker.html": "presentation",
        "public/ai-resume-builder.html": "resume",
        "public/ai-video-generator.html": "video",
        "public/ai-project-workspace.html": "projects",
    }

    for relative, expected_intent in pages.items():
        parser = _CtaParser()
        parser.feed(read(relative))
        app_links = [link for link in parser.links if urlparse(link["href"]).path == "/app"]
        assert len(app_links) >= 5, relative
        for link in app_links:
            query = parse_qs(urlparse(link["href"]).query)
            assert query.get("intent") == [expected_intent], (relative, link)


def test_marketing_analytics_keeps_only_the_allowlisted_intent_label():
    landing = read("public/landing.js")

    assert "destination.searchParams.get('intent')" in landing
    assert "intent: creationIntent" in landing
    assert "safeSource(destination.searchParams.get('intent'), creationIntent)" in landing


def test_creation_intent_survives_auth_without_storing_user_content():
    controller = read("public/auth-controller.js")
    intent_slice = controller[
        controller.index("function creationIntentValue") :
        controller.index("function pendingPlanIntent")
    ]

    assert "askcrump.pending-creation-intent" in controller
    assert "CREATION_INTENT_TTL_MS = 24 * 60 * 60 * 1000" in controller
    assert "new Set(['document', 'presentation', 'resume', 'video', 'projects'])" in controller
    assert "captureCreationIntent();" in controller
    assert "dispatchPendingCreationIntent();" in controller
    assert "crump:body-runtime-ready" in intent_slice
    assert "crump:creation-intent-consumed" in intent_slice
    assert "localStorage.removeItem(CREATION_INTENT_KEY)" in intent_slice
    for forbidden in ("prompt", "filename", "email", "message", "response", "chatId"):
        assert forbidden not in intent_slice


def test_creation_intent_opens_the_exact_non_generating_workspace():
    navigation = read("public/crump-navigation-5.9.30.js")
    handler = navigation[
        navigation.index("function openCreateTool") :
        navigation.index("function openAsk")
    ]

    assert "CREATION_HANDOFF_INTENTS = new Set(['document', 'presentation', 'resume', 'video', 'projects'])" in navigation
    assert "if (action === 'projects')" in handler
    assert "openProjects();" in handler
    assert "window.CrumpDocumentStudio?.open?.()" in handler
    assert "window.CrumpDocumentStudio?.select?.('pptx'" in handler
    assert "window.CrumpDocumentStudio?.select?.('docx'" in handler
    assert "job requirements you want to match…', 'resume')" in handler
    assert "window.CrumpProduct53?.open?.('manuscripts')" in handler
    assert "openVideo();" in handler
    assert "CreationIntentContinued" in handler
    assert "crump:creation-intent-consumed" in handler
    assert "fetch(" not in handler


def test_real_controller_fixture_covers_the_authenticated_handoff():
    fixture = read("tests/fixtures/creation-intent-handoff.html")

    assert "/public/crump-navigation-5.9.30.js" in fixture
    assert "/public/auth-controller.js" in fixture
    assert "authenticated:true" in fixture
    assert "get('auth') === '0'" in fixture
    assert "askcrump.pending-creation-intent" in fixture
    assert "fixtureCalls" in fixture
    assert "fixtureErrors" in fixture
    assert "format, placeholder, purpose" in fixture


def test_campaign_attribution_fixture_uses_real_runtime_without_production_writes():
    fixture = read("tests/fixtures/campaign-attribution-handoff.html")

    assert '/public/landing.js?v=campaign-attribution-fixture' in fixture
    assert 'data-cta="presentation-hero"' in fixture
    assert 'data-cta="resume-hero"' in fixture
    assert 'data-cta="resume-nav-signin"' in fixture
    assert "askcrump.acquisition-source" in fixture
    assert "window.__fixture.events" in fixture
    assert "MarketingCTA" not in fixture
    assert "MarketingSignin" not in fixture
    assert "fetch(" not in fixture
    assert "askcrump.com" not in fixture
    assert "https://" not in fixture


def test_referral_landing_fixture_preserves_only_the_fixed_share_placement():
    fixture = read("tests/fixtures/referral-landing-handoff.html")

    assert '/public/landing.js?v=referral-landing-fixture' in fixture
    assert 'data-cta="hero"' in fixture
    assert 'data-cta="nav-signin"' in fixture
    assert "askcrump.acquisition-source" in fixture
    assert "askcrump.acquisition-placement" in fixture
    assert "fixtureStoredPlacement" in fixture
    assert "window.__fixture.events" in fixture
    assert "MarketingCTA" not in fixture
    assert "MarketingSignin" not in fixture
    assert "fetch(" not in fixture
    assert "askcrump.com" not in fixture
    assert "https://" not in fixture


def test_profile_link_fixture_preserves_only_categorical_channel_and_placement():
    fixture = read("tests/fixtures/profile-link-attribution-handoff.html")

    assert '/public/landing.js?v=profile-link-attribution-fixture' in fixture
    assert 'data-cta="hero"' in fixture
    assert 'data-cta="nav-signin"' in fixture
    assert "askcrump.acquisition-source" in fixture
    assert "askcrump.acquisition-placement" in fixture
    assert "fixtureStoredPlacement" in fixture
    assert "window.__fixture.events" in fixture
    assert "MarketingCTA" not in fixture
    assert "MarketingSignin" not in fixture
    assert "fetch(" not in fixture
    assert "askcrump.com" not in fixture
    assert "https://" not in fixture


def test_resume_purpose_survives_send_retry_and_server_packaging():
    studio = read("public/crump-5.0.js")
    route = read("backend/routes/chat.py")
    sync_patch = read("backend/crump52_patches.py")

    assert "documentPurpose: null" in studio
    assert "state.documentPurpose = purpose || null" in studio
    assert "body.artifactPurpose = state.documentPurpose" in studio
    assert "{artifactPurpose:state.documentPurpose}" in studio
    assert "state.documentPurpose = String(purpose || '').toLowerCase() === 'resume' ? 'resume' : null" in studio
    assert "artifacts.normalize_purpose(request_payload.get('artifactPurpose'))" in route
    assert "artifactPurpose', 'needsSearch'" in route
    assert "purpose=artifact_purpose" in route
    assert '"artifactFormat", "artifactPurpose"' in sync_patch
    assert 'clean_meta[key] = "resume"' in sync_patch
