from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "public" / "app.html").read_text(encoding="utf-8")
SHELL = (ROOT / "public" / "crump-vision-shell-1.0.js").read_text(encoding="utf-8")
BROWSER = (ROOT / "public" / "crump-browser-workspace-1.0.js").read_text(encoding="utf-8")
CSS = (ROOT / "public" / "crump-browser-workspace-1.0.css").read_text(encoding="utf-8")
WORKER = (ROOT / "public" / "sw.js").read_text(encoding="utf-8")
RUNTIME = (ROOT / "public" / "runtime-body-v1.js").read_text(encoding="utf-8")
NATIVE = (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8")


def test_shell_has_exact_clean_information_architecture():
    assert "var ORDER = ['home', 'chats', 'projects', 'library', 'studios', 'you'];" in SHELL
    assert "var MOBILE_ORDER = ['home', 'chats', 'projects', 'library', 'studios'];" in SHELL
    assert "<span>New</span>" in SHELL
    assert "takeOverMobileUtility" in SHELL
    assert "cvMobileYou" in SHELL


def test_browser_is_first_class_without_cluttering_primary_navigation():
    assert "browser: 'browser'" in SHELL
    assert "registerView('browser'" in BROWSER
    assert "data-v1-command=\"browser\"" in APP
    assert "Browse and research" in APP
    assert "'browser'" not in "var ORDER = ['home', 'chats', 'projects', 'library', 'studios', 'you'];"
    assert "if (id === 'browser') return;" in SHELL


def test_browser_ui_has_truthful_four_stage_workflow_and_controls():
    for label in ("Brief", "Progress", "Review", "Result"):
        assert label in BROWSER
    for status in (
        "queued", "preparing", "running", "paused", "waiting_approval",
        "blocked", "done", "failed", "cancelled",
    ):
        assert status in BROWSER
    for control in ("Pause", "Resume", "Cancel", "Approve once", "Deny"):
        assert control in BROWSER
    assert "External effects appear only after durable settlement." in BROWSER
    assert "The page cannot approve this." in BROWSER
    assert "review decision outcome is unknown" in BROWSER
    assert "reconcileAmbiguousMutation" in BROWSER
    assert "`/requests/${mutation.requestId}`" in BROWSER
    assert "if (typeof status.released !== 'boolean')" in BROWSER
    assert "if (!Array.isArray(response.tasks))" in BROWSER
    assert "function updateRenderedRegions" in BROWSER
    assert "previousTasksFingerprint" in BROWSER
    assert "previousActiveFingerprint" in BROWSER
    assert "tasks: tasksChanged" in BROWSER
    assert "main: availabilityChanged || activeChanged" in BROWSER
    assert "notices.dataset.cbwNotices = '1'" in BROWSER


def test_browser_ui_is_owner_scoped_and_does_not_persist_private_content():
    assert "CrumpAuthBoundary?.authenticatedUserId" in BROWSER
    assert "window.CrumpAuthBoundary.register('browser-workspace', scrub)" in BROWSER
    assert "state.draft = {objective: '', sites: '', boundaries: '', timeLimitMinutes: '20'};" in BROWSER
    assert "window.addEventListener('crump:body-runtime-ready'" in BROWSER
    assert "ensureBoundaryRegistration();" in BROWSER
    assert "X-Ask-Crump-Expected-Owner" in BROWSER
    assert "credentials: 'same-origin'" in BROWSER
    assert "cache: 'no-store'" in BROWSER
    assert "redirect: 'error'" in BROWSER
    assert "localStorage" not in BROWSER
    assert "sessionStorage" not in BROWSER


def test_browser_assets_are_atomic_across_web_pwa_and_native():
    release = "5.9.76-premium-browser-workspace-1"
    cache = "ask-crump-new-body-v1-r283-premium-browser-workspace-1"
    for asset in (
        "crump-vision-shell-1.0.js",
        "crump-vision-studios-1.0.js",
        "crump-browser-workspace-1.0.css",
        "crump-browser-workspace-1.0.js",
    ):
        assert f"/{asset}?v={release}" in APP
        assert f"/{asset}?v={release}" in WORKER
    assert "await cp(publicDir, outDir, { recursive: true });" in NATIVE
    assert "../public/app.html" in NATIVE
    assert f"/runtime-body-v1.js?v={release}" in APP
    assert f"/runtime-body-v1.js?v={release}" in WORKER
    for asset in (
        "onboarding.js",
        "crump-5.2.js",
        "crump-v1-body.js",
        "crump-polish-5.6.js",
    ):
        assert f"/{asset}?v={release}" in RUNTIME
        assert f"/{asset}?v={release}" in WORKER
        assert f"/{asset}?v={release}" in NATIVE
    assert cache in WORKER


def test_mobile_accessibility_and_reduced_motion_contract():
    assert "width: 44px" in CSS
    assert "height: 44px" in CSS
    assert "min-height: 44px" in CSS
    assert "env(safe-area-inset" in (ROOT / "public" / "crump-vision-shell-1.0.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in CSS
    assert "aria-live" in BROWSER
    assert "aria-current" in BROWSER
