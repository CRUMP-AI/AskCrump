from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_settings_and_billing_keep_one_primary_sidebar_destination_each():
    html = read_public("app.html")
    cleanup = read_public("crump-navigation-5.2.5.js")
    cleanup_css = read_public("crump-navigation-5.2.5.css")

    # The labeled sidebar rows remain the single user-facing destinations.
    assert html.count('id="settingsBtn"') == 1
    assert html.count('id="upgradeBtnSidebar"') == 1
    assert "<span>Settings</span>" in html
    assert "<span>Plan & credits</span>" in html

    # The final navigation layer removes the legacy icon-only rail duplicates.
    assert '.v1-rail [data-v1-command="settings"]' in cleanup
    assert '.v1-rail [data-v1-command="billing"]' in cleanup
    assert ".forEach(node => node.remove())" in cleanup
    assert "document.querySelector('.v1-rail .v1-rail-spacer')?.remove();" in cleanup

    # Defense in depth prevents those legacy controls flashing before JS cleanup.
    assert 'body.crump-v1-body .v1-rail [data-v1-command="settings"]' in cleanup_css
    assert 'body.crump-v1-body .v1-rail [data-v1-command="billing"]' in cleanup_css
    assert "display: none !important;" in cleanup_css


def test_footer_normalization_removes_decorative_destination_icons():
    cleanup = read_public("crump-navigation-5.2.5.js")

    assert "normalizeFooterDestination('settingsBtn', 'Settings')" in cleanup
    assert "normalizeFooterDestination('upgradeBtnSidebar', 'Plan & credits')" in cleanup
    assert "button.querySelector(':scope > svg')?.remove();" in cleanup


def test_credit_badge_remains_attached_and_mobile_destination_click_closes_drawer():
    billing_js = read_public("crump-billing-5.1.js")
    cleanup = read_public("crump-navigation-5.2.5.js")
    cleanup_css = read_public("crump-navigation-5.2.5.css")

    assert "const button = $('#upgradeBtnSidebar');" in billing_js
    assert "button.appendChild(badge);" in billing_js
    assert "function closeMobileSidebar()" in cleanup
    assert "#settingsBtn, #upgradeBtnSidebar" in cleanup
    assert "byId('sidebar')?.classList.remove('active');" in cleanup
    assert "byId('sidebarOverlay')?.classList.remove('active');" in cleanup
    assert "#upgradeBtnSidebar .billing51-sidebar-balance" in cleanup_css
    assert "margin-left: auto" in cleanup_css