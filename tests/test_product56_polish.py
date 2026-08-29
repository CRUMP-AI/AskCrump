from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_56_polish_layer_is_last_on_web_and_native():
    runtime = read("public/runtime-body-v1.js")
    native = read("scripts/build-native.mjs")
    worker = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")
    for source in (runtime, native):
        assert "/crump-4.3.css" in source and "/crump-4.3.js" in source
        assert source.index("/crump-4.3.js") < source.index("/crump-4.4.js")
        assert source.index("/crump-product-5.3.1.js") < source.index("/crump-polish-5.6.js")
        assert "/crump-polish-5.6.css" in source
    assert "ask-crump-new-body-v1-r114" in worker
    assert "/crump-polish-5.6.css" in worker and "/crump-polish-5.6.js" in worker
    assert "crump-polish-5.6.js" in checker


def test_tutorial_is_current_and_no_longer_bootstraps_legacy_runtime():
    tutorial = read("public/onboarding.js")
    styles = read("public/onboarding.css")
    polish = read("public/crump-polish-5.6.js")
    assert "crump_tutorial_completed_v6" in tutorial
    for destination in ("Ask", "Projects", "Create", "Library", "You"):
        assert f"destination: '{destination}'" in tutorial
    assert "Conversation history remains in Chats." in tutorial
    assert "Nothing generates until you review the setup and send the request." in tutorial
    assert "tutorial-destination-map" in tutorial and ".tutorial-destination-map" in styles
    assert "aria-current', 'step'" in tutorial
    assert "Replay workspace guide" in polish
    assert "Review Ask, Projects, Create, Library, and You." in polish
    assert "loadRevampAssets" not in tutorial
    assert "crump-4.3.js" not in tutorial
    assert "event.key === 'Tab'" in tutorial
    assert "if (document.getElementById('v1Launchpad')) return;" in tutorial


def test_authenticated_workspace_stays_behind_a_bounded_runtime_gate():
    page = read("public/app.html")
    styles = read("public/crump-v1-body.css")
    controller = read("public/auth-controller.js")
    runtime = read("public/runtime-body-v1.js")

    assert 'id="v1RuntimeGate"' in page
    assert "Opening your workspace" in page
    assert ".v1-runtime-gate" in styles
    assert "holdWorkspaceForRuntime();" in controller
    assert "shell?.setAttribute('inert', '');" in controller
    assert "window.addEventListener('crump:body-runtime-ready', releaseWorkspaceRuntimeGate" in controller
    assert "window.setTimeout(releaseWorkspaceRuntimeGate, 5000)" in controller
    assert "window.CrumpWorkspaceRuntime = Object.freeze({load});" in runtime
    assert "await prepareAuthenticatedWorkspace();" in controller
    assert "window.addEventListener('load'" not in runtime


def test_five_destination_tutorial_fixture_uses_production_assets():
    fixture = read("tests/fixtures/five-destination-tutorial.html")

    assert "/public/onboarding.css" in fixture
    assert "/public/onboarding.js?fixture=five-destinations" in fixture
    assert "window.tutorial.start({force: true})" in fixture


def test_home_surface_exposes_projects_and_video_without_hiding_core_chat():
    app = read("public/app.html")
    body = read("public/crump-v1-body.js")
    assert 'data-v1-command="focus"' in app
    assert 'data-v1-command="projects"' in app
    assert 'data-v1-command="video"' in app
    assert "case 'projects':" in body and "openProduct('projects')" in body
    assert "case 'video':" in body and "openProduct('video')" in body


def test_clean_start_offers_a_private_recent_work_continuation():
    app = read("public/app.html")
    body = read("public/crump-v1-body.js")
    tracker = body[
        body.index("function recentWorkChat"):
        body.index("function command(command)")
    ]

    assert 'id="v1RecentWork"' in app
    assert 'id="v1RecentWorkButton"' in app
    assert 'id="v1RecentWorkName"' in app
    assert 'id="v1RecentWorkHint"' in app
    assert "Continue recent work" in app
    assert "chat.messages.length > 0" in tracker
    assert "recent?.title" in tracker
    assert "rawName.slice(0, 72)" in tracker
    assert "nameNode.textContent = recentName" in tracker
    assert "Continue where you left off." in tracker
    assert "window.loadChat(chatId)" in tracker
    assert "'RecentWorkResumed'" in tracker
    assert "eventKey: 'recent-work-resumed'" in tracker
    assert "source: 'launchpad'" in tracker
    analytics_call = tracker[tracker.index("CrumpAnalytics"):tracker.index("window.loadChat")]
    assert "chatId" not in analytics_call
    assert "title" not in analytics_call.lower()
    assert "content" not in analytics_call.lower()


def test_video_result_actions_share_one_button_system():
    product = read("public/crump-product-5.3.js")
    polish = read("public/crump-polish-5.6.css")
    assert "crump53-video-result-actions" in product
    assert "crump53-button-link" in product
    assert "Download video</a>" in product
    assert "Open Library" in product
    assert "Saved to Library" in product
    assert "text-decoration: none !important" in polish
    assert "a.crump53-button" in polish


def test_creation_surfaces_are_separate_and_accessible():
    product = read("public/crump-product-5.3.js")
    polish_js = read("public/crump-polish-5.6.js")
    for label in ("Ask Crump Projects", "Ask Crump Manuscripts", "Ask Crump Video Studio", "Ask Crump Library"):
        assert label in product
    assert "Video engine guide" in product
    assert "Founder Lab active · App credits are bypassed" in product
    assert "role', 'region'" in polish_js
    assert "aria-hidden" in polish_js
    assert "role', 'tab'" not in polish_js
    assert "aria-selected" not in polish_js
    assert "ArrowLeft" not in polish_js and "ArrowRight" not in polish_js


def test_parent_company_page_reflects_current_product():
    page = read("public/ask-crump.html")
    css = read("public/landing-5.6.css")
    assert "ASK CRUMP 5.9" in page
    assert "AI should help you" in page and "finish things." in page
    assert "Projects" in page
    assert "THE CRUMP VIDEO ENGINE" in page
    assert "EXTENDABLE" in page and "CINEMATIC" in page
    assert "HOW CLEVER CRUMP BUILDS" in page
    assert "Built in Savannah" in page
    assert ".product-stage" in css


def test_store_and_pwa_copy_match_current_creation_surface():
    listing = read("docs/STORE_LISTING_COPY.md")
    manifest = read("public/manifest.json")
    assert "scene continuation" in listing
    assert "Ask, Projects, Create, Library, and You" in listing
    assert "guided research inside Ask" in listing
    assert "Open Projects and resume" in listing
    assert "Open Create and test" in listing
    assert "Open Library and verify" in listing
    assert "Open You → Settings" in listing
    assert "Saved Library" not in listing
    assert "Quick, Extendable, and Cinematic" in listing
    assert "manuscripts" in manifest and "video" in manifest and "Projects" in manifest


def test_native_bundle_paths_are_windows_safe():
    native = read("scripts/build-native.mjs")
    assert "fileURLToPath" in native
    assert "entryPoints: [fileURLToPath(" in native
    assert "outfile: fileURLToPath(" in native
    assert "native-entry.js', import.meta.url).pathname" not in native
    assert "native-runtime.js', import.meta.url).pathname" not in native
