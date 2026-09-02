from pathlib import Path
import re

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
        "Advanced Intelligence: Think Longer + Always Review",
        "10-second Cinematic video access",
    ):
        assert expected in landing

    assert "Premium video and other high-compute generations use Crump Credits." in landing
    assert landing.count("Advanced Intelligence: Think Longer + Always Review") == 2
    assert "Think Longer and premium creation access" not in landing
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
            "Advanced Intelligence: Think Longer + Always Review",
            "10-second Cinematic video access",
            "Premium creation access",
            "Premium video and other high-compute generations use Crump Credits.",
        ):
            assert expected in source
        assert source.count("Advanced Intelligence: Think Longer + Always Review") == 2
        assert "billing51-plan-benefits" in source
        assert "For sustained work that needs the largest current individual limits." in source
        assert "organization workflows" not in source.lower()
        for unsupported in (
            "team administration", "sso", "procurement", "sla",
            "dedicated support", "enterprise security",
        ):
            assert re.search(rf"\b{re.escape(unsupported)}\b", source, re.IGNORECASE) is None

    assert "Think Longer and premium creation access" not in billing
    assert "Think Longer and premium creation access" not in final_billing
    assert "Think Longer and premium creation access" not in subscriptions

    for dynamic_source in (billing, subscriptions):
        assert "textContent = item" in dynamic_source

    assert ".billing51-plan-benefits" in stylesheet
    assert ".billing51-plan-meter-note" in stylesheet


def test_quick_upgrade_prompt_matches_truthful_current_capabilities():
    source = read_public("subscription-ui.js")

    for expected in (
        "500 included messages daily",
        "25 private Projects",
        "5,000 included messages daily",
        "200 private Projects",
        "demanding individual workflows",
        "Premium video and other high-compute generations use Crump Credits.",
    ):
        assert expected in source

    for unsupported in (
        "priority support",
        "dedicated support",
        "SSO",
        "SLA",
        "admin controls",
        "procurement",
    ):
        assert unsupported.lower() not in source.lower()


def test_quick_upgrade_asset_is_versioned_for_web_pwa_and_native():
    versioned = "/subscription-ui.js?v=5.9.76-commerce-recovery-1"
    sources = (
        read_public("runtime-body-v1.js"),
        read_public("sw.js"),
        (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8"),
    )

    for source in sources:
        assert versioned in source


def test_credit_pack_merchandising_contains_no_unsupported_social_proof():
    billing = read_public("crump-billing-5.1.js")
    final_billing = read_public("crump-5.2.js")
    billing_styles = read_public("crump-billing-5.1.css")
    shell_styles = read_public("crump-v1-body.css")

    for source in (billing, final_billing):
        for unsupported in (
            "Popular", "Most popular", "Recommended", "Best value", "Customer favorite",
        ):
            assert unsupported.lower() not in source.lower()
        assert "billing51-badge" not in source
        assert "credits === 150 ? 'is-featured'" not in source
        assert "Number(pack.credits) === 150 ? 'is-featured'" not in source

    for source in (billing_styles, shell_styles):
        assert ".billing51-pack.is-featured" not in source
    assert ".billing51-plan.is-featured" in billing_styles


def test_credit_pack_truth_is_browser_verified_without_checkout_success():
    verifier = (ROOT / "scripts" / "verify-credit-pack-accessibility.cjs").read_text(
        encoding="utf-8"
    )

    assert "featuredPackCards" in verifier
    assert "unsupportedClaims" in verifier
    assert "assert.equal(state.featuredPackCards, 0);" in verifier
    assert "assert.equal(state.unsupportedClaims, 0);" in verifier
    fixture = (ROOT / "tests" / "fixtures" / "plan-center-clarity.html").read_text(
        encoding="utf-8"
    )
    assert "Fixture blocks credit checkout." in fixture


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
    versioned_billing = "/crump-billing-5.1.js?v=5.9.76-credit-pack-truth-1"
    versioned_final = "/crump-5.2.js?v=5.9.76-credit-pack-truth-1"
    versioned_billing_css = "/crump-billing-5.1.css?v=5.9.76-credit-pack-truth-1"
    versioned_credit_contract = "/crump-5.2.2.js?v=5.9.76-new-response-cue-1"
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
        assert versioned_billing_css in source
        assert versioned_credit_contract in source
    assert "ask-crump-new-body-v1-r213" in read_public("sw.js")
    assert "/runtime-body-v1.js?v=5.9.76-live-image-preview-loader-1" in read_public("app.html")


def test_browser_fixture_uses_the_production_plan_center_layers():
    fixture = (
        ROOT / "tests" / "fixtures" / "plan-center-clarity.html"
    ).read_text(encoding="utf-8")

    assert "/public/crump-billing-5.1.css" in fixture
    assert "/public/crump-billing-5.1.js" in fixture
    assert "/public/crump-5.2.js" in fixture
    assert "/public/crump-5.2.2.js" in fixture
    assert "billing-modal-containment-fixture-1" in fixture
    assert "/public/crump-subscriptions-5.3.2.js" in fixture
    assert "window.__planCenterEvents" in fixture
    assert "fixture-user" in fixture
    assert 'id="billingFixtureBackground"' in fixture
    assert 'id="billingFixtureCheckouts"' in fixture
    assert 'id="billingFixturePortals"' in fixture
    assert "status') === 'past_due'" in fixture
    assert "status: 'past_due', provider: 'stripe', manageable: true" in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert "/api/stripe/create-checkout-session" in fixture
    assert "Fixture blocks checkout." in fixture
    assert "checkout.stripe.com" not in fixture
    assert "askcrump.com" not in fixture


def test_credit_packs_expose_one_named_purchase_control_without_nested_button_roles():
    billing = read_public("crump-billing-5.1.js")
    final_billing = read_public("crump-5.2.js")
    final_contract = read_public("crump-5.2.2.js")
    stylesheet = read_public("crump-5.2.css")
    verifier = (ROOT / "scripts" / "verify-credit-pack-accessibility.cjs").read_text(
        encoding="utf-8"
    )
    fixture = (
        ROOT / "tests" / "fixtures" / "plan-center-clarity.html"
    ).read_text(encoding="utf-8")

    assert "article.setAttribute('role', 'button')" not in final_billing
    assert "article.tabIndex" not in final_billing
    assert "card.setAttribute('role', 'button')" not in final_contract
    assert "card.tabIndex = 0" not in final_contract
    assert "card.removeAttribute('role')" in final_contract
    assert "card.removeAttribute('tabindex')" in final_contract
    assert "button.setAttribute('aria-label', accessibleLabel)" in final_contract
    assert "closest('.billing51-buy[data-crump-pack]')" in final_contract
    assert "Add ${Number(pack.credits) || 0} Crump Credits for" in final_billing
    assert "Add ${pack.credits} Crump Credits for ${displayPrice}" in billing
    assert ":focus-within" in stylesheet
    assert ":focus-visible" not in stylesheet
    assert "nestedInteractiveCards" in verifier
    assert "Add 50 Crump Credits for $4.99" in verifier
    assert "Fixture blocks credit checkout." in fixture
