from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_code_workspace_is_lazy_loaded_only_after_server_configuration_and_entitlement():
    script = read("public/crump-code-5.9.35.js")
    loader = read("public/crump-code-loader.js")
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
    assert "function hydrateAvailability(data)" in script
    assert "__crumpCodeBootstrapStatus" in script
    assert "window.CrumpCodeWorkspace = Object.freeze({open, close, refresh, refreshAvailability, hydrateAvailability})" in script
    versioned_script = "/crump-code-5.9.35.js?v=5.9.76-autonomous-activation-2"
    versioned_style = "/crump-code-5.9.35.css?v=5.9.76-autonomous-activation-2"
    versioned_loader = "/crump-code-loader.js?v=5.9.76-autonomous-activation-2"
    for source in (runtime, native, worker):
        assert versioned_loader in source
        assert versioned_script not in source
        assert versioned_style not in source
    assert versioned_script in loader
    assert versioned_style in loader
    assert "if (!configured(data))" in loader
    assert "await loadWorkspace(data);" in loader
    assert "window.CrumpCodeLoader = Object.freeze" in loader
    assert "window.CrumpCodeLoader?.open?.()" in navigation
    assert "url.pathname === '/crump-code-loader.js'" in worker
    assert "url.pathname === '/crump-code-5.9.35.js'" not in worker
    assert "url.pathname === '/crump-code-5.9.35.css'" not in worker


def test_code_lazy_load_has_real_browser_disabled_locked_and_entitled_proof():
    verifier = read("scripts/verify-code-lazy-load.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")

    assert "verify-code-lazy-load.cjs" in matrix
    assert "disabled:${assetPaths.script}" in verifier
    assert "disabled:${assetPaths.style}" in verifier
    assert "counts.get('disabled:/api/features'), 1" in verifier
    assert "Autonomous Crump — Professional plan" in verifier
    assert "bootstrapStatusRetained" in verifier
    assert "askcrump.com" not in verifier.lower()
    assert "password" not in verifier.lower()


def test_code_workspace_separates_preparation_from_confirmed_metered_execution():
    script = read("public/crump-code-5.9.35.js")
    routes = read("backend/routes/code.py")

    assert "Preparing saves the task for review. It does not start a model or spend credits." in script
    assert 'checkbox.id = \'crumpCodeRunConfirmed\'' in script
    assert "I reviewed the repository, objective, mode, cost, and built-in-only verification boundary." in script
    assert "I authorize bounded repository tests/checks and model-visible redacted output." in script
    assert "Repository tests are executable code." in script
    assert "verificationPolicy:" in script
    assert "updateVerificationPolicyControl" in script
    assert "method: 'POST', body: {confirmed: true}" in script
    assert 'payload.get("confirmed") is not True' in routes
    assert '"RUN_CONFIRMATION_REQUIRED"' in routes
    assert "status_code=202" in routes
    assert '"accepted": True' in routes
    assert "Task accepted. You can close this window" in script


def test_code_workspace_exposes_review_cancellation_failure_and_patch_surfaces():
    script = read("public/crump-code-5.9.35.js")

    for signal in (
        "Changes ·",
        "Download .patch",
        "Verification",
        "Unsupported boundary reached",
        "No approval action is available",
        "Cancel task",
        "Activity history",
    ):
        assert signal in script
    assert "function parseUnifiedPatch(value)" in script
    assert "function renderPatch(container, task)" in script
    assert "button.dataset.codeAction = 'diff-file'" in script
    assert "Nothing is pushed. Review or download the complete patch" in script
    assert "copy.textContent = String(task.result_summary)" in script
    assert "request cancellation. Autonomous Crump checks that request" in script
    assert "cannot resume from the recorded boundary" in script
    assert "data-code-approval" not in script
    assert "CODE_TASK_EXPIRED" in script
    assert "addTextRow(facts, 'Expires', formatDate(task.expires_at))" in script


def test_autonomous_crump_review_console_proves_durable_progress_diff_and_check_output():
    script = read("public/crump-code-5.9.35.js")
    styles = read("public/crump-code-5.9.35.css")
    verifier = read("scripts/verify-autonomous-crump-review.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")

    for signal in (
        "AUTONOMOUS CRUMP · PRIVATE PREVIEW",
        "Durable run progress",
        "Saved to Project",
        "The private worker continues",
        "Connection paused",
        "Connection restored",
    ):
        assert signal in script
    assert "verify-autonomous-crump-review.cjs" in matrix
    assert "fixture offline" in verifier
    assert "window.dispatchEvent(new Event('online'))" in verifier
    assert "src/retry.js" in verifier
    assert "tests/retry.test.js" in verifier
    assert "mode=ownership" in verifier
    assert "task-fast/run" in verifier
    assert "task-fast/cancel" in verifier
    assert "axe.run" in verifier
    assert "{width: 390, height: 844}" in verifier
    assert "fileList.setAttribute('role', 'list')" not in script
    assert ".crump-code-progress-stages" in styles
    assert ".crump-code-diff-viewer" in styles
    assert ".crump-code-check pre" in styles


def test_customer_runtime_uses_autonomous_crump_brand_without_renaming_internal_contracts():
    customer_runtime = (
        "public/crump-code-loader.js",
        "public/crump-code-5.9.35.js",
        "public/crump-navigation-5.9.30.js",
        "backend/feature_service.py",
        "backend/routes/code.py",
        "backend/code_service.py",
        "backend/code_runner.py",
    )
    for relative in customer_runtime:
        source = read(relative)
        assert "Crump Code" not in source, relative

    always_loaded_plan_surfaces = (
        "public/crump-billing-5.1.js",
        "public/crump-5.2.js",
    )
    for relative in always_loaded_plan_surfaces:
        source = read(relative)
        assert "Crump Code" not in source, relative
        assert "Autonomous Crump" not in source, relative

    workspace = read("public/crump-code-5.9.35.js")
    navigation = read("public/crump-navigation-5.9.30.js")
    routes = read("backend/routes/code.py")
    config = read("backend/config.py")
    assert "AUTONOMOUS CRUMP · PRIVATE PREVIEW" in workspace
    assert "No Ask Crump or account credentials are injected" in workspace
    assert "Public repository contents and check output may be sent" in workspace
    assert "authorized and prepared to share" in workspace
    assert "cannot see secrets" not in workspace.lower()
    assert "autonomous-crump-${String(state.task.id" in workspace
    assert "Autonomous tasks stay attached to one Ask Crump Project." in workspace
    assert "No Autonomous tasks in this Project yet." in workspace
    assert "Untitled Autonomous task" in workspace
    assert "Loading Autonomous tasks…" in workspace
    for legacy_task_label in (
        "Code tasks stay attached",
        "No code tasks",
        "Untitled code task",
        "Loading code tasks",
    ):
        assert legacy_task_label not in workspace
    assert "label: 'Autonomous'" in navigation
    assert '"CODE_WORKSPACE_NOT_CONFIGURED"' in routes
    assert "CODE_WORKSPACE_PUBLIC_RELEASED = False" in config
    assert "CRUMP_ENABLE_CODE_WORKSPACE" in config


def test_disabled_feature_brand_is_confined_to_gated_runtime_and_absent_from_promotion_surfaces():
    text_suffixes = {".css", ".html", ".js", ".json", ".md", ".txt", ".xml"}
    public_brand_hits = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "public").rglob("*")
        if path.is_file()
        and path.suffix.lower() in text_suffixes
        and "Autonomous Crump" in path.read_text(encoding="utf-8")
    }
    assert public_brand_hits == {
        "public/crump-code-5.9.35.js",
        "public/crump-code-loader.js",
    }

    promotion_paths = {
        path
        for path in (ROOT / "public").rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".html", ".xml"}
    }
    promotion_paths.update(
        path
        for path in (ROOT / "public").iterdir()
        if path.is_file()
        and path.suffix.lower() in {".css", ".js"}
        and path.name.startswith(("billing", "crump-billing", "landing", "onboarding"))
    )
    promotion_paths.update(
        path
        for path in (ROOT / "store").rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt"}
    )
    for path in sorted(promotion_paths):
        source = path.read_text(encoding="utf-8")
        assert "Autonomous Crump" not in source, path.relative_to(ROOT)
        assert "Crump Code" not in source, path.relative_to(ROOT)


def test_current_docs_use_one_explicit_customer_name_migration_note():
    for relative in ("docs/DATA_SAFETY.md", "docs/CRUMP_CODE_SECURITY.md"):
        assert "Crump Code" not in read(relative), relative

    backlog = read("docs/OPERATING_BACKLOG.md")
    active_gate = backlog.split(
        "### P0 — Complete the Autonomous Crump activation gates", 1
    )[1].split("\n### ", 1)[0]
    assert "Crump Code" not in active_gate

    company = read("docs/COMPANY_OPERATING_PLAN.md")
    assert "Deploy Autonomous Crump and Crump Voice foundations disabled by default" in company
    assert "Autonomous Crump remains a separate hidden gated destination" in company
    assert "Deploy Crump Code and Crump Voice foundations disabled by default" not in company
    assert "Crump Code remains a separate hidden gated destination" not in company
    assert "Do not enable Autonomous Crump until the real" in backlog
    assert "Do not enable Crump Code until the real" not in backlog

    candidate = read("docs/AUTONOMOUS_CRUMP_ACTIVATION_CANDIDATE_2026-09-16.md")
    migration_note = "Autonomous Crump (formerly Crump Code; internal identifier `crump_code`)"
    assert candidate.count(migration_note) == 1
    assert candidate.count("Crump Code") == 1
    assert (
        f"the {(ROOT / 'public/crump-code-5.9.35.js').stat().st_size:,}-byte workspace script "
        f"and {(ROOT / 'public/crump-code-5.9.35.css').stat().st_size:,}-byte stylesheet"
        in candidate
    )


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
