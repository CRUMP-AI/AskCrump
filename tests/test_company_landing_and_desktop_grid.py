import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_clever_crump_has_a_dedicated_parent_company_landing_page():
    page = read("public/clever-crump.html")
    styles = read("public/clever-crump.css")

    assert "Clever Crump | Independent AI product company" in page
    assert 'rel="canonical" href="https://www.clevercrump.com/"' in page
    assert "We build the part" in page
    assert 'id="ask-crump"' in page
    assert 'id="principles"' in page
    assert "https://www.askcrump.com/app?signup=1&amp;source=clevercrump&amp;plan=free" in page
    assert "public/index.html" not in page
    assert "crump-mark-master.png" not in page
    assert page.count('src="/assets/brand/crump-mark.png"') == 2
    assert ".hero-mark img { position: relative; z-index: 2; width: 38%; height: 38%;" in styles
    assert "overflow-x: hidden" in styles
    assert "@media (max-width: 700px)" in styles
    assert "prefers-reduced-motion" in styles


def test_public_header_actions_stay_single_line_on_narrow_phones():
    product_page = read("public/ask-crump.html")
    product_styles = read("public/landing-5.6.css")
    company_page = read("public/clever-crump.html")
    company_styles = read("public/clever-crump.css")

    assert '/landing-5.6.css?v=5.9.76-truthful-destinations-1' in product_page
    assert ".nav-cta { min-height: 42px; display: inline-flex; flex: 0 0 auto;" in product_styles
    assert "white-space: nowrap" in product_styles
    assert "@media (max-width: 360px)" in product_styles
    assert ".nav-logo { width: 150px; height: 36px; }" in product_styles
    assert ".nav-cta { min-height: 44px; padding-inline: 13px; }" in product_styles

    assert '/clever-crump.css?v=5.9.76-3' in company_page
    assert 'class="header-cta-prefix"' in company_page
    assert ".header-cta { display: inline-flex; flex-shrink: 0; min-height: 44px;" in company_styles
    assert "@media (max-width: 370px)" in company_styles
    assert ".header-cta-prefix { display: none; }" in company_styles


def test_clever_crump_hosts_rewrite_only_the_root_to_the_company_page():
    config = json.loads(read("vercel.json"))
    company_rules = [
        rule
        for rule in config["rewrites"]
        if rule.get("destination") == "/clever-crump"
    ]

    assert {rule["has"][0]["value"] for rule in company_rules} == {
        "clevercrump.com",
        "www.clevercrump.com",
    }
    assert all(rule["source"] == "/" for rule in company_rules)

    ask_root = [
        rule
        for rule in config["rewrites"]
        if rule.get("source") == "/" and rule.get("destination") == "/ask-crump"
    ]
    assert ask_root == [{"source": "/", "destination": "/ask-crump"}]
    assert not (ROOT / "public" / "index.html").exists()
    assert (ROOT / "public" / "ask-crump.html").exists()


def test_public_company_preview_matches_the_current_destination_contract():
    product_page = read("public/ask-crump.html")
    company_page = read("public/clever-crump.html")

    for destination in ("Ask", "Projects", "Create", "Library", "You"):
        assert f"<small>{destination}</small>" in product_page
    assert "Projects → Files" in product_page
    assert "private, dedicated bookshelf" in product_page
    assert "Books + manuscripts" in company_page
    assert "Return + reuse" not in company_page


def test_new_grid_cancels_the_legacy_desktop_sidebar_offset():
    styles = read("public/crump-navigation-5.9.30.css")
    fixture = read("tests/fixtures/desktop-workspace-grid.html")

    assert ".main-content.v1-workspace" in styles
    assert "grid-column: 3" in styles
    assert "margin-left: 0 !important" in styles
    assert "width: 100% !important" in styles
    assert "crump-5.0.css" in fixture
    assert "workspaceRight" in fixture
