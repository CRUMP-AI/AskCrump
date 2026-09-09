from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
BUTTON_TAG_PATTERN = re.compile(r"<button\b[^>]*>", re.IGNORECASE)
DYNAMIC_BUTTON_PATTERN = re.compile(
    r"(?P<name>[A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:[^;\n?]+\?\s*)?"
    r"(?:document\.)?createElement\(\s*([\"'])button\2\s*\)",
    re.IGNORECASE,
)
EXPECTED_BUTTON_INVENTORY = {
    "public/app.html": 47,
    "public/credit-confirmation.js": 3,
    "public/crump-5.0.js": 3,
    "public/crump-5.2.js": 5,
    "public/crump-billing-5.1.js": 3,
    "public/crump-code-5.9.35.js": 4,
    "public/crump-library-5.7.js": 41,
    "public/crump-navigation-5.9.30.js": 4,
    "public/crump-product-5.3.1.js": 10,
    "public/crump-product-5.3.js": 54,
    "public/install-prompt.js": 2,
    "public/lifecycle-manager.js": 2,
    "public/subscription-ui.js": 3,
}
DYNAMIC_BUTTON_INVENTORY = {
    "public/account-manager.js": 1,
    "public/app.js": 2,
    "public/crump-4.3.js": 1,
    "public/crump-4.4.js": 3,
    "public/crump-5.0.js": 22,
    "public/crump-5.2.js": 3,
    "public/crump-billing-5.1.js": 2,
    "public/crump-code-5.9.35.js": 5,
    "public/crump-polish-5.6.js": 1,
    "public/crump-precision-image-edit.js": 29,
    "public/crump-product-5.3.1.js": 1,
    "public/crump-product-5.3.js": 4,
    "public/crump-subscriptions-5.3.2.js": 2,
    "public/install-prompt.js": 1,
    "public/onboarding.js": 1,
    "public/ui-functions.js": 15,
}
INDIRECT_DYNAMIC_BUTTON_OWNERS = {
    "public/crump-5.0.js:1400:close": (
        "mountLightbox(box, close);",
        "closeButton.addEventListener('click', dismiss)",
    ),
    "public/crump-5.0.js:1477:close": (
        "mountLightbox(box, close);",
        "closeButton.addEventListener('click', dismiss)",
    ),
    "public/crump-5.0.js:1681:project": (
        "wireOutputProjectAction(project, {",
        "button.addEventListener('click', async () => {",
    ),
    "public/crump-5.2.js:653:buy": (
        "buy.dataset.crumpPack =",
        "modal.addEventListener('click', event => {",
        "event.target.closest?.('[data-crump-pack]')",
    ),
    "public/crump-code-5.9.35.js:316:button": (
        "button.dataset.crumpCodeTask =",
        "byId('crumpCodeTaskList')?.addEventListener('click'",
        "event.target.closest?.('[data-crump-code-task]')",
    ),
    "public/crump-code-5.9.35.js:360:button": (
        "button.dataset.codeApproval =",
        "byId('crumpCodeDetail')?.addEventListener('click'",
        "event.target.closest?.('[data-code-approval]')",
    ),
    "public/crump-code-5.9.35.js:474:download": (
        "download.dataset.codeAction = 'download'",
        "byId('crumpCodeDetail')?.addEventListener('click'",
        "button.dataset.codeAction === 'download'",
    ),
    "public/crump-code-5.9.35.js:504:run": (
        "run.dataset.codeAction = 'run'",
        "byId('crumpCodeDetail')?.addEventListener('click'",
        "button.dataset.codeAction === 'run'",
    ),
    "public/crump-code-5.9.35.js:522:cancel": (
        "cancel.dataset.codeAction = 'cancel'",
        "byId('crumpCodeDetail')?.addEventListener('click'",
        "button.dataset.codeAction === 'cancel'",
    ),
    "public/crump-product-5.3.1.js:457:button": (
        "button.className = 'crump531-chat-menu-button'",
        "document.addEventListener('click', event => {",
        "event.target.closest?.('.crump531-chat-menu-button')",
    ),
    "public/ui-functions.js:358:submit": (
        "submit.type = 'submit'",
        "form.addEventListener('submit', async event => {",
    ),
}


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


def _runtime_owner_source() -> str:
    """Return executable JS text without the button markup that it renders."""
    return "\n".join(
        BUTTON_TAG_PATTERN.sub("", path.read_text(encoding="utf-8"))
        for path in sorted(PUBLIC.glob("*.js"))
    )


def _button_has_runtime_owner(button: dict[str, str], scripts: str) -> bool:
    if button.get("type", "").lower() == "submit" or button.get("onclick"):
        return True

    button_id = button.get("id", "")
    if button_id and re.search(
        rf"(?<![\w-]){re.escape(button_id)}(?![\w-])",
        scripts,
    ):
        return True

    data_attributes = [name for name in button if name.startswith("data-")]
    if any(
        f"[{attribute}" in scripts
        or f"dataset.{_dataset_name(attribute)}" in scripts
        or f"getAttribute('{attribute}')" in scripts
        or f'getAttribute("{attribute}")' in scripts
        for attribute in data_attributes
    ):
        return True

    classes = button.get("class", "").split()
    return any(
        re.search(rf"(?<![\w-]){re.escape(class_name)}(?![\w-])", scripts)
        for class_name in classes
    )


def _dynamic_button_tail(source: str, match: re.Match[str]) -> str:
    """Bound one created button to its own declaration lifetime."""
    name = re.escape(match.group("name"))
    remainder = source[match.end():]
    next_declaration = re.search(
        rf"(?<![\w$]){name}\s*=\s*(?:[^;\n?]+\?\s*)?"
        rf"(?:document\.)?createElement\(\s*([\"'])button\1\s*\)",
        remainder,
        re.IGNORECASE,
    )
    if next_declaration:
        remainder = remainder[:next_declaration.start()]
    return remainder[:12_000]


def _dynamic_button_declares_type(name: str, tail: str) -> bool:
    escaped = re.escape(name)
    return bool(
        re.search(
            rf"(?<![\w$]){escaped}\.type\s*=\s*([\"'])(?:button|submit|reset)\1",
            tail,
            re.IGNORECASE,
        )
        or re.search(
            rf"(?<![\w$]){escaped}\.setAttribute\(\s*([\"'])type\1\s*,\s*"
            r"([\"'])(?:button|submit|reset)\2\s*\)",
            tail,
            re.IGNORECASE,
        )
    )


def _dynamic_button_has_direct_owner(name: str, tail: str) -> bool:
    escaped = re.escape(name)
    return bool(
        re.search(
            rf"(?<![\w$]){escaped}\.addEventListener\(\s*([\"'])click\1",
            tail,
            re.IGNORECASE,
        )
        or re.search(
            rf"(?<![\w$]){escaped}\.onclick\s*=",
            tail,
            re.IGNORECASE,
        )
    )


def test_rendered_button_inventory_requires_explicit_review() -> None:
    inventory: dict[str, int] = {}
    for page in sorted([*PUBLIC.rglob("*.html"), *PUBLIC.glob("*.js")]):
        parser = ButtonParser()
        parser.feed(page.read_text(encoding="utf-8"))
        if parser.buttons:
            inventory[page.relative_to(ROOT).as_posix()] = len(parser.buttons)

    assert inventory == EXPECTED_BUTTON_INVENTORY
    assert sum(inventory.values()) == 181


def test_programmatically_created_button_inventory_requires_explicit_review() -> None:
    inventory: dict[str, int] = {}
    for path in sorted(PUBLIC.glob("*.js")):
        count = len(list(DYNAMIC_BUTTON_PATTERN.finditer(path.read_text(encoding="utf-8"))))
        if count:
            inventory[path.relative_to(ROOT).as_posix()] = count

    assert inventory == DYNAMIC_BUTTON_INVENTORY
    assert sum(inventory.values()) == 93
    assert sum(EXPECTED_BUTTON_INVENTORY.values()) + sum(inventory.values()) == 274


def test_programmatically_created_buttons_declare_type_and_runtime_owner() -> None:
    missing_type: list[str] = []
    missing_owner: list[str] = []
    indirect_owners_used: set[str] = set()

    for path in sorted(PUBLIC.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for match in DYNAMIC_BUTTON_PATTERN.finditer(source):
            name = match.group("name")
            tail = _dynamic_button_tail(source, match)
            identity = (
                f"{path.relative_to(ROOT).as_posix()}:"
                f"{source.count(chr(10), 0, match.start()) + 1}:{name}"
            )
            if not _dynamic_button_declares_type(name, tail):
                missing_type.append(identity)
            indirect_evidence = INDIRECT_DYNAMIC_BUTTON_OWNERS.get(identity, ())
            indirect_owner = bool(indirect_evidence) and all(
                evidence in source for evidence in indirect_evidence
            )
            direct_owner = _dynamic_button_has_direct_owner(name, tail)
            if not direct_owner and indirect_owner:
                indirect_owners_used.add(identity)
            if not direct_owner and not indirect_owner:
                missing_owner.append(identity)

    assert not missing_type, f"Programmatic buttons without an explicit type: {missing_type}"
    assert not missing_owner, f"Programmatic buttons without a runtime click owner: {missing_owner}"
    assert indirect_owners_used == set(INDIRECT_DYNAMIC_BUTTON_OWNERS)


def test_dynamic_button_owner_guard_rejects_an_unowned_control() -> None:
    source = (
        "const futureDeadButton = document.createElement('button');\n"
        "futureDeadButton.type = 'button';\n"
        "futureDeadButton.textContent = 'Future action';\n"
        "host.appendChild(futureDeadButton);\n"
    )
    match = next(DYNAMIC_BUTTON_PATTERN.finditer(source))
    tail = _dynamic_button_tail(source, match)

    assert _dynamic_button_declares_type("futureDeadButton", tail)
    assert not _dynamic_button_has_direct_owner("futureDeadButton", tail)


def test_every_rendered_button_has_a_form_or_runtime_owner() -> None:
    scripts = _runtime_owner_source()
    missing: list[str] = []

    for page in sorted([*PUBLIC.rglob("*.html"), *PUBLIC.glob("*.js")]):
        parser = ButtonParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for index, button in enumerate(parser.buttons, start=1):
            if _button_has_runtime_owner(button, scripts):
                continue
            identity = button.get("id") or button.get("class") or f"button-{index}"
            missing.append(f"{page.relative_to(ROOT)}::{identity}")

    assert not missing, f"Rendered buttons without a form or runtime owner: {missing}"


def test_button_owner_guard_does_not_accept_markup_self_references() -> None:
    rendered_markup = '<button type="button" id="futureDeadButton">Future action</button>'
    scripts = BUTTON_TAG_PATTERN.sub("", rendered_markup)

    assert not _button_has_runtime_owner(
        {"type": "button", "id": "futureDeadButton"},
        scripts,
    )


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


def test_browser_control_matrix_is_fail_closed_and_one_command() -> None:
    runner = (ROOT / "scripts" / "verify-browser-control-matrix.mjs").read_text(encoding="utf-8")
    package = (ROOT / "package.json").read_text(encoding="utf-8")
    verifier_names = sorted(path.name for path in (ROOT / "scripts").glob("verify-*.cjs"))

    assert len(verifier_names) == 35
    for name in verifier_names:
        assert f"'{name}'" in runner
    assert "Browser verifier inventory drifted." in runner
    assert "ASKCRUMP_PLAN_DELAY_RUNS" in runner
    for port in (4173, 8765, 8766, 8767, 8770):
        assert f"port: {port}" in runner
    assert '"test:browser-controls": "node scripts/verify-browser-control-matrix.mjs"' in package


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
