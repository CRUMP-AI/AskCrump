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

    assert '<div class="v1-mode-strip" hidden aria-hidden="true">' in shell
    assert 'id="crump53ToolTrigger"' not in product
    assert 'id="crump53ToolMenu"' not in product
    assert "enhanceToolMenu" not in product
    assert "retireLegacyToolStrip(strip);" in product
    assert "strip.hidden = true;" in product
    assert ".crump53-tool-shell" not in product_styles
    assert ".crump53-tool-menu" not in product_styles
    assert ".v1-mode-strip[hidden] { display: none !important; }" in product_styles

    # Every capability still has one intentional, live destination.
    for action in ("document", "presentation", "image", "manuscript", "video"):
        assert f"createCard('{action}'" in navigation
    assert 'id="crumpCodeCreateSlot" class="crump-code-create-slot" hidden' in navigation
    assert "title.textContent = 'Intelligence';" in intelligence
    assert "Research in Intelligence, creation in Create, and files on the + button." in product
    assert "forwardClick('attachBtn')" in body


def test_retired_tool_assets_are_cache_versioned_atomically():
    version = "5.9.76-destination-tools-1"
    shell = read("public/app.html")
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    native = read("scripts/build-native.mjs")

    assert f"/runtime-body-v1.js?v={version}" in shell
    assert f"/runtime-body-v1.js?v={version}" in worker
    for asset in ("crump-product-5.3.css", "crump-product-5.3.js"):
        versioned = f"/{asset}?v={version}"
        assert versioned in runtime
        assert versioned in worker
        assert versioned in native
    assert "ask-crump-new-body-v1-r160" in worker
