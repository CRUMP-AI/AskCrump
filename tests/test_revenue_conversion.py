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


def test_signup_deep_link_opens_registration_and_tracks_the_funnel():
    app = read("public/app.html")
    controller = read("public/auth-controller.js")

    assert '/_vercel/insights/script.js' in app
    assert "params.get('signup') === '1'" in controller
    assert "showAuth(signupRequested ? 'register' : 'login')" in controller
    assert "SignupIntent" in controller
    assert "SignupSubmitted" in controller
    assert "AccountCreated" in controller
    assert "registerEmail" not in controller[controller.index("function trackFunnel"):controller.index("function applyServerSettings")]


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

    assert '"version": "5.9.1"' in package
    assert "__version__ = '5.9.1'" in backend
    assert "ask-crump-new-body-v1-r35" in worker
