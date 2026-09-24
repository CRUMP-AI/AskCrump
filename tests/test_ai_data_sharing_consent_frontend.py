from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_consent_guard_is_versioned_early_and_cached_for_web_and_native() -> None:
    asset = "/ai-data-sharing-consent.js?v=5.9.76-ai-data-sharing-consent-1"
    style = "/ai-data-sharing-consent.css?v=5.9.76-ai-data-sharing-consent-1"
    runtime = read("public/runtime-body-v1.js")
    native = read("scripts/build-native.mjs")
    shell = read("public/app.html")
    worker = read("public/sw.js")

    for source in (runtime, native):
        assert source.index(asset) < source.index("/onboarding.js")
        assert source.index(style) < source.index("/billing.css")
    assert 'id="aiDataSharingConsentModal"' in shell
    assert asset in worker
    assert style in worker
    assert "ask-crump-new-body-v1-r259" in worker
    assert "url.pathname === '/ai-data-sharing-consent.js'" in worker
    assert "url.pathname === '/ai-data-sharing-consent.css'" in worker


def test_consent_guard_matches_only_provider_bound_post_shapes() -> None:
    source = read("public/ai-data-sharing-consent.js")
    for path in (
        "/api/chat",
        "/api/voice/synthesize",
        "/api/media/video",
    ):
        assert f"'{path}'" in source
    for fragment in (
        "media\\/video\\/[^/]+\\/continue",
        "code\\/tasks\\/[^/]+\\/run",
        "manuscripts\\/[^/]+\\/(?:blueprint|draft-next)",
        "sections\\/[^/]+\\/draft",
    ):
        assert fragment in source
    for fragment in (
        "manuscripts\\/[^/]+\\/runs",
        "manuscript-runs\\/[^/]+\\/resume",
    ):
        assert fragment in source
    assert "requestMethod(input, init) !== 'POST'" in source
    assert "EXACT_PROVIDER_PATHS.has(path)" in source
    assert "CODE_APPROVAL_PATH.test(path)" in source
    assert "isServerAuthoritativeConsentAction" in source
    assert "preparedRequest.clone()" in source
    assert "if (!await consentRequired(response)) return response" in source
    assert "AI_DATA_SHARING_CONSENT_REQUIRED" in source
    assert "status: 428" in source
    assert "/api/account/ai-data-sharing-consent" in source
    assert "method: 'DELETE'" in source
    assert "method: 'POST'" in source
    assert "body: JSON.stringify({version: CONSENT_VERSION})" in source
    assert "aiDataSharingConsentAt" in source
    assert "aiDataSharingConsentVersion" in source
    assert "aiDataSharingConsentRevokedAt" in source


def test_consent_copy_is_explicit_separate_and_reviewable_from_account_settings() -> None:
    shell = read("public/app.html")
    for phrase in (
        "This permission is separate from accepting the Terms.",
        "your prompt and relevant conversation context",
        "files or images you select",
        "text you choose for voice",
        "video prompts, settings, and references",
        "Autonomous Crump task and repository content",
        "Anthropic",
        "OpenAI",
        "Vercel AI Gateway and Groq",
        "Google Gemini and Veo",
        "Runway",
        "ElevenLabs",
        "Brave Search",
        "OpenWeather",
        "Vercel Sandbox",
        "Nothing is sent until you choose Allow and continue.",
        "Withdrawal applies to future requests",
        "does not undo processing already completed at your direction.",
        "only the data categories described above",
    ):
        assert phrase in shell
    assert 'id="aiDataSharingConsentBtn"' in shell
    assert 'id="aiDataSharingConsentStatus"' in shell
    assert 'href="/legal.html#ai-data-sharing"' in shell
    assert 'role="dialog"' in shell
    assert 'aria-modal="true"' in shell
    assert 'aria-labelledby="aiConsentTitle"' in shell
    assert 'aria-describedby="aiConsentDescription"' in shell


def test_browser_proof_is_private_and_matrix_owned() -> None:
    fixture = read("tests/fixtures/ai-data-sharing-consent.html")
    verifier = read("scripts/verify-ai-data-sharing-consent.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")

    assert "verify-ai-data-sharing-consent.cjs" in matrix
    assert "provider request escaped before a decision" in verifier
    assert "Not now must not POST consent" in verifier
    assert "Not now must not send the provider request" in verifier
    assert "GET polling must remain outside the permission gate" in verifier
    assert "export-only work must not request AI permission" in verifier
    assert "cross-device recovery must retry once" in verifier
    assert "allowed provider resume must retry exactly once" in verifier
    assert "allowed provider manuscript start must retry exactly once" in verifier
    assert "Not now after server 428 must not replay" in verifier
    assert "consecutive 428 responses must stop after one Request-object replay" in verifier
    assert "Request-object replay must preserve the exact JSON body bytes" in verifier
    assert "aiDataSharingConsentRevokedAt" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture.lower()
