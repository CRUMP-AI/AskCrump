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
    assert "overflow-x: hidden" in styles
    assert "@media (max-width: 700px)" in styles
    assert "prefers-reduced-motion" in styles


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


def test_new_grid_cancels_the_legacy_desktop_sidebar_offset():
    styles = read("public/crump-navigation-5.9.30.css")
    fixture = read("tests/fixtures/desktop-workspace-grid.html")

    assert ".main-content.v1-workspace" in styles
    assert "grid-column: 3" in styles
    assert "margin-left: 0 !important" in styles
    assert "width: 100% !important" in styles
    assert "crump-5.0.css" in fixture
    assert "workspaceRight" in fixture
