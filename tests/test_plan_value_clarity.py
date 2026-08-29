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
    assert "void window.CrumpAnalytics?.track('PlanCenterViewed'" in billing
    assert "recordPlanCenterView(options);" in billing
    final_billing = read_public("crump-5.2.js")
    assert "function showBillingCenter52(options = {})" in final_billing
    assert "void window.CrumpAnalytics?.track('PlanCenterViewed'" in final_billing
    assert "recordPlanCenterView(options);" in final_billing
    assert "button.addEventListener('click', () => showBillingCenter52({source: 'settings'}));" in final_billing
    tracker = billing[
        billing.index("function recordPlanCenterView"):
        billing.index("async function jsonFetch")
    ]
    assert "prompt" not in tracker.lower()
    assert "content" not in tracker.lower()

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


def test_browser_fixture_uses_the_production_plan_center_layers():
    fixture = (
        ROOT / "tests" / "fixtures" / "plan-center-clarity.html"
    ).read_text(encoding="utf-8")

    assert "/public/crump-billing-5.1.css" in fixture
    assert "/public/crump-billing-5.1.js" in fixture
    assert "/public/crump-5.2.js" in fixture
    assert "/public/crump-subscriptions-5.3.2.js" in fixture
    assert "window.__planCenterEvents" in fixture
    assert "fixture-user" in fixture
    assert "/api/stripe/create-checkout-session" not in fixture
