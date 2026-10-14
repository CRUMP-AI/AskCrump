from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v1_header_brand_is_not_replaced_by_legacy_shells():
    legacy_43 = read("public/crump-4.3.js")
    legacy_50 = read("public/crump-5.0.js")

    assert "if (document.body.classList.contains('crump-v1-body')) return;" in legacy_43
    assert "!document.body.classList.contains('crump-v1-body')" in legacy_50


def test_v1_brand_guard_reuses_the_initial_header_image():
    body = read("public/crump-v1-body.js")

    assert "const existing = host.querySelector(':scope > img');" in body
    assert "existing.classList.add('v1-header-logo', 'v1-body-header-logo');" in body
    assert "existing.loading = 'eager';" in body
    assert "existing.decoding = 'sync';" in body
    assert "existing.fetchPriority = 'high';" in body


def test_visible_library_brand_is_also_normalized_as_a_critical_image():
    body = read("public/crump-v1-body.js")

    assert "const existing = host.querySelector(':scope > .v1-library-logo');" in body
    assert "'Ask Crump',\n      true," in body
    assert "horizontalLight: '/assets/brand/crump-shell-lockup-light.webp?v=5.9.76-shell-no-tagline-1'" in body


def test_workspace_positioning_asset_cannot_overwrite_the_shell_lockup():
    generator = read("scripts/generate_workspace_brand_asset.py")

    assert 'TAGLINE = "AN AI WORKSPACE FOR WORK THAT CONTINUES"' in generator
    assert 'SOURCE_WORDMARK = ROOT / "public" / "assets" / "brand" / "crump-horizontal-light.png"' in generator
    assert 'WORDMARK = ROOT / "public" / "assets" / "brand" / "crump-workspace-lockup-light.png"' in generator
    assert 'crump-shell-lockup-light' not in generator


def test_shell_lockup_uses_exact_paint_boxes():
    body = read("public/crump-v1-body.css")

    assert "width: 200px;" in body
    assert "height: 50px;" in body
    assert "aspect-ratio: 4 / 1;" in body
    assert "width: 176px;" in body
    assert "height: 44px;" in body


def test_conversation_drawer_preserves_the_official_gold_lockup() -> None:
    app = read("public/app.html")
    styles = read("public/crump-design-pass.css")

    assert 'class="v1-library-logo"' in app
    assert '/assets/brand/crump-shell-lockup-light.webp?v=5.9.76-shell-no-tagline-1' in app
    logo_rule = styles[styles.index("body.crump-v1-body .v1-library-logo {") :]
    logo_rule = logo_rule[: logo_rule.index("}")]
    assert "filter: none !important;" in logo_rule
    assert "brightness(" not in logo_rule
    assert "#171a1f !important;" in styles
    assert "color: #f0ece3 !important;" in styles
    assert 'html[data-theme="light"] body.crump-v1-body .v1-auth-mobile-brand' in styles
    assert 'html[data-theme="light"] body.crump-v1-body .v1-about-signature' in styles


def test_initial_and_final_desktop_rail_widths_match_before_runtime_handoff():
    initial_shell = read("public/crump-v1-body.css")
    final_navigation = read("public/crump-navigation-5.9.30.css")

    assert "--ac-rail: 94px;" in initial_shell
    assert "--ac-rail: 94px;" in final_navigation
    assert "--ac-rail: 74px;" not in initial_shell
