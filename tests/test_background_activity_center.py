from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "public" / "crump-activity-center-1.0.js").read_text(encoding="utf-8")
CSS = (ROOT / "public" / "crump-activity-center-1.0.css").read_text(encoding="utf-8")
BEHAVIOR = (ROOT / "scripts" / "verify-activity-center-behavior.cjs").read_text(encoding="utf-8")


def test_activity_center_reuses_owner_scoped_product_state_without_new_mutations() -> None:
    assert "askcrump.videoJob53" in JS
    assert "askcrump.videoRequest53" in JS
    assert "video: '/api/media/video'" in JS
    assert "code: '/api/code/activity'" in JS
    assert "dueFeeds.map(feed => fetchActivity(paths[feed]))" in JS
    assert "credentials: 'same-origin'" in JS
    assert "method: 'GET'" in JS
    assert "ACTIVE_REFRESH_MS = 30 * 1000" in JS
    assert "IDLE_REFRESH_MS = 5 * 60 * 1000" in JS
    assert "feedFailureCount: {video: 0, code: 0}" in JS
    assert "function dueNetworkFeeds(force)" in JS
    assert "function feedNextNetworkDelay(feed)" in JS
    assert "if (state.networkInFlight) return state.networkInFlight" in JS
    assert "if (!ownerUserId || ownerUserId !== state.userId || document.hidden)" in JS

    # The center observes; it never starts, cancels, retries, or charges work.
    for forbidden in (
        "method: 'POST'",
        "method: 'PATCH'",
        "method: 'DELETE'",
        "/api/media/video/${",
        "creditsRequired",
        "retryMessage(",
    ):
        assert forbidden not in JS


def test_activity_persistence_is_user_scoped_content_free_and_bounded() -> None:
    assert "askcrump.activityCenter.v1" in JS
    assert "String(payload?.userId || '') !== userId" in JS
    assert "MAX_STORED_ITEMS = 18" in JS
    assert "FINISHED_TTL_MS = 7 * 24 * 60 * 60 * 1000" in JS
    assert "ACTIVE_TTL_MS = 3 * 24 * 60 * 60 * 1000" in JS
    assert "const OPAQUE_ID" in JS

    persisted_shape = re.search(
        r"storage\.setItem\(key, JSON\.stringify\(\{(.*?)\}\)\);",
        JS,
        re.DOTALL,
    )
    assert persisted_shape
    payload = persisted_shape.group(1)
    assert "version" in payload
    assert "userId" in payload
    assert "items" in payload

    # Prompts, response content, filenames, URLs, and errors are never placed
    # in the activity record or panel.
    safe_item = JS[JS.index("function safeItem"):JS.index("function itemExpired")]
    for private_field in ("prompt", "content", "fileName", "filename", "url", "error"):
        assert private_field not in safe_item
    for safe_code_field in ("taskId", "projectId", "codeStatus"):
        assert safe_code_field in safe_item
    assert "title.textContent = `${kindLabel(item.kind)}" in JS


def test_activity_center_tracks_only_provable_video_and_creative_states() -> None:
    assert "const KINDS = new Set(['video', 'image', 'document', 'presentation', 'code'])" in JS
    assert "const STATUSES = new Set(['queued', 'running', 'ready', 'failed'])" in JS
    assert "meta.creativeTool === 'image'" in JS
    assert "artifactKind(meta.artifactFormat)" in JS
    assert "assistant?.imageFile || assistant?.imageUrl" in JS
    assert "message?.replyStatus === 'processing'" in JS
    assert "message?.replyStatus === 'replied'" in JS
    assert "normalizeVideoStatus(job?.status)" in JS
    assert "Continues securely outside Video Studio" in JS
    assert "Working in this signed-in session" in JS

    reconcile = JS[JS.index("function reconcileConversationWork"):JS.index("function normalizeVideoStatus")]
    assert "assistant?.timestamp || assistant?.createdAt, timestamp" in reconcile
    assert "message?.updatedAt || message?.failedAt, timestamp" in reconcile
    assert "updatedAt: terminalTimestamp" in reconcile
    assert "updatedAt: now()" not in reconcile
    assert "if (jobs.some(job => safeOpaque(job?.id))) removeItem('video-request:pending')" not in JS


def test_activity_center_ingests_content_free_autonomous_status_and_reopens_exact_task() -> None:
    assert "const CODE_STATUSES = new Set" in JS
    assert "function normalizeCodeStatus(value)" in JS
    assert "function reconcileCodeResponse(data, ownerUserId)" in JS
    assert "ownerUserId !== state.userId || currentUserId() !== ownerUserId" in JS
    assert "const activity = Array.isArray(data?.activity) ? data.activity.slice(0, MAX_STORED_ITEMS)" in JS
    assert "id: `code:${taskId}`" in JS
    assert "source: 'code'" in JS
    assert "kind: 'code'" in JS
    assert "window.CrumpCodeLoader.open({projectId: item.projectId, taskId: item.taskId})" in JS

    reconcile = JS[JS.index("function reconcileCodeResponse"):JS.index("function counts")]
    for private_field in (
        "objective",
        "repository",
        "result",
        "patch",
        "receipt",
        "sandbox",
        "failure",
    ):
        assert private_field not in reconcile.lower()


def test_activity_center_has_executable_terminal_timeout_priority_and_focus_coverage() -> None:
    assert "verifyTerminalPermanence(browser)" in BEHAVIOR
    assert "verifyFailurePriorityAndFocus(browser)" in BEHAVIOR
    assert "verifyTimeoutAndBackoff(browser)" in BEHAVIOR
    assert "verifyCodeActivityContinuity(browser)" in BEHAVIOR
    assert "verifyCodeOwnerFence(browser)" in BEHAVIOR
    assert "verifyIndependentFeedBackoff(browser)" in BEHAVIOR
    assert "window.__CrumpActivityCenterTestHooks.reconcileStoredVideo()" in BEHAVIOR
    assert "hooks.refreshVideos({force: false})" in BEHAVIOR
    assert "hooks.abortNetwork('visibility')" in BEHAVIOR
    assert "crump:authentication-required" in BEHAVIOR
    assert "assert.equal(result.firstStatus, 'failed')" in BEHAVIOR
    assert "assert.equal(result.itemCloseFocus, 'crumpActivityTrigger')" in BEHAVIOR
    assert "'verify-activity-center-behavior.cjs'" in (
        ROOT / "scripts" / "verify-browser-control-matrix.mjs"
    ).read_text(encoding="utf-8")


def test_activity_actions_only_open_existing_public_product_destinations() -> None:
    assert "window.CrumpVision?.navigate" in JS
    assert "window.CrumpVision.navigate('video')" in JS
    assert "window.CrumpProduct53.open('video')" in JS
    assert "window.CrumpVision.navigate('ask')" in JS
    assert "window.loadChat?.(chatId)" in JS
    assert "window.CrumpCodeLoader.open({projectId: item.projectId, taskId: item.taskId})" in JS
    assert "window.CrumpActivityCenter = Object.freeze" in JS
    assert "window.addEventListener('crump:activity'" in JS
    assert "window.addEventListener('crump:authenticated-ready', activate)" in JS
    assert "window.addEventListener('crump:authentication-required', deactivate)" in JS


def test_activity_panel_is_accessible_mobile_safe_and_reduced_motion_aware() -> None:
    for contract in (
        "aria-haspopup', 'dialog'",
        "aria-controls', 'crumpActivityPanel'",
        "aria-expanded', 'false'",
        "panel.setAttribute('role', 'dialog')",
        "panel.setAttribute('aria-modal', 'false')",
        "aria-labelledby', 'crumpActivityTitle'",
        "aria-live=\"polite\"",
        "event.key === 'Escape'",
        "closePanel()",
    ):
        assert contract in JS

    assert "env(safe-area-inset-top)" in CSS
    assert "env(safe-area-inset-right)" in CSS
    assert "env(safe-area-inset-bottom)" in CSS
    assert "var(--cv-mobile-nav, 72px)" in CSS
    assert "@media (max-width: 680px)" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert ".crump-v1-keyboard-visible .crump-activity-trigger" in CSS
    assert 'html[data-theme="dark"] body.crump-v1-body' in CSS
    assert "right: max(76px, calc(env(safe-area-inset-right) + 64px))" in CSS
    assert "right: max(68px, calc(env(safe-area-inset-right) + 58px))" in CSS
    assert "min-height: 44px" in CSS
    assert "width: 44px" in CSS
    assert "height: 44px" in CSS
    assert "from { opacity: .78" in CSS
    assert "crump-activity-has-connection-status" in CSS
    assert "right: max(322px, calc(env(safe-area-inset-right) + 310px))" in CSS
    assert "@media (max-width: 920px)" in CSS
    assert "max-width: calc(100vw - 184px)" in CSS
    assert "new MutationObserver(syncHeaderStatus)" in JS
    assert "refreshRelativeTimes()" in JS
    assert "focusedItemId" in JS


def test_activity_theme_tokens_keep_text_legible_in_both_appearances() -> None:
    def tokens(selector: str) -> dict[str, str]:
        match = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\n\}}", CSS, re.DOTALL)
        assert match
        return dict(re.findall(r"(--activity-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", match.group(1)))

    def luminance(color: str) -> float:
        values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        channels = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in values
        ]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    def contrast(foreground: str, background: str) -> float:
        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    light = tokens("body.crump-v1-body")
    dark = tokens('html[data-theme="dark"] body.crump-v1-body')
    for palette in (light, dark):
        for foreground in (
            "--activity-text",
            "--activity-text-soft",
            "--activity-muted",
            "--activity-label",
            "--activity-ready",
            "--activity-running",
            "--activity-queued",
            "--activity-failed",
        ):
            assert contrast(palette[foreground], palette["--activity-bg"]) >= 4.5, foreground
        for status in ("ready", "running", "queued", "failed"):
            assert contrast(
                palette[f"--activity-{status}"],
                palette[f"--activity-{status}-soft"],
            ) >= 4.5, status
