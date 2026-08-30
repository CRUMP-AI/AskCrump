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
    assert "#settingsBtn, #upgradeBtnSidebar, #crump53ProjectsSidebar" in cleanup
    assert "byId('sidebar')?.classList.remove('active');" in cleanup
    assert "byId('sidebarOverlay')?.classList.remove('active');" in cleanup
    assert "menu?.setAttribute('aria-expanded', 'false');" in cleanup
    assert "menu?.setAttribute('aria-label', 'Open Chats');" in cleanup
    assert "window.CrumpBodyV1?.syncConversationLibrary?.();" in cleanup
    assert cleanup.index("openDestination(destinationId);") < cleanup.index("closeMobileSidebar();", cleanup.index("openDestination(destinationId);"))
    assert "#upgradeBtnSidebar .billing51-sidebar-balance" in cleanup_css
    assert "margin-left: auto" in cleanup_css


def test_footer_destinations_have_a_late_binding_fallback():
    cleanup = read_public("crump-navigation-5.2.5.js")

    assert "destinationIsOpen" in cleanup
    assert "openDestination" in cleanup
    assert "window.openSettings?.();" in cleanup
    assert "window.showBillingCenter || window.showUpgradePrompt" in cleanup
    assert "window.CrumpProduct53?.open?.('projects');" in cleanup


def test_conversation_options_use_a_stable_delegated_mobile_handler():
    product = read_public("crump-product-5.3.1.js")

    assert "function wireChatMenuDelegation()" in product
    assert "event.target.closest?.('.crump531-chat-menu-button')" in product
    assert "button?.closest?.('.chat-item[data-chat-id]')" in product
    assert "event.stopPropagation();" in product
    assert "openChatMenu(button, item.dataset.chatId);" in product
    assert "}, true);" in product[product.index("function wireChatMenuDelegation()") : product.index("function enhanceChatList()")]


def test_mobile_library_state_sync_survives_the_reorganized_navigation():
    body = read_public("crump-v1-body.js")

    assert "byId('menuBtn')" in body
    assert "sidebar.dataset.v1InertRevision" in body
    assert "sidebar.removeAttribute('inert');" in body
    assert "sidebar.setAttribute('inert', '');" in body


def test_final_desktop_navigation_keeps_a_permanent_chats_toggle():
    navigation = read_public("crump-navigation-5.9.30.js")
    body = read_public("crump-v1-body.js")

    assert "function conversationLibraryMarkup()" in navigation
    assert "data-crump5930-library-toggle" in navigation
    assert 'aria-label="Hide Chats"' in navigation
    assert ": (expanded ? 'Hide' : 'Show')" in body
    assert "? (expanded ? 'Close' : 'Open')" in body
    assert "window.CrumpBodyV1?.toggleConversationLibrary?.()" in navigation
    assert "window.CrumpBodyV1?.syncConversationLibrary?.()" in navigation
    assert "syncConversationLibrary: syncLibraryControl" in body
    assert "toggleConversationLibrary: openLibrary" in body
    assert "crump_v1_library_control_v2" in body
    assert "localStorage.removeItem('crump_v1_library_collapsed');" in body


def test_mobile_sidebar_browser_fixture_uses_the_production_navigation_layers():
    fixture = (ROOT / "tests" / "fixtures" / "mobile-sidebar-actions.html").read_text(encoding="utf-8")

    assert '/public/crump-v1-body.js' in fixture
    assert '/public/crump-navigation-5.2.5.js' in fixture
    assert '/public/crump-product-5.3.1.js' in fixture
    assert '/public/crump-navigation-5.9.30.js' in fixture
    assert 'aria-label="Conversation options"' not in fixture


def test_runtime_and_native_shell_load_the_chats_language_revision():
    runtime = (ROOT / "public" / "runtime-body-v1.js").read_text(encoding="utf-8")
    native = (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8")

    for source in (runtime, native):
        assert "/crump-v1-body.js?v=5.9.76-chats-language-1" in source
        assert "/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1" in source
