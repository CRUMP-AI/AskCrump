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


def test_every_markup_button_declares_its_behavior_type() -> None:
    missing: list[str] = []
    button_pattern = re.compile(r"<button\b[^>]*>", re.IGNORECASE)
    type_pattern = re.compile(r"\btype\s*=\s*([\"'])(?:button|submit|reset)\1", re.IGNORECASE)

    for path in sorted([*PUBLIC.rglob("*.html"), *PUBLIC.glob("*.js")]):
        text = path.read_text(encoding="utf-8")
        for match in button_pattern.finditer(text):
            if type_pattern.search(match.group(0)):
                continue
            line = text.count("\n", 0, match.start()) + 1
            missing.append(f"{path.relative_to(ROOT)}:{line}")

    assert not missing, (
        "Buttons must explicitly declare type=button, submit, or reset so a later form "
        f"composition cannot change their action: {missing}"
    )


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


def test_add_menu_creation_buttons_open_the_authoritative_studios() -> None:
    attachment = (PUBLIC / "crump-5.2.js").read_text(encoding="utf-8")
    menu = attachment[attachment.index("function showAttachMenu52"):attachment.index("function ownAttachButton")]

    assert "window.CrumpImageStudio.open();" in menu
    assert "window.CrumpDocumentStudio.open();" in menu
    assert "document.documentElement.dataset.crump52CreativeTool = 'image'" not in menu
    assert "input.placeholder = 'Describe the document you want Crump to create…'" not in menu


def test_generated_output_project_button_has_visible_pending_and_recovery_states() -> None:
    composer = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")
    action = composer[
        composer.index("function wireOutputProjectAction"):
        composer.index("function enhanceRenderedMessages")
    ]

    assert "Keep in a Project" in action
    assert "button.textContent = 'Saving…';" in action
    assert "Saving file and conversation privately…" in action
    assert "const previousLabel = button.textContent;" in action
    assert "button.textContent = previousLabel;" in action
    assert "window.CrumpAnalytics?.track?.('ProjectSaveIntentReached'" in action
    assert "source: selectedProjectId ? 'existing_project' : 'new_project'" in action
    assert "if (selectedProjectId) options.projectId = selectedProjectId;" in action
    assert "const savedProjectId = String(button.dataset.projectId || '').trim();" in action
    assert "window.CrumpProduct53?.openProject?.(savedProjectId)" in action


def test_tutorial_names_the_current_image_apply_button() -> None:
    tutorial = (PUBLIC / "onboarding.js").read_text(encoding="utf-8")
    editor = (PUBLIC / "crump-precision-image-edit.js").read_text(encoding="utf-8")

    phrase = "Choose Apply changes to return to the conversation with the edited image"
    assert phrase in tutorial
    assert "saveLocal.textContent = 'Apply changes'" in editor
    assert "Save local edit" not in tutorial


def test_creation_mode_chip_restores_the_normal_contextual_composer() -> None:
    composer = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")

    assert "function defaultComposerPlaceholder()" in composer
    assert "function restoreComposerPlaceholder({focus = false} = {})" in composer
    assert "function clearToolMode({focus = false} = {})" in composer
    assert "chip.addEventListener('click', () => clearToolMode({focus: true}))" in composer
    assert "input.placeholder = defaultComposerPlaceholder();" in composer
    assert "Message ${assistant} in ${projectName}…" in composer
    assert "window.addEventListener('crump:conversation-opened', scheduleComposerPlaceholderSync)" in composer


def test_button_state_browser_fixture_is_private_and_credential_free() -> None:
    fixture = (ROOT / "tests" / "fixtures" / "creation-sheet-containment.html").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify-button-state-integrity.cjs").read_text(encoding="utf-8")

    assert "Simulate Project conversation" in fixture
    assert "IN PROJECT · Button QA" in fixture
    assert "Create DOCX" in verifier
    assert "Create PPTX" in verifier
    assert "contextualAfterTool" in verifier
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture


def test_continuous_workflow_proof_uses_real_controls_without_customer_or_provider_data() -> None:
    fixture = (ROOT / "tests" / "fixtures" / "marketing-workflow-proof.html").read_text(encoding="utf-8")
    recorder = (ROOT / "scripts" / "record-marketing-workflow-proof.cjs").read_text(encoding="utf-8")

    for asset in (
        "/public/ui-functions.js",
        "/public/crump-5.0.js",
        "/public/crump-product-5.3.js",
        "/public/crump-product-5.3.1.js",
    ):
        assert asset in fixture
    for action in ("Send message", "Keep in a Project", "Open Project", "Editable PowerPoint ready"):
        assert action in recorder
    assert "recordVideo" in recorder
    assert "unexpectedRequests" in recorder
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture


def test_browser_error_sensitive_button_fixtures_suppress_favicon_noise() -> None:
    for relative in (
        "auth-navigation-focus.html",
        "feature-access-recovery.html",
        "project-limit-plan-default-off.html",
    ):
        fixture = (ROOT / "tests" / "fixtures" / relative).read_text(encoding="utf-8")
        assert '<link rel="icon" href="data:,">' in fixture


def test_add_menu_browser_fixture_exercises_both_authoritative_studios() -> None:
    fixture = (ROOT / "tests" / "fixtures" / "attach-creation-routing.html").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify-attach-creation-routing.cjs").read_text(encoding="utf-8")

    assert '<script src="/public/crump-5.0.js?v=attach-creation-routing-fixture-1"></script>' in fixture
    assert '<script src="/public/crump-5.2.js?v=attach-creation-routing-fixture-1"></script>' in fixture
    assert "Create image Generate or edit an image" in verifier
    assert "Create document DOCX" in verifier
    assert "dataset.crump52CreativeTool" in verifier
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture


def test_library_new_button_opens_the_visible_manuscript_workspace_first() -> None:
    library = (PUBLIC / "crump-library-5.7.js").read_text(encoding="utf-8")

    handler = library[library.index("byId('crump57New')?.addEventListener"):]
    handler = handler[:handler.index("byId('crump57Deleted')")]
    assert "openProduct('manuscripts')" in handler
    assert "byId('crump53NewManuscript')?.click()" in handler
    assert handler.index("openProduct('manuscripts')") < handler.index("byId('crump53NewManuscript')?.click()")
    assert "The manuscript workspace is still loading. Try again in a moment." in handler


def test_library_layout_buttons_expose_their_selected_state() -> None:
    library = (PUBLIC / "crump-library-5.7.js").read_text(encoding="utf-8")

    assert 'aria-pressed="${state.layout === layout ? \'true\' : \'false\'}"' in library


def test_library_new_button_release_is_cache_addressable_everywhere() -> None:
    asset = "/crump-library-5.7.js?v=5.9.76-library-new-routing-1"

    for relative in ("public/runtime-body-v1.js", "public/sw.js", "scripts/build-native.mjs"):
        assert asset in (ROOT / relative).read_text(encoding="utf-8")
