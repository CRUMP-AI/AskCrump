from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_code_workspace_is_lazy_loaded_only_after_server_configuration_and_entitlement():
    script = read("public/crump-code-5.9.35.js")
    loader = read("public/crump-code-loader.js")
    navigation = read("public/crump-navigation-5.9.30.js")
    vision_shell = read("public/crump-vision-shell-1.0.js")
    runtime = read("public/runtime-body-v1.js")
    native = read("scripts/build-native.mjs")
    worker = read("public/sw.js")

    assert "id: 'code'" in navigation
    assert "data-crump-code-destination hidden disabled aria-hidden=\"true\"" in vision_shell
    assert "state.configured = Boolean(feature?.configured && provider?.configured)" in script
    assert "state.available = state.configured && state.entitled" in script
    assert "destination.hidden = !state.configured" in script
    assert "showBillingCenter?.({plan: 'professional'})" in script
    assert "function hydrateAvailability(data)" in script
    assert "__crumpCodeBootstrapStatus" in script
    assert "window.CrumpCodeWorkspace = Object.freeze({open, close, refresh, refreshAvailability, hydrateAvailability})" in script
    versioned_script = "/crump-code-5.9.35.js?v=5.9.76-account-owner-boundary-1"
    versioned_style = "/crump-code-5.9.35.css?v=5.9.76-autonomous-continuity-1"
    versioned_loader = "/crump-code-loader.js?v=5.9.76-account-owner-boundary-1&workspaceRelease=guest-free-contract-2"
    for source in (runtime, native, worker):
        assert versioned_loader in source
        assert versioned_script not in source
        assert versioned_style not in source
    assert versioned_script in loader
    assert versioned_style in loader
    assert "if (!configured(data))" in loader
    assert "await loadWorkspace(data, context);" in loader
    assert "const DESTINATION_SELECTOR = '[data-crump-code-destination], [data-cv-destination=\"autonomous\"]'" in loader
    assert "syncDestinations(data);" in loader
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
    assert "I reviewed the repository, objective, mode, and cost boundary." in script
    assert "method: 'POST', body: {confirmed: true}" in script
    assert 'payload.get("confirmed") is not True' in routes
    assert '"RUN_CONFIRMATION_REQUIRED"' in routes
    assert "status_code=202" in routes
    assert '"accepted": True' in routes
    assert "Task accepted. You can close this window" in script


def test_code_workspace_reports_only_started_or_terminal_tasks_to_activity_center():
    script = read("public/crump-code-5.9.35.js")

    assert "function activityStatus(task)" in script
    assert "if (status === 'queued') return task?.payment_source ? 'queued' : '';" in script
    assert "function reportTaskActivity(task)" in script
    assert "window.CrumpActivityCenter?.report?.({" in script
    assert "function applyTask(task, {render = true} = {})" in script
    assert "reportTaskActivity(merged);" in script

    report = script[
        script.index("function reportTaskActivity"):
        script.index("function applyTask")
    ]
    for field in ("taskId", "projectId", "codeStatus", "createdAt", "updatedAt"):
        assert field in report
    for private_or_billable_field in (
        "objective",
        "repository",
        "result_patch",
        "result_summary",
        "usage_receipt",
        "creditsRequired",
        "payment_intent",
    ):
        assert private_or_billable_field not in report


def test_code_workspace_can_reopen_exact_project_and_task_from_global_activity():
    script = read("public/crump-code-5.9.35.js")
    loader = read("public/crump-code-loader.js")

    assert "async function open({projectId = '', taskId = ''} = {})" in script
    assert "const requestContext = beginNavigation();" in script
    assert "await loadProjects({projectId, taskId}, requestContext);" in script
    assert "async function loadProjects({projectId = '', taskId = ''} = {}, context = null)" in script
    assert "state.projectId = requestedProjectId;" in script
    assert "async function loadTasks(targetTaskId = '', context = null)" in script
    assert "const selectedTaskId = requestedTaskId || state.tasks[0]?.id || '';" in script
    assert "await selectTask(selectedTaskId, {" in script
    assert "context: requestContext" in script
    assert "projectId," in script
    assert "async function open(options = {})" in loader
    assert "window.CrumpCodeWorkspace?.open?.(options)" in loader


def test_code_workspace_polling_is_bounded_and_recovers_on_visibility_or_network():
    script = read("public/crump-code-5.9.35.js")

    assert "const POLL_TIMEOUT_MS = 12000" in script
    assert "const POLL_MAX_MS = 30000" in script
    assert "const controller = new AbortController();" in script
    assert "window.setTimeout(() => controller.abort(), POLL_TIMEOUT_MS)" in script
    assert "Math.min(POLL_MAX_MS, POLL_BASE_MS * (2 ** state.pollFailureCount))" in script
    assert "document.addEventListener('visibilitychange'" in script
    assert "window.addEventListener('online'" in script
    assert "startPolling(state.task.id, {immediate: true})" in script
    assert "window.addEventListener('crump:authentication-required', () => {" in script


def test_code_workspace_fences_accounts_navigation_and_poll_generations():
    script = read("public/crump-code-5.9.35.js")
    loader = read("public/crump-code-loader.js")

    assert "function resetWorkspaceState(ownerId = '')" in script
    assert "state.projects = [];" in script
    assert "state.tasks = [];" in script
    assert "state.task = null;" in script
    assert "renderDetail();" in script
    assert "function navigationIsCurrent(context)" in script
    assert "context.ownerId === currentOwnerId()" in script
    assert "state.projectId !== expectedProjectId" in script
    assert "returnedProjectId !== expectedProjectId" in script
    assert "state.pollGeneration += 1;" in script
    assert "generation !== state.pollGeneration" in script
    assert "resetWorkspaceState('');" in script
    assert "let availabilityGeneration = 0;" in loader
    assert "function availabilityIsCurrent(context)" in loader
    assert "context.ownerId === currentOwnerId()" in loader
    assert "if (!availabilityIsCurrent(context)) return false;" in loader
    assert "window.addEventListener('crump:authentication-required'" in loader


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
    assert "request cancellation. Autonomous Crump checks that request" in script
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
