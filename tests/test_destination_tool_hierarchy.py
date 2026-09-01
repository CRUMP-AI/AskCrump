from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_redundant_tools_dropdown_is_retired_without_removing_real_capabilities():
    shell = read("public/app.html")
    product = read("public/crump-product-5.3.js")
    product_styles = read("public/crump-product-5.3.css")
    navigation = read("public/crump-navigation-5.9.30.js")
    intelligence = read("public/crump-4.4.js")
    body = read("public/crump-v1-body.js")

    assert 'v1-mode-strip' not in shell
    assert 'imageQuickAction' not in shell
    assert 'searchQuickAction' not in shell
    assert 'codeQuickAction' not in shell
    assert 'id="crump53ToolTrigger"' not in product
    assert 'id="crump53ToolMenu"' not in product
    assert "enhanceToolMenu" not in product
    assert "retireLegacyToolStrip" not in product
    assert "document.querySelector('.v1-mode-strip')" not in product
    assert ".crump53-tool-shell" not in product_styles
    assert ".crump53-tool-menu" not in product_styles

    # Every capability still has one intentional, live destination.
    for action in ("document", "presentation", "image", "manuscript", "video"):
        assert f"createCard('{action}'" in navigation
    assert "data-crump-code-destination hidden" in navigation
    assert "createCard('code'" not in navigation
    assert "title.textContent = 'Intelligence';" in intelligence
    assert "forwardClick('attachBtn')" in body
    assert "window.triggerWebSearch?.()" in body
    assert "window.CrumpImageStudio.open()" in body


def test_retired_tool_assets_are_cache_versioned_atomically():
    version = "5.9.76-intelligence-architecture-1"
    loader_version = "5.9.76-continuity-action-1"
    product_style_version = "5.9.76-file-library-window-1"
    product_script_version = "5.9.76-file-library-window-1"
    shell = read("public/app.html")
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    native = read("scripts/build-native.mjs")

    assert f"/runtime-body-v1.js?v={loader_version}" in shell
    assert f"/runtime-body-v1.js?v={loader_version}" in worker
    for asset, asset_version in (
        ("crump-product-5.3.css", product_style_version),
        ("crump-product-5.3.js", product_script_version),
    ):
        versioned = f"/{asset}?v={asset_version}"
        assert versioned in runtime
        assert versioned in worker
        assert versioned in native
    assert "ask-crump-new-body-v1-r189" in worker
