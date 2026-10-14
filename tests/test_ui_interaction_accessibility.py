from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_nested_conversation_actions_do_not_activate_the_conversation_row():
    app = read("public/app.js")
    row_handler = app[
        app.index("item.addEventListener('keydown', event => {"):
        app.index("const content = document.createElement('div');", app.index("item.addEventListener('keydown', event => {"))
    ]

    assert "if (event.target !== item) return;" in row_handler
    assert row_handler.index("if (event.target !== item) return;") < row_handler.index("loadChat(chat.id)")


def test_settings_is_a_labelled_modal_with_inert_background_and_focus_lifecycle():
    html = read("public/app.html")
    app = read("public/app.js")

    assert 'id="settingsModal" class="modal v1-modal" style="display:none;" aria-hidden="true"' in html
    assert 'role="dialog" aria-modal="true" aria-labelledby="settingsTitle"' in html
    assert "setSettingsBackgroundInert(modal);" in app
    assert "element.setAttribute('inert', '')" in app
    assert "restoreSettingsBackground();" in app
    assert "element.id !== 'toastContainer'" in app
    assert "if (event.key === 'Escape')" in app
    assert "if (event.key !== 'Tab') return;" in app
    assert "last.focus({preventScroll: true});" in app
    assert "first.focus({preventScroll: true});" in app
    assert "settingsReturnFocus = opener || document.activeElement;" in app
    assert "const focusTarget = isVisibleControl(returnFocus) ? returnFocus : fallback;" in app
    assert "focusTarget?.focus({preventScroll: true});" in app
    assert '[data-cv-destination="profile"], [data-cv-destination="more"]' in app


def test_settings_sections_use_ordinary_current_page_navigation():
    html = read("public/app.html")
    body = read("public/crump-v1-body.js")

    assert 'id="settingsNavProfile"' in html
    assert 'aria-current="page" aria-controls="settingsPanelProfile"' in html
    assert 'id="settingsPanelProfile"' in html
    assert 'aria-labelledby="settingsNavProfile"' in html
    assert 'id="settingsPanelAppearance"' in html and 'aria-labelledby="settingsNavAppearance" hidden' in html
    assert "button.setAttribute('aria-current', 'page')" in body
    assert "button.removeAttribute('aria-current')" in body
    assert "panel.hidden = !active;" in body
    assert "aria-selected" not in body[body.index("function showSettingsTab"):body.index("function wireSettingsTabs")]


def test_rename_dialog_traps_focus_and_restores_its_conversation_menu_trigger():
    product = read("public/crump-product-5.3.1.js")
    rename = product[product.index("function renameChat"):product.index("function openChatMenu")]

    assert "function renameChat(chatId, trigger = state.menuTrigger)" in rename
    assert 'aria-modal="true" aria-labelledby="crump531RenameTitle"' in rename
    assert "const restoreTriggerFocus = () =>" in rename
    assert "trigger?.isConnected" in rename
    assert "liveTrigger.focus({preventScroll: true});" in rename
    assert "window.requestAnimationFrame(() => findLiveTrigger()?.focus?.({preventScroll: true}))" in rename
    assert "if (event.key === 'Escape')" in rename
    assert "if (event.key !== 'Tab') return;" in rename
    assert "const focusable = [input, cancel, save]" in rename
    assert "renameChat(chatId, button)" in product


def test_workspace_home_copy_uses_the_current_ways_to_begin_language():
    html = read("public/app.html")

    assert "Ways to begin" in html
