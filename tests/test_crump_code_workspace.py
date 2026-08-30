from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_code_workspace_is_loaded_but_hidden_until_server_configuration_and_entitlement():
    script = read("public/crump-code-5.9.35.js")
    navigation = read("public/crump-navigation-5.9.30.js")
    runtime = read("public/runtime-body-v1.js")
    native = read("scripts/build-native.mjs")
    worker = read("public/sw.js")

    assert "id: 'code'" in navigation
    assert "data-crump-code-destination hidden" in navigation
    assert "state.configured = Boolean(feature?.configured && provider?.configured)" in script
    assert "state.available = state.configured && state.entitled" in script
    assert "destination.hidden = !state.configured" in script
    assert "showBillingCenter?.({plan: 'professional'})" in script
    versioned_script = "/crump-code-5.9.35.js?v=5.9.76-intelligence-architecture-1"
    assert versioned_script in runtime
    assert versioned_script in native
    assert versioned_script in worker
    for asset in ("/crump-code-5.9.35.css", "/crump-code-5.9.35.js"):
        assert asset in runtime
        assert asset in native
        assert asset in worker


def test_code_workspace_separates_preparation_from_confirmed_metered_execution():
    script = read("public/crump-code-5.9.35.js")
    routes = read("backend/routes/code.py")

    assert "Preparing saves the task for review. It does not start a model or spend credits." in script
    assert 'checkbox.id = \'crumpCodeRunConfirmed\'' in script
    assert "I reviewed the repository, objective, mode, and cost boundary." in script
    assert "method: 'POST', body: {confirmed: true}" in script
    assert 'payload.get("confirmed") is not True' in routes
    assert '"RUN_CONFIRMATION_REQUIRED"' in routes
    assert "status_code=202" in routes
    assert '"accepted": True' in routes
    assert "Task accepted. You can close this window" in script


def test_code_workspace_exposes_review_cancellation_approval_and_patch_surfaces():
    script = read("public/crump-code-5.9.35.js")

    for signal in (
        "Review patch",
        "Download .patch",
        "Verification",
        "Approval required",
        "Approve bounded retry",
        "Cancel task",
        "Activity history",
    ):
        assert signal in script
    assert "pre.textContent = String(task.result_patch)" in script
    assert "copy.textContent = String(task.result_summary)" in script
    assert "request cancellation. Crump Code checks that request" in script
    assert "This approval expires" in script
    assert "CODE_APPROVAL_EXPIRED" in script
    assert "CODE_TASK_EXPIRED" in script
    assert "addTextRow(facts, 'Expires', formatDate(task.expires_at))" in script


def test_code_workspace_has_accessible_modal_and_mobile_controls():
    script = read("public/crump-code-5.9.35.js")
    styles = read("public/crump-code-5.9.35.css")

    assert 'role="dialog" aria-modal="true" aria-labelledby="crumpCodeTitle"' in script
    assert "if (event.key === 'Escape')" in script
    assert "if (event.key !== 'Tab') return" in script
    assert "aria-live=\"polite\"" in script
    assert ".crump-code-control { font-size: 16px; }" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles


def test_code_workspace_has_its_own_gated_navigation_destination():
    navigation = read("public/crump-navigation-5.9.30.js")
    styles = read("public/crump-navigation-5.9.30.css")

    assert "else if (destination === 'code') void openCode();" in navigation
    assert "if (codeWorkspaceIsOpen()) return 'code';" in navigation
    assert "createCard('code'" not in navigation
    assert ".crump5930-destination.is-locked::after" in styles
    assert "repeat(6,minmax(0,1fr))" in styles


def test_local_preview_fixture_cannot_reach_real_product_endpoints():
    preview = read("tests/fixtures/crump-code-preview.html")

    assert "window.fetch = async input" in preview
    assert "window.__mockEnabled" in preview
    assert "https://www.askcrump.com" not in preview
    assert "task-preview" in preview
    assert "previewStatus === 'expired'" in preview
    assert "CODE_TASK_EXPIRED" in preview
