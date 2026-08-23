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
    assert "ask-crump-new-body-v1-r37" in worker
    assert "/crump-polish-5.6.css" in worker and "/crump-polish-5.6.js" in worker
    assert "crump-polish-5.6.js" in checker


def test_tutorial_is_current_and_no_longer_bootstraps_legacy_runtime():
    tutorial = read("public/onboarding.js")
    assert "crump_tutorial_completed_v5" in tutorial
    assert "Projects" in tutorial
    assert "VIDEO" in tutorial
    assert "Continue scenes" in tutorial
    assert "YOUR LIBRARY" in tutorial
    assert "loadRevampAssets" not in tutorial
    assert "crump-4.3.js" not in tutorial
    assert "event.key === 'Tab'" in tutorial


def test_home_surface_exposes_projects_and_video_without_hiding_core_chat():
    app = read("public/app.html")
    body = read("public/crump-v1-body.js")
    assert 'data-v1-command="focus"' in app
    assert 'data-v1-command="projects"' in app
    assert 'data-v1-command="video"' in app
    assert "case 'projects':" in body and "openProduct('projects')" in body
    assert "case 'video':" in body and "openProduct('video')" in body


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


def test_creation_studio_copy_and_tabs_are_user_facing_and_accessible():
    product = read("public/crump-product-5.3.js")
    polish_js = read("public/crump-polish-5.6.js")
    assert "Projects & Create" in product
    assert "Video engine guide" in product
    assert "Founder Lab active · App credits are bypassed" in product
    assert "role', 'tab'" in polish_js
    assert "aria-selected" in polish_js
    assert "ArrowLeft" in polish_js and "ArrowRight" in polish_js


def test_parent_company_page_reflects_current_product():
    page = read("public/index.html")
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
    assert "Projects & Create" in listing
    assert "Quick, Extendable, and Cinematic" in listing
    assert "manuscripts" in manifest and "video" in manifest and "Projects" in manifest


def test_native_bundle_paths_are_windows_safe():
    native = read("scripts/build-native.mjs")
    assert "fileURLToPath" in native
    assert "entryPoints: [fileURLToPath(" in native
    assert "outfile: fileURLToPath(" in native
    assert "native-entry.js', import.meta.url).pathname" not in native
    assert "native-runtime.js', import.meta.url).pathname" not in native
