from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_authenticated_home_has_one_semantic_document_studio_entry() -> None:
    app = read("public/app.html")
    launchpad_start = app.index('<section id="v1Launchpad"')
    launchpad_end = app.index("</section>", launchpad_start)
    launchpad = app[launchpad_start:launchpad_end]

    assert launchpad.count("data-home-document-entry") == 1
    assert 'type="button" class="v1-launch-card" data-home-document-entry' in launchpad
    assert 'aria-labelledby="v1LaunchDocumentTitle"' in launchpad
    assert 'aria-describedby="v1LaunchDocumentDescription"' in launchpad
    assert 'id="v1LaunchDocumentTitle">Create a document</strong>' in launchpad
    assert "Word, PDF, presentation, spreadsheet, or text file" in launchpad
    assert launchpad.count('class="v1-launch-card') == 5
    assert [f'data-v1-index="0{index}"' in launchpad for index in range(1, 6)] == [True] * 5


def test_home_entry_invokes_only_the_authoritative_document_studio_open_api() -> None:
    entry = read("public/home-document-entry.js")

    assert "window.CrumpDocumentStudio.open();" in entry
    assert "data-home-document-entry" in entry
    assert "homeDocumentEntryWired" in entry
    assert "crump:body-runtime-ready" in entry
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "CrumpAnalytics",
        "CrumpChatTransport",
        "credit",
        "localStorage",
        "sessionStorage",
        "sendMessage",
        "fileInput",
        ".select(",
    ):
        assert forbidden not in entry


def test_open_is_not_misclassified_as_a_measured_starter_or_generator() -> None:
    app = read("public/app.html")
    body = read("public/crump-v1-body.js")
    launchpad_start = app.index('<section id="v1Launchpad"')
    launchpad_end = app.index("</section>", launchpad_start)
    launchpad = app[launchpad_start:launchpad_end]

    assert 'data-v1-command="document"' not in launchpad
    allowlist = body[body.index("const STARTER_INTENTS"):body.index("function command(command)")]
    assert "'document'" not in allowlist


def test_existing_studio_preserves_format_choice_until_the_intentional_send() -> None:
    studio = read("public/crump-5.0.js")
    options = studio[studio.index("function showDocumentOptions()"):
                     studio.index("function openCamera()")]
    request = studio[studio.index("function buildRequestBody("):
                     studio.index("async function ensureUsage(expectedOwnerId")]
    export = studio[studio.index("window.CrumpDocumentStudio = Object.freeze"):
                    studio.index("window.CrumpImageStudio = Object.freeze")]

    assert "['docx','Word','DOCX']" in options
    assert "['pptx','PowerPoint','PPTX']" in options
    assert "state.documentFormat = value" in options
    assert "state.documentPurpose = null" in options
    assert "input.focus({preventScroll: true})" in studio
    assert "input.value" not in options
    assert "body.artifactFormat = state.documentFormat" in request
    assert "body.artifactPurpose = state.documentPurpose" in request
    assert "open: showDocumentOptions" in export


def test_document_home_asset_is_atomic_for_web_and_pwa_updates() -> None:
    app = read("public/app.html")
    worker = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")
    returning_load = read("scripts/verify-service-worker-returning-load.cjs")
    expected = "/home-document-entry.js?v=5.9.76-home-document-entry-1"

    assert app.count(expected) == 1
    assert worker.count(expected) == 1
    assert "ask-crump-new-body-v1-r280-login-workspace-recovery-2" in worker
    assert "url.pathname === '/home-document-entry.js'" in worker
    assert "home-document-entry.js" in checker
    assert "homeDocumentEntryVersion" in checker
    assert expected in returning_load


def test_browser_proofs_cover_side_effect_payload_and_responsive_contracts() -> None:
    first_action = read("scripts/verify-first-action-browser.cjs")
    delivery = read("scripts/verify-conversational-document-delivery.cjs")
    delivery_server = read("scripts/serve-conversational-document-delivery-fixture.py")

    assert "Create a document" in first_action
    assert "window.__documentStudioOpens" in first_action
    assert "preservedDraft" in first_action
    assert "apiRequests" in first_action
    assert "window.__sendClicks" in first_action
    assert "documentEntryLayout" in first_action
    for width in (1280, 768, 390):
        assert f"width: {width}" in first_action
    for theme in ("light", "dark"):
        assert f"'{theme}'" in first_action
    assert "crump-v1-keyboard-visible" in first_action
    assert "artifactFormat" in delivery
    assert "preservedDraft" in delivery
    assert "fixtureStateBeforeOpen" in delivery
    assert "pageRequestsBeforeOpen" in delivery
    assert '"subscription_tier": "professional"' in delivery_server
    assert '"subscription_status": "active"' in delivery_server
    assert 'user_tier="professional"' in delivery_server
