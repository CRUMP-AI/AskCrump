from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_marketing_page_exposes_a_clear_free_to_paid_path():
    page = read("public/index.html")

    assert 'id="pricing"' in page
    assert "Clear pricing. Real runway." in page
    assert "$0" in page and "$20" in page and "$50" in page
    assert "50 · $4.99" in page and "400 · $19.99" in page
    assert "No card required" in page
    assert "eventually choose to pay" not in page
    for plan in ("free", "professional", "enterprise"):
        assert f"plan={plan}" in page
    assert page.count('data-cta="') >= 7


def test_marketing_ctas_are_first_party_analytics_events():
    page = read("public/index.html")
    script = read("public/landing.js")

    assert '/_vercel/insights/script.js' in page
    assert "window.vaq" in script
    assert "MarketingCTA" in script
    assert "link.dataset.cta" in script
    assert "link.dataset.plan" in script
    assert "utm_source" in script
    assert "destination.searchParams.set('acquisition', acquisition)" in script
    assert "sessionStorage.setItem(ACQUISITION_KEY" in script
    assert "document.referrer" in script
    assert "referrer URL" not in script
    assert "window.location.replace('/app')" not in script
    assert 'rel="canonical" href="https://www.askcrump.com/"' in page
    assert 'property="og:title"' in page
    assert 'type="application/ld+json"' in page
    assert 'class="nav-signin"' in page
    assert 'href="/app?signup=1' in page
    assert 'href="https://askcrump.com/app' not in page


def test_public_marketing_surface_is_indexable_while_the_private_app_is_not():
    page = read("public/index.html")
    app = read("public/app.html")
    robots = read("public/robots.txt")
    sitemap = read("public/sitemap.xml")

    assert 'name="robots" content="index,follow' in page
    assert 'name="robots" content="noindex,nofollow"' in app
    assert "Sitemap: https://www.askcrump.com/sitemap.xml" in robots
    assert "Disallow: /app" in robots and "Disallow: /api/" in robots
    assert "<loc>https://www.askcrump.com/</loc>" in sitemap


def test_signup_deep_link_opens_registration_and_tracks_the_funnel():
    app = read("public/app.html")
    controller = read("public/auth-controller.js")

    assert '/_vercel/insights/script.js' in app
    assert "params.get('signup') === '1'" in controller
    assert "showAuth(signupRequested ? 'register' : 'login')" in controller
    assert "SignupIntent" in controller
    assert "SignupSubmitted" in controller
    assert "AccountCreated" in controller
    assert "source: funnelContext().acquisition" in controller
    assert "params.get('acquisition')" in controller
    assert "registerEmail" not in controller[controller.index("function trackFunnel"):controller.index("function applyServerSettings")]


def test_legacy_social_deep_links_keep_channel_attribution_without_relabeling_ctas():
    controller = read("public/auth-controller.js")

    assert "LEGACY_ACQUISITION_SOURCES" in controller
    for channel in (
        "instagram",
        "facebook",
        "facebook-pinned",
        "linkedin",
        "tiktok",
        "youtube",
        "x",
        "referral",
        "clevercrump",
    ):
        assert f"'{channel}'" in controller
    assert "LEGACY_ACQUISITION_SOURCES.has(locationSource)" in controller
    assert "const currentAcquisition = explicitAcquisition || legacyAcquisition" in controller
    assert "acquisition: currentAcquisition || storedAcquisition || 'direct'" in controller
    allowlist = controller[
        controller.index("const LEGACY_ACQUISITION_SOURCES"):
        controller.index("window.va =")
    ]
    for onsite_location in ("hero", "pricing", "footer", "closing", "video"):
        assert f"'{onsite_location}'" not in allowlist


def test_paid_plan_intent_survives_auth_and_stops_before_checkout():
    controller = read("public/auth-controller.js")
    runtime = read("public/runtime-body-v1.js")
    subscriptions = read("public/crump-subscriptions-5.3.2.js")

    assert "askcrump.pending-plan-intent" in controller
    assert "PAID_PLAN_INTENTS = new Set(['professional', 'enterprise'])" in controller
    assert "PLAN_INTENT_TTL_MS" in controller
    assert "crump:plan-intent" in controller
    assert "crump:body-runtime-ready" in runtime
    assert "window.showBillingCenter?.({plan})" in subscriptions
    assert "data-crump-plan" in subscriptions or "dataset.crumpPlan" in subscriptions
    assert "PlanIntentReached" in subscriptions
    listener = subscriptions[subscriptions.index("window.addEventListener('crump:plan-intent'"):]
    assert "openCheckout(plan" not in listener
    assert "crump:plan-intent-consumed" in listener


def test_release_version_and_cache_advance_together():
    package = read("package.json")
    backend = read("backend/version.py")
    worker = read("public/sw.js")

    assert '"version": "5.9.15"' in package
    assert "__version__ = '5.9.15'" in backend
    assert "ask-crump-new-body-v1-r49" in worker


def test_changed_activation_assets_are_release_versioned():
    shell = read("public/app.html")
    worker = read("public/sw.js")

    for asset in (
        "/conversation.css?v=5.9.15",
        "/ui-functions.js?v=5.9.15",
        "/product-analytics.js?v=5.9.15",
        "/app.js?v=5.9.15",
    ):
        assert asset in shell
        assert asset in worker
