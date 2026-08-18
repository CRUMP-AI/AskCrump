from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")

def test_app_shell_blocks_page_level_pinch_without_disabling_image_zoom():
    script = read("public/crump-v1-stability.js")
    assert "function installViewportGesturePolicy()" in script
    assert "function isImageZoomSurface(target)" in script
    assert "target?.closest?.('.crump50-lightbox')" in script
    assert "document.addEventListener('gesturestart', blockViewportPinch, { passive: false });" in script
    assert "document.addEventListener('gesturechange', blockViewportPinch, { passive: false });" in script
    assert "document.addEventListener('touchmove', event => {" in script
    assert "(event.touches?.length || 0) < 2" in script
    assert "if (isImageZoomSurface(event.target)) return;" in script
    assert "event.preventDefault();" in script
    assert "installViewportGesturePolicy();" in script

def test_shell_prevents_horizontal_drift_and_double_tap_zoom():
    css = read("public/crump-v1-stability.css")
    assert "overscroll-behavior-x: none;" in css
    assert "overflow-x: hidden;" in css
    assert "touch-action: manipulation;" in css
    assert "body.crump-v1-body .crump50-lightbox" in css
    assert "touch-action: pan-x pan-y pinch-zoom;" in css

def test_viewport_is_not_hard_locked_so_image_lightbox_can_keep_native_pinch():
    app = read("public/app.html")
    assert 'name="viewport"' in app
    assert "width=device-width, initial-scale=1.0, viewport-fit=cover" in app
    assert "user-scalable=no" not in app
    assert "maximum-scale=1" not in app

def test_existing_image_viewer_remains_the_zoom_exception():
    product = read("public/crump-5.0.js")
    assert "function showLightbox(file, url)" in product
    assert "box.className = 'crump50-lightbox'" in product
    assert "img.alt = file?.name || 'Generated image'" in product

def test_mobile_zoom_policy_advances_shell_cache():
    sw = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")
    assert "ask-crump-new-body-v1-r23" in sw
    assert "ask-crump-new-body-v1-r22" not in sw
    assert "ask-crump-new-body-v1-r23" in checker
