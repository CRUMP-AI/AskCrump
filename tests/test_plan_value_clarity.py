from pathlib import Path

from backend.feature_service import POLICIES, PROJECT_LIMITS


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_public_plan_comparison_matches_server_enforced_allowances():
    landing = read_public("ask-crump.html")
    config = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")

    assert PROJECT_LIMITS == {"free": 2, "professional": 25, "enterprise": 200}
    assert POLICIES["research"].included_daily == {
        "free": 1,
        "professional": 20,
        "enterprise": 50,
    }
    assert POLICIES["image"].included_daily == {
        "free": 0,
        "professional": 1,
        "enterprise": 2,
    }
    assert POLICIES["visual_analysis"].included_daily == {
        "free": 0,
        "professional": 20,
        "enterprise": 100,
    }
    assert "professional_daily_messages=int(os.getenv('PROFESSIONAL_DAILY_MESSAGES', '500'))" in config
    assert "enterprise_daily_messages=int(os.getenv('ENTERPRISE_DAILY_MESSAGES', '5000'))" in config

    for expected in (
        "25 included messages each day",
        "2 private Projects",
        "1 live research request each day",
        "500 included messages each day",
        "25 private Projects",
        "20 research, 1 image, and 20 visual analyses each day",
        "5,000 included messages each day",
        "200 private Projects",
        "50 research, 2 images, and 100 visual analyses each day",
        "10-second Cinematic video access",
    ):
        assert expected in landing

    assert "Premium video and other high-compute generations use Crump Credits." in landing
    assert "Crump Code" not in landing
    assert "Crump Voice" not in landing


def test_signed_in_plan_cards_state_specific_value_and_metering():
    billing = read_public("crump-billing-5.1.js")
    final_billing = read_public("crump-5.2.js")
    subscriptions = read_public("crump-subscriptions-5.3.2.js")
    stylesheet = read_public("crump-billing-5.1.css")

    for source in (billing, final_billing, subscriptions):
        for expected in (
            "500 included messages daily",
            "25 private Projects",
            "20 research · 1 image · 20 visual analyses daily",
            "5,000 included messages daily",
            "200 private Projects",
            "50 research · 2 images · 100 visual analyses daily",
            "10-second Cinematic video access",
            "Premium video and other high-compute generations use Crump Credits.",
        ):
            assert expected in source
        assert "billing51-plan-benefits" in source

    for dynamic_source in (billing, subscriptions):
        assert "textContent = item" in dynamic_source

    assert ".billing51-plan-benefits" in stylesheet
    assert ".billing51-plan-meter-note" in stylesheet


def test_plan_center_measurement_is_daily_content_free_and_fail_open():
    billing = read_public("crump-billing-5.1.js")
    analytics = read_public("product-analytics.js")
    migration = (
        ROOT / "migrations" / "20260829140155_plan_center_conversion.sql"
    ).read_text(encoding="utf-8")
    normalized = migration.lower()

    assert "PlanCenterViewed" in analytics
    assert "eventKey: 'plan-center-viewed'" in billing
    assert "window.CrumpAnalytics?.track?.('PlanCenterViewed'" in billing
    assert "void recordPlanCenterView(options);" in billing
    assert "eventName: 'PlanCenterViewed'" in billing
    assert "eventKey: 'plan-center-viewed'" in billing
    assert "dataset.crumpPlanCenterEvent" in billing
    final_billing = read_public("crump-5.2.js")
    assert "function showBillingCenter52(options = {})" in final_billing
    assert "window.CrumpAnalytics?.track?.('PlanCenterViewed'" in final_billing
    assert "void recordPlanCenterView(options);" in final_billing
    assert "eventName: 'PlanCenterViewed'" in final_billing
    assert "eventKey: 'plan-center-viewed'" in final_billing
    assert "dataset.crumpPlanCenterEvent" in final_billing
    assert "button.addEventListener('click', () => showBillingCenter52({source: 'settings'}));" in final_billing
    tracker = billing[
        billing.index("function recordPlanCenterView"):
        billing.index("async function jsonFetch")
    ]
    assert "prompt" not in tracker.lower()
    assert "filename" not in tracker.lower()
    assert "email" not in tracker.lower()
    assert "payment" not in tracker.lower()

    assert "'PlanCenterViewed'" in migration
    assert "product_plan_conversion_snapshot" in migration
    assert "checkout_opened_after_plan_view" in migration
    assert "checkout_completed_after_plan_view" in migration
    assert "security invoker" in normalized
    assert ") from public, anon, authenticated;" in normalized
    assert ") to service_role;" in normalized
    assert "metadata jsonb" not in normalized
    assert "prompt" not in normalized
    assert "email" not in normalized


def test_both_plan_center_owners_contain_and_restore_modal_focus():
    billing = read_public("crump-billing-5.1.js")
    final_billing = read_public("crump-5.2.js")

    for source in (billing, final_billing):
        assert "const BILLING_FOCUSABLE" in source
        assert "element.setAttribute('inert', '')" in source
        assert "element.setAttribute('aria-hidden', 'true')" in source
        assert "element.removeAttribute('inert')" in source
        assert "element.removeAttribute('aria-hidden')" in source
        assert "event.key !== 'Tab'" in source
        assert "active === first || !modal.contains(active)" in source
        assert "active === last || !modal.contains(active)" in source
        assert "requestAnimationFrame(() => trigger.focus?.({preventScroll: true}))" in source
        assert 'aria-modal="true" aria-labelledby="billing' in source
        assert 'tabindex="-1"' in source


def test_plan_center_containment_assets_are_versioned_everywhere():
    versioned_billing = "/crump-billing-5.1.js?v=5.9.76-billing-modal-containment-1"
    versioned_final = "/crump-5.2.js?v=5.9.76-billing-modal-containment-1"
    sources = (
        read_public("runtime-body-v1.js"),
        read_public("sw.js"),
        read_public("runtime-config.js"),
        read_public("runtime-config-v1.js"),
        (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8"),
    )

    for source in sources:
        assert versioned_billing in source
        assert versioned_final in source
    assert "ask-crump-new-body-v1-r139" in read_public("sw.js")
    assert "/runtime-body-v1.js?v=5.9.76-billing-modal-containment-1" in read_public("app.html")


def test_browser_fixture_uses_the_production_plan_center_layers():
    fixture = (
        ROOT / "tests" / "fixtures" / "plan-center-clarity.html"
    ).read_text(encoding="utf-8")

    assert "/public/crump-billing-5.1.css" in fixture
    assert "/public/crump-billing-5.1.js" in fixture
    assert "/public/crump-5.2.js" in fixture
    assert "billing-modal-containment-fixture-1" in fixture
    assert "/public/crump-subscriptions-5.3.2.js" in fixture
    assert "window.__planCenterEvents" in fixture
    assert "fixture-user" in fixture
    assert 'id="billingFixtureBackground"' in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert "/api/stripe/create-checkout-session" not in fixture
