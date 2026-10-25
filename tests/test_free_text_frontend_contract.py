from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_free_allowance_is_server_authoritative_for_guest_and_registered_free_users():
    auth = read_public("auth-controller.js")
    transport = read_public("chat-resilience.js")
    app = read_public("app.js")
    composer = read_public("crump-5.0.js")

    assert "function parseServerAllowance(payload)" in auth
    assert "payload.freeMessageAllowance" in auth
    assert "payload.dailyUsage?.freeMessageAllowance" in auth
    assert "freeMessagesRemaining" in auth
    assert "freeMessageNextAvailableAt" in auth
    assert "windowKind: String(allowance.windowKind" in auth
    assert "freeAllowanceState = {...allowance" in auth
    assert "'/api/usage/check'" in auth
    assert "refreshAllowance: refreshFreeAllowanceFromServer" in auth
    assert "freeAllowanceState.used + 1" not in auth
    assert "if (used === null && remaining === null) return null;" in auth
    assert "noteMessageSent: applyServerAllowance" in auth

    assert "applyServerAllowance(data);" in transport
    assert "applyServerAllowance(job.data);" in transport
    assert "FREE_TEXT_LIMIT_REACHED" in transport
    assert "window.CrumpAccess?.applyServerAllowance?.(data);" in app
    assert composer.count("window.CrumpAccess?.applyServerAllowance?.(data);") == 2


def test_free_allowance_copy_is_exact_about_rolling_window_and_signup_continuity():
    app = read_public("app.html")
    auth = read_public("auth-controller.js")
    transport = read_public("chat-resilience.js")

    assurance = (
        "Free includes up to 5 text messages in any rolling 24-hour window. "
        "Advanced tools require a paid plan."
    )
    assert assurance in app
    assert assurance in auth
    assert "Signing up does not add another five messages." in auth
    assert "preserve this conversation and your remaining allowance" in auth
    assert "Your next free text message becomes available" in auth
    assert "five free text messages in the rolling 24-hour window" in transport

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PUBLIC.rglob("*")
        if path.suffix in {".html", ".js"}
    )
    for retired_claim in (
        "25 messages each day",
        "25 included messages each day",
        "2 private Projects",
        "two Free Projects",
        "1 live research request each day",
    ):
        assert retired_claim not in combined


def test_creation_actions_fail_closed_while_owned_results_and_account_controls_remain_open():
    auth = read_public("auth-controller.js")
    body = read_public("crump-v1-body.js")
    composer = read_public("crump-5.0.js")
    loader = read_public("crump-product-loader.js")
    product = read_public("crump-product-5.3.js")
    code = read_public("crump-code-loader.js")
    legacy = read_public("app.js")
    attach_sheet = read_public("crump-5.2.js")

    assert "function hasPaidToolAccess" in auth
    assert "return Boolean(user?.internalAccess) || PAID_TIERS.has(effectiveTier(user));" in auth
    assert "function requireOwnedWorkspace(featureLabel = 'That workspace')" in auth
    assert "if (isGuestUser(user))" in auth
    assert "requireOwnedWorkspace," in auth
    assert "requirePaidTool: showPaidToolPrompt" in auth
    assert "accessCode: 'SUBSCRIPTION_REQUIRED'" in auth

    for label in (
        "Research",
        "Image Studio",
        "Files",
        "Autonomous Crump",
    ):
        assert f"requirePaidTool('{label}')" in body

    for label in ("Projects", "Video Studio", "Files"):
        assert f"requireOwnedWorkspace('{label}')" in body

    assert "if (!requirePaidTool(imageReference ? 'Image Studio' : 'Files')) return;" in composer
    assert "if (!requirePaidTool('Files and creative tools')) return;" in composer
    assert "if (!requirePaidTool('Image Studio')) return;" in composer
    assert "if (!requirePaidTool('Document Studio')) return;" in composer
    assert "const guard = window.CrumpAccess?.requireOwnedWorkspace;" in loader
    assert "if (typeof guard !== 'function')" in loader
    assert "return Promise.resolve(false);" in loader
    assert "if (!window.CrumpAccess?.requireOwnedWorkspace?.(labels[tab] || 'Studios')) return;" in product
    assert "if (!window.CrumpAccess?.requireOwnedWorkspace?.('Projects')) return false;" in product
    assert "if (!window.CrumpAccess?.requireOwnedWorkspace?.('Files')) return false;" in product
    assert "if (!window.CrumpAccess?.requireOwnedWorkspace?.('Manuscripts')) return false;" in product
    assert "function requirePaidMutation(label)" in product
    for label in (
        "Project creation",
        "Project changes",
        "Manuscript creation",
        "Manuscript generation",
        "Manuscript editing",
        "Manuscript export",
        "Video generation",
    ):
        assert f"requirePaidMutation('{label}')" in product
    assert "action === 'resume' && !requirePaidMutation('Manuscript generation')" in product
    assert "if (!window.CrumpAccess?.requirePaidTool?.('Autonomous Crump')) return false;" in code
    assert "function requirePaidToolAccess(label)" in legacy
    assert "if (!requirePaidToolAccess('File attachments')) return;" in legacy
    assert "selectedFiles.length && !requirePaidToolAccess('File attachments')" in legacy
    assert "function requirePaidTool52(label)" in attach_sheet
    assert "if (!requirePaidTool52('Attachments and creation tools')) return;" in attach_sheet
    assert "if (!requirePaidTool52('File attachments')) return;" in attach_sheet
    assert "if (!requirePaidTool('Image Studio')) return;" in composer

    settings = body[body.index("case 'settings':"):body.index("case 'billing':")]
    billing = body[body.index("case 'billing':"):body.index("case 'research':")]
    assert "requirePaidTool" not in settings
    assert "requirePaidTool" not in billing
    assert "forwardClick('settingsBtn')" in settings
    assert "forwardClick('upgradeBtnSidebar')" in billing


def test_guest_and_registered_free_receive_distinct_upgrade_actions():
    auth = read_public("auth-controller.js")

    assert "if (isGuestUser(window.currentUser || activeUser)) showGuestWall();" in auth
    assert "else showPaidToolPrompt('More messages');" in auth
    assert "link.textContent = guest ? 'Save conversation' : 'Compare plans';" in auth
    assert "Create a free account to preserve this conversation" in auth
    assert "window.showUpgradePrompt?.({" in auth
    assert "source: 'advanced_tool_guard'" in auth


def test_guest_free_contract_auth_asset_is_cache_refreshable():
    app = read_public("app.html")
    worker = read_public("sw.js")
    asset = "/auth-controller.js?v=5.9.76-workspace-opened-retry-1"

    assert asset in app
    assert asset in worker


def test_guest_free_frontend_release_is_atomic_across_web_native_and_pwa():
    app = read_public("app.html")
    runtime = read_public("runtime-body-v1.js")
    worker = read_public("sw.js")
    loader = read_public("crump-product-loader.js")
    native = (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8")
    legacy_runtime = read_public("runtime-config.js")
    v1_runtime = read_public("runtime-config-v1.js")

    assert "/auth-styles.css?v=5.9.76-guest-free-contract-2" in app
    assert "/auth-styles.css?v=5.9.76-guest-free-contract-2" in worker
    assert "/runtime-body-v1.js?v=5.9.76-legacy-project-resume-truth-1" in app
    assert "/runtime-body-v1.js?v=5.9.76-legacy-project-resume-truth-1" in worker
    assert "ask-crump-new-body-v1-r276-initial-chat-owner-reconciliation-1" in worker

    released_assets = (
        "/chat-resilience.js?v=5.9.76-chat-owner-boundary-1&workspaceRelease=guest-free-contract-2",
        "/app.js?v=5.9.76-native-push-owner-fence-1&workspaceRelease=guest-free-contract-2",
        "/crump-5.0.js?v=5.9.76-chat-owner-boundary-1&workspaceRelease=guest-free-contract-2",
        "/crump-billing-5.1.js?v=5.9.76-private-owner-boundary-1&workspaceRelease=guest-free-contract-2",
        "/crump-5.2.js?v=5.9.76-legacy-attachment-owner-fence-1&workspaceRelease=guest-free-contract-2",
        "/crump-v1-body.js?v=5.9.76-atelier-workspace-1&workspaceRelease=guest-free-contract-2",
        "/crump-product-loader.js?v=5.9.76-legacy-project-resume-truth-1&workspaceRelease=guest-free-contract-2",
        "/crump-code-loader.js?v=5.9.76-account-owner-boundary-1&workspaceRelease=guest-free-contract-2",
    )
    for asset in released_assets:
        assert asset in runtime
        assert asset in native
        assert asset in worker

    for asset in released_assets[2:5]:
        assert asset in legacy_runtime
        assert asset in v1_runtime

    assert "/crump-product-5.3.js?v=5.9.76-legacy-project-resume-truth-1&workspaceRelease=guest-free-contract-2" in loader


def test_explicit_signup_intent_never_bootstraps_or_routes_a_guest_into_the_workspace():
    auth = read_public("auth-controller.js")

    assert "if (signupRequested) {\n      showAuth('register');" in auth
    assert "const mayStartGuest = !signupRequested" in auth
    assert "&& (freeGuestRequested || !accountOnDevice);" in auth
    assert "if (signupRequested && isGuestUser(session.data.user))" in auth
    guest_signup = auth[auth.index("if (signupRequested && isGuestUser(session.data.user))") :]
    guest_signup = guest_signup[:guest_signup.index("await prepareAuthenticatedWorkspace();")]
    assert "showAuth('register');" in guest_signup
    assert "routeAuthenticatedUser(activeUser)" not in guest_signup
