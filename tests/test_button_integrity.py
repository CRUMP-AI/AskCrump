from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


class ButtonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "button":
            return
        self.buttons.append({str(key): str(value or "") for key, value in attrs})


def _dataset_name(attribute: str) -> str:
    parts = attribute.removeprefix("data-").split("-")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def test_every_static_button_has_a_form_or_runtime_action() -> None:
    scripts = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PUBLIC.glob("*.js"))
    )
    missing: list[str] = []

    for page in sorted(PUBLIC.rglob("*.html")):
        parser = ButtonParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for index, button in enumerate(parser.buttons, start=1):
            if button.get("type", "").lower() == "submit" or button.get("onclick"):
                continue
            button_id = button.get("id", "")
            if button_id and re.search(rf"[\"']{re.escape(button_id)}[\"']", scripts):
                continue
            data_attributes = [name for name in button if name.startswith("data-")]
            wired = any(
                f"[{attribute}]" in scripts
                or f"dataset.{_dataset_name(attribute)}" in scripts
                or f"getAttribute('{attribute}')" in scripts
                or f'getAttribute("{attribute}")' in scripts
                for attribute in data_attributes
            )
            if wired:
                continue
            identity = button_id or button.get("class") or f"button-{index}"
            missing.append(f"{page.relative_to(ROOT)}::{identity}")

    assert not missing, f"Static buttons without an actionable runtime owner: {missing}"


def test_primary_destination_and_creation_buttons_have_complete_handlers() -> None:
    navigation = (PUBLIC / "crump-navigation-5.9.30.js").read_text(encoding="utf-8")
    body = (PUBLIC / "crump-v1-body.js").read_text(encoding="utf-8")

    for destination in ("ask", "projects", "code", "create", "video", "library", "you"):
        assert f"id: '{destination}'" in navigation
    for action in ("document", "presentation", "image", "manuscript", "video"):
        assert f"action === '{action}'" in navigation
    for command in ("new", "library", "settings", "billing", "research", "image", "file", "projects", "video"):
        assert f"case '{command}':" in body
    assert "button.addEventListener('click', () => openDestination" in navigation
    assert "button.addEventListener('click', () => openCreateTool" in navigation


def test_dynamic_button_systems_use_direct_or_delegated_click_owners() -> None:
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    composer = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")
    attachment = (PUBLIC / "crump-5.2.js").read_text(encoding="utf-8")
    conversations = (PUBLIC / "crump-product-5.3.1.js").read_text(encoding="utf-8")
    code = (PUBLIC / "crump-code-5.9.35.js").read_text(encoding="utf-8")
    library = (PUBLIC / "crump-library-5.7.js").read_text(encoding="utf-8")

    for button_id in (
        "clearChatsBtn",
        "settingsBtn",
        "upgradeBtnSidebar",
        "closeSettingsBtn",
        "saveSettingsBtn",
        "signOutBtn",
        "devicesBtn",
        "deleteAccountBtn",
    ):
        assert f"['{button_id}'," in app
    assert "button.addEventListener('click', handler)" in composer
    assert "button.addEventListener('click', event =>" in attachment
    assert "event.target.closest?.('.crump531-chat-menu-button')" in conversations
    assert "menu.querySelector('[data-crump531-action=\"rename\"]')" in conversations
    assert "byId('crumpCodeDetail')?.addEventListener('click'" in code
    assert "event.target.closest?.('[data-code-action]')" in code
    assert "event.target.closest?.('[data-code-approval]')" in code
    for button_id in ("crump57Deleted", "crump57Import", "crump57New"):
        assert f"byId('{button_id}')?.addEventListener('click'" in library


def test_tutorial_names_the_current_image_apply_button() -> None:
    tutorial = (PUBLIC / "onboarding.js").read_text(encoding="utf-8")
    editor = (PUBLIC / "crump-precision-image-edit.js").read_text(encoding="utf-8")

    phrase = "Choose Apply changes to return to the conversation with the edited image"
    assert phrase in tutorial
    assert "saveLocal.textContent = 'Apply changes'" in editor
    assert "Save local edit" not in tutorial
