from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_intelligence_control_uses_product_native_glasses_icon():
    intelligence = read("public/crump-4.4.js")

    assert "control.id = 'crumpIntelligenceButton'" in intelligence
    assert "control.setAttribute('aria-label', `${assistantName()} intelligence controls`)" in intelligence
    assert "control.title = 'Intelligence'" in intelligence
    assert 'class="crump44-glasses-icon"' in intelligence
    assert 'class="crump44-glasses-icon" width="23" height="23"' in intelligence
    assert 'focusable="false"' in intelligence
    assert '<rect x="3.35" y="8.55" width="6.15" height="5.5" rx="2.2"' in intelligence
    assert 'M9.5 11.15H14.5' in intelligence
    assert 'M3.35 10.95L2.35 10.55M20.65 10.95L21.65 10.55' in intelligence
    assert 'M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M10 14v6' not in intelligence


def test_intelligence_glasses_keeps_existing_button_behavior():
    intelligence = read("public/crump-4.4.js")
    css = read("public/crump-4.4.css")

    assert "control.addEventListener('click', event => {" in intelligence
    assert "togglePanel();" in intelligence
    assert ".crump44-control-button" in css
    assert '.crump44-control-button[aria-expanded="true"]' in css
    assert "color: #d8bd70;" in css


def test_glasses_icon_release_advances_shell_cache():
    sw = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")

    assert "ask-crump-new-body-v1-r123" in sw
    assert "ask-crump-new-body-v1-r20" not in sw
    assert "ask-crump-new-body-v1-r123" in checker
