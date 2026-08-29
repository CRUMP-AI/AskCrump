from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_desktop_rail_names_conversations_in_plain_language():
    shell = read("public/app.html")
    product = read("public/crump-product-5.3.js")

    assert '<span class="v1-rail-label">New</span>' in shell
    assert '<span class="v1-rail-label">Chats</span>' in shell
    assert '<span class="v1-rail-label">Projects</span>' in product
    assert 'aria-controls="sidebar" aria-expanded="true"' in shell


def test_conversation_library_control_exposes_and_tracks_its_state():
    body = read("public/crump-v1-body.js")
    styles = read("public/crump-v1-body.css")

    assert "function syncLibraryControl()" in body
    assert "control.setAttribute('aria-expanded', expanded ? 'true' : 'false')" in body
    assert "sidebar.setAttribute('aria-hidden', expanded ? 'false' : 'true')" in body
    assert "sidebar.removeAttribute('inert')" in body
    assert "sidebar.setAttribute('inert', '')" in body
    assert "sidebar.dataset.v1InertRevision" in body
    assert "new MutationObserver(syncLibraryControl)" in body
    assert 'body.crump-v1-body .v1-rail-label {' in styles
    assert 'body.crump-v1-body .v1-rail-button[aria-expanded="true"]' in styles


def test_browser_fixture_uses_the_real_rail_assets_without_network_writes():
    fixture = read("tests/fixtures/conversation-library-discovery.html")

    assert '/public/crump-v1-body.css' in fixture
    assert '/public/crump-v1-body.js' in fixture
    assert '/public/assets/brand/crump-shell-lockup-light.png' in fixture
    assert 'data-v1-command="library"' in fixture
    assert '<span class="v1-rail-label">Chats</span>' in fixture
    assert "fetch(" not in fixture
