from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")

def test_app_shell_does_not_block_page_level_pinch_zoom():
    script = read("public/crump-v1-stability.js")
    assert "installViewportGesturePolicy" not in script
    assert "gesturestart" not in script
    assert "gesturechange" not in script
    assert "blockViewportPinch" not in script
    assert "event.touches" not in script

def test_shell_prevents_horizontal_drift_while_allowing_pinch_zoom():
    css = read("public/crump-v1-stability.css")
    assert "overscroll-behavior-x: none;" in css
    assert "overflow-x: hidden;" in css
    assert "touch-action: pan-y pinch-zoom;" in css
    assert "touch-action: pan-x pan-y;" not in css

def test_viewport_allows_accessibility_zoom_at_the_installed_app_scale():
    app = read("public/app.html")
    assert 'name="viewport"' in app
    assert "width=device-width, initial-scale=1.0" in app
    assert "maximum-scale" not in app
    assert "user-scalable=no" not in app
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
    library_style = "['/crump-library-5.7.css', 'crumplibrary57']"
    stability_style = "['/crump-v1-stability.css', 'crumpv1stability']"
    assert library_style in runtime
    assert stability_style in runtime
    assert runtime.index(library_style) < runtime.index(stability_style)
    assert runtime.index("/crump-v1-stability.css") < runtime.index("/crump-navigation-5.9.30.css")
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
    assert "ask-crump-new-body-v1-r153" in sw
    assert "ask-crump-new-body-v1-r22" not in sw
    assert "ask-crump-new-body-v1-r153" in checker
