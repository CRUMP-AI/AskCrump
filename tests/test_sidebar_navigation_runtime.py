from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_runtime_loads_navigation_cleanup_last():
    runtime = read("public/runtime-body-v1.js")
    assert "crump-navigation-5.2.5.css" in runtime
    assert "crump-navigation-5.2.5.js" in runtime
    assert "/crump-v1-body.js?v=5.9.76-canonical-files-handoff-1" in runtime
    assert "/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1" in runtime
    assert runtime.index("crump-v1-stability.js") < runtime.index("crump-navigation-5.2.5.js")


def test_cleanup_removes_duplicate_destinations():
    script = read("public/crump-navigation-5.2.5.js")
    assert '[data-v1-command="settings"]' in script
    assert '[data-v1-command="billing"]' in script
    assert "node.remove()" in script
    assert "v1-rail-spacer" in script


def test_footer_keeps_primary_destinations_and_live_balance():
    script = read("public/crump-navigation-5.2.5.js")
    css = read("public/crump-navigation-5.2.5.css")

    assert "settingsBtn" in script
    assert "upgradeBtnSidebar" in script
    assert "Plan & credits" in script
    assert "billing51-sidebar-balance" in css
    assert "margin-left: auto" in css


def test_mobile_destination_click_closes_drawer():
    script = read("public/crump-navigation-5.2.5.js")
    assert "closeMobileSidebar" in script
    assert "#settingsBtn, #upgradeBtnSidebar, #crump53ProjectsSidebar" in script
    assert "sidebarOverlay" in script
    assert "openDestination(destinationId);" in script
    assert script.index("openDestination(destinationId);") < script.index("closeMobileSidebar();", script.index("openDestination(destinationId);"))
    assert "}, true);" not in script[script.index("function wireDrawerClose()") : script.index("function observeSidebar()")]


def test_destination_fallback_restores_core_sidebar_routes_without_double_opening():
    script = read("public/crump-navigation-5.2.5.js")

    assert "function destinationIsOpen(id)" in script
    assert "function openDestination(id)" in script
    assert "if (destinationIsOpen(id)) return;" in script
    assert "window.openSettings?.();" in script
    assert "window.showBillingCenter || window.showUpgradePrompt" in script
    assert ".billing51-modal, .upgrade-modal.active" in script
    assert "window.CrumpProduct53?.open?.('projects');" in script
    assert "const destinationId = destination.id;" in script
    assert "openDestination(destinationId);" in script
    assert "menu?.setAttribute('aria-expanded', 'false');" in script
    assert "menu?.setAttribute('aria-label', 'Open Chats');" in script
    assert "window.CrumpBodyV1?.syncConversationLibrary?.();" in script
