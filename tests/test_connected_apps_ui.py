from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "public" / "app.html").read_text(encoding="utf-8")
JS = (ROOT / "public" / "connected-apps-ui.js").read_text(encoding="utf-8")
CSS = (ROOT / "public" / "connected-apps-ui.css").read_text(encoding="utf-8")
RUNTIME = (ROOT / "public" / "runtime-body-v1.js").read_text(encoding="utf-8")
SW = (ROOT / "public" / "sw.js").read_text(encoding="utf-8")
UI_FUNCTIONS = (ROOT / "public" / "ui-functions.js").read_text(encoding="utf-8")
NATIVE_BUILD = (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8")


def test_connections_surface_is_static_hidden_and_truthful() -> None:
    assert re.search(
        r'id="settingsNavConnections"[^>]+aria-hidden="true"[^>]+hidden', APP
    )
    assert re.search(
        r'id="settingsPanelConnections"[^>]+aria-hidden="true"[^>]+hidden', APP
    )
    assert "Crump never receives your password" in APP
    assert "external writes stay behind a review step" in APP
    assert "Nothing is connected until you approve it there" in APP
    assert "Checking secure connection availability" in APP


def test_connections_surface_covers_both_providers_and_resources() -> None:
    for binding in (
        'data-connected-start="google:mail:read"',
        'data-connected-start="google:mail:manage"',
        'data-connected-start="google:calendar:read"',
        'data-connected-start="google:calendar:manage"',
        'data-connected-start="microsoft:mail:read"',
        'data-connected-start="microsoft:mail:manage"',
        'data-connected-start="microsoft:calendar:read"',
        'data-connected-start="microsoft:calendar:manage"',
    ):
        assert binding in APP
    for binding in (
        'data-connected-grant="google:mail"',
        'data-connected-grant="google:calendar"',
        'data-connected-grant="microsoft:mail"',
        'data-connected-grant="microsoft:calendar"',
    ):
        assert binding in APP
    for area in (
        'id="connectedAppsConnections"',
        'id="connectedAppsTasks"',
        'id="connectedAppsApprovals"',
        'id="connectedAppsSchedules"',
        'id="connectedAppsActivity"',
    ):
        assert area in APP


def test_connected_workspace_is_a_truthful_operator_surface() -> None:
    assert "Delegate with proof, not guesswork" in APP
    assert "Ask in the conversation" in APP
    assert "review every external change" in APP
    assert "follow durable progress and receipts" in APP
    for section in ("connections", "approvals", "tasks", "schedules", "activity"):
        assert f'data-connected-jump="{section}"' in APP
    for target in (
        "connectedAppsAccounts",
        "connectedAppsApprovals",
        "connectedAppsTasks",
        "connectedAppsSchedules",
        "connectedAppsActivity",
    ):
        assert f'aria-controls="{target}"' in APP
    assert re.search(
        r'id="connectedAppsApprovals"[^>]+aria-live="polite"', APP
    )
    assert APP.index('id="connectedAppsApprovals"') < APP.index(
        'id="connectedAppsTasks"'
    )
    for state in (
        "active",
        "waiting_approval",
        "clarification",
        "completed",
        "failed",
        "cancelled",
        "expired",
        "effect_unknown",
        "limit_reached",
    ):
        assert f"{state}:" in JS or f"'{state}'" in JS


def test_task_timeline_is_owner_revision_bound_and_fails_closed() -> None:
    assert "request('/tasks', {}, boundary)" in JS
    assert "renderTasks(tasks.tasks)" in JS
    assert "exactKeys(record, expected)" in JS
    assert "record.maxSteps !== 8" in JS
    assert "record.currentStep > record.maxSteps" in JS
    assert "record.status === 'waiting_approval'" in JS
    assert "record.pendingApprovalId !== null" in JS
    assert "function localTaskTitle(chatId)" in JS
    assert "chats.length > 1_000" in JS
    assert "title.length > 120" in JS
    assert "localTaskTitle(record.chatId)" in JS
    assert "`/tasks/${record.loopId}/cancel`" in JS
    assert "taskStateRevision: record.taskStateRevision" in JS
    assert "confirmed: true" in JS
    assert "Crump will not repeat it automatically" in JS


def test_chat_cards_route_to_truthful_connected_controls() -> None:
    assert "function createConnectedOperatorCard(message)" in UI_FUNCTIONS
    assert "keysAre('loopId', 'currentStep', 'maxSteps'" in UI_FUNCTIONS
    assert "Nothing has been sent or changed" in UI_FUNCTIONS
    assert "No schedule was saved" in UI_FUNCTIONS
    assert "will not repeat the action automatically" in UI_FUNCTIONS
    assert "openWorkspace?.('connections')" in UI_FUNCTIONS
    assert "openWorkspace?.('approvals')" in UI_FUNCTIONS
    assert "openWorkspace?.('schedules')" in UI_FUNCTIONS
    assert "openWorkspace?.('tasks')" in UI_FUNCTIONS
    assert "focusComposer?.()" in UI_FUNCTIONS
    assert "receipt.dataset.connectedOperatorCard = card.state" in UI_FUNCTIONS
    assert "card.hidden = !state.released" in JS


def test_ui_fails_closed_and_is_owner_bound() -> None:
    assert "data.enabled === true" in JS
    assert "data.status === 'ready'" in JS
    assert "providers.length > 0" in JS
    assert "const capabilityMapValid" in JS
    assert "Object.keys(capabilities).length === providers.length" in JS
    assert "new Set(actions).size === actions.length" in JS
    assert "KNOWN_CAPABILITIES.has(value)" in JS
    assert "Object.keys(oauthClientIds).length === providers.length" in JS
    assert "`${provider}:${action}`" in JS
    assert "nav.hidden = !state.released" in JS
    assert "[OWNER_HEADER]: boundary.ownerId" in JS
    assert "credentials: 'same-origin'" in JS
    assert "redirect: 'error'" in JS
    assert "cache: 'no-store'" in JS
    assert "boundaryIsCurrent" in JS
    assert "CrumpAuthBoundary?.register?.('connected-apps-ui', scrub)" in JS
    assert "state.controller?.abort('owner-boundary')" in JS
    assert "state.oauthController?.abort('owner-boundary')" in JS
    assert "controller.abort('response-too-large')" in JS
    assert "REQUEST_TIMEOUT_MS" in JS
    assert "client@example.com" not in JS
    assert "localStorage" not in JS
    assert ".innerHTML" not in JS
    assert "function activeConnection(provider, resource, accountKind)" in JS
    assert "record.accountKind === accountKind" in JS
    assert "return matches.length === 1 ? matches[0] : null" in JS
    assert "new Set(activeKeys).size !== activeKeys.length" in JS
    assert "`${record.provider}:${record.accountKind}:${record.resource}`" in JS
    assert ".map(record => [record.connectionId, record])" in JS


def test_microsoft_account_kinds_remain_distinct_and_explicitly_selectable() -> None:
    assert "Personal Microsoft account" in APP
    assert "Work or school account" in APP
    assert "select.disabled = false" in JS
    assert "activeConnection(provider, resource, accountKind)" in JS
    assert "activeConnection(provider, resource, accountKind);" in JS
    assert "record.accountKind === 'work_school' ? 'Work or school' : 'Personal'" in JS
    assert "connectionId: existing?.connectionId || null" in JS
    assert "...(consent.connectionId ? {connectionId: consent.connectionId} : {})" in JS


def test_ui_requires_two_explicit_oauth_steps_and_exact_provider_host() -> None:
    assert "openConsent(provider, resource, mode, control)" in JS
    assert "connectedAppsConsentContinue" in JS
    assert "confirmed: true" in JS
    assert "accounts.google.com" in JS
    assert "login.microsoftonline.com" in JS
    assert "consent.accountKind === 'personal' ? 'consumers' : 'organizations'" in JS
    assert "`/${microsoftTenant}/oauth2/v2.0/authorize`" in JS


def test_connected_content_ai_processing_is_disclosed_before_oauth() -> None:
    assert "How connected content is processed." in APP
    assert "only the excerpts needed for that request" in APP
    assert "zero-data-retention and no-training routing" in APP
    assert "Provider security, abuse-prevention, and legally required processing" in APP
    assert "Nothing is connected until you approve it there." in APP
    assert "url.protocol !== 'https:'" in JS
    assert "url.username || url.password" in JS
    assert "new Set(keys).size !== keys.length" in JS
    assert "keys.some(key => forbidden.has(key))" in JS
    assert "parameter('client_id') !== state.oauthClientIds.get(consent.provider)" in JS
    assert "parameter('code_challenge_method') !== 'S256'" in JS
    assert "JSON.stringify([...scopes].sort()) !== JSON.stringify(expectedScopes" in JS
    assert "scopes.add('openid')" in JS
    assert "scopes.add('email')" in JS
    assert "scopes.add('offline_access')" in JS
    assert "scopes.add('User.Read')" in JS
    assert "record.requestId !== requestId" in JS
    assert "window.location.assign(destination)" in JS
    assert "url.searchParams.delete('connected-app')" in JS
    assert "marker === 'connected' || marker === 'denied' || marker === 'failed'" in JS
    assert "The account was not connected. Try again from Connections." in JS
    assert "window.history.replaceState" in JS
    assert "The account was connected securely." in JS
    assert "https://www.askcrump.com/api/connected-apps/oauth/callback/" in JS


def test_approval_is_blocked_without_exact_bound_preview() -> None:
    assert "review.approvalBindingSha256 !== record.approvalBindingSha256" in JS
    assert "review.previewSha256 !== record.previewSha256" in JS
    assert "computed !== review.displaySha256" in JS
    assert "decision === 'approved'" in JS
    assert "previewSha256: record.previewSha256" in JS
    assert "approve.disabled = !review || expired" in JS
    assert "deny.disabled = expired" in JS
    assert "Exact cryptographic action preview required" in JS
    assert "You may safely deny it" in JS
    assert "Google mail account" in JS
    assert "{label: 'Attendee effect', value: attendeeEffect}" in JS
    assert "will send invitations to the listed attendees" in JS
    assert "may send cancellation notices to attendees removed by this change" in JS
    assert "will send cancellation notices to the listed attendees" in JS
    assert "connected-approval-token" in JS
    assert "isolated.dir = 'auto'" in JS
    assert "unicode-bidi: plaintext" in CSS
    assert "unicode-bidi: isolate" in CSS
    for binding in (
        "actionId: record.actionId",
        "connectionId: record.connectionId",
        "taskId: record.taskId",
        "turnId: record.turnId",
        "authorizationRevision: record.authorizationRevision",
        "authorizationSnapshotSha256: record.authorizationSnapshotSha256",
        "grantedScopesSha256: record.grantedScopesSha256",
        "policyVersion: record.policyVersion",
        "actionRevision: record.actionRevision",
        "approvalBindingSha256: record.approvalBindingSha256",
        "parametersSha256: record.parametersSha256",
        "resourceVersionSha256: record.resourceVersionSha256",
    ):
        assert binding in JS


def test_schedule_controls_are_revision_bound_and_cancel_visible() -> None:
    assert "expectedTaskStateRevision: record.taskStateRevision" in JS
    assert "requestId: newRequestId()" in JS
    assert "transitionSchedule(record, 'pause'" in JS
    assert "transitionSchedule(record, 'resume'" in JS
    assert "transitionSchedule(record, 'cancel'" in JS
    assert "requiresApprovalEveryRun" in JS
    assert "Every run requires your approval" in JS


def test_oauth_denial_has_truthful_retry_copy() -> None:
    assert "marker === 'denied'" in JS
    assert "state.oauthReturnStatus === 'denied'" in JS
    assert "Permission was not granted. Nothing was connected or changed." in JS


def test_assets_are_loaded_and_cache_busted_as_one_release() -> None:
    version = "5.9.76-connected-operator-workspace-5"
    for source in (RUNTIME, SW, NATIVE_BUILD):
        assert f"/connected-apps-ui.css?v={version}" in source
        assert f"/connected-apps-ui.js?v={version}" in source
    assert "/runtime-body-v1.js?v=5.9.76-login-recovery-visible-1" in APP
    assert "/runtime-body-v1.js?v=5.9.76-login-recovery-visible-1" in SW
    assert "ask-crump-new-body-v1-r282-connected-operator-workspace-5" in SW
    assert "url.pathname === '/connected-apps-ui.css'" in SW
    assert "url.pathname === '/connected-apps-ui.js'" in SW


def test_mobile_accessibility_and_safe_targets_are_styled() -> None:
    assert "min-height: 44px" in CSS
    assert "@media (max-width: 430px)" in CSS
    assert "grid-template-columns: 1fr" in CSS
    assert ":focus-visible" in CSS
    assert "prefers-reduced-motion: reduce" in CSS
    assert "env(safe-area-inset-bottom)" in CSS
    assert ".connected-resource-actions" in CSS
    assert ".connected-grant-state.is-connected" in CSS
    assert ".connected-operator-overview" in CSS
    assert ".connected-workspace-nav button" in CSS
    assert ".connected-task-card" in CSS
    assert ".connected-operator-card" in CSS


def test_connected_apps_javascript_parses() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable")
    subprocess.run(
        [node, "--check", str(ROOT / "public" / "connected-apps-ui.js")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_connected_apps_browser_journey() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("local Playwright runtime is unavailable")
    probe = subprocess.run(
        [node, "-e", "require.resolve('playwright')"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        pytest.skip("local Playwright runtime is unavailable")
    completed = subprocess.run(
        [node, str(ROOT / "scripts" / "verify-connected-apps-ui-browser.cjs")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
