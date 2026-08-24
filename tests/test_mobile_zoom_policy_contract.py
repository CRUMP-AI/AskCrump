from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")

def test_app_shell_blocks_page_level_pinch_everywhere():
    script = read("public/crump-v1-stability.js")
    assert "function installViewportGesturePolicy()" in script
    assert "document.addEventListener('gesturestart', blockViewportPinch, { passive: false });" in script
    assert "document.addEventListener('gesturechange', blockViewportPinch, { passive: false });" in script
    assert "document.addEventListener('touchmove', event => {" in script
    assert "(event.touches?.length || 0) < 2" in script
    assert "event.preventDefault();" in script
    assert "installViewportGesturePolicy();" in script
    assert "isImageZoomSurface" not in script

def test_shell_prevents_horizontal_drift_and_double_tap_zoom():
    css = read("public/crump-v1-stability.css")
    assert "overscroll-behavior-x: none;" in css
    assert "overflow-x: hidden;" in css
    assert "touch-action: pan-x pan-y;" in css
    assert "pinch-zoom" not in css

def test_viewport_is_hard_locked_to_the_installed_app_scale():
    app = read("public/app.html")
    assert 'name="viewport"' in app
    assert "width=device-width, initial-scale=1.0" in app
    assert "maximum-scale=1.0" in app
    assert "user-scalable=no" in app
    assert "viewport-fit=cover" in app

def test_every_mobile_editor_meets_the_ios_no_focus_zoom_threshold():
    css = read("public/crump-v1-stability.css")
    runtime = read("public/runtime-body-v1.js")
    product = read("public/crump-product-5.3.js")
    assert '@media (hover: none) and (pointer: coarse), (max-width: 820px)' in css
    assert 'body.crump-v1-body input:not([type="button"])' in css
    assert "body.crump-v1-body textarea" in css
    assert "body.crump-v1-body select" in css
    assert 'body.crump-v1-body [contenteditable="true"]' in css
    assert "font-size: 16px !important;" in css
    assert "await loadStyle('/crump-library-5.7.css', 'crumplibrary57');\n    // Keep the stability layer last." in runtime
    assert "await loadStyle('/crump-v1-stability.css', 'crumpv1stability');" in runtime
    assert 'id="crump53VideoPrompt" class="crump53-textarea"' in product
    assert 'id="crump53ContinuePrompt" class="crump53-textarea"' in product

def test_mobile_header_controls_share_the_same_safe_area_centerline():
    css = read("public/crump-v1-stability.css")
    paired_selector = "body.crump-v1-body :is(.v1-mobile-menu,#crumpIntelligenceButton,.crump44-control-button)"
    assert css.count(paired_selector) == 2
    assert "top: calc(env(safe-area-inset-top) + 13px) !important;" in css
    assert "top: calc(env(safe-area-inset-top) + 14px) !important;" in css
    assert "position: absolute !important;" in css
    assert "left: max(10px,env(safe-area-inset-left)) !important;" in css

def test_mobile_zoom_policy_advances_shell_cache():
    sw = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")
    assert "ask-crump-new-body-v1-r47" in sw
    assert "ask-crump-new-body-v1-r22" not in sw
    assert "ask-crump-new-body-v1-r47" in checker
