from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_final_plan_center_routes_installed_app_commerce_only_through_revenuecat():
    center = read("public/crump-5.2.js")
    capture_owner = read("public/crump-5.2.2.js")
    subscriptions = read("public/crump-subscriptions-5.3.2.js")

    for source in (center, capture_owner):
        assert "window.BillingManager.purchaseCredits" in source
        assert "nativeBilling()" in source
        assert "native_credit_purchase" in source
    assert "window.BillingManager?.getCreditProducts?.()" in center
    assert "id=\"billing52Restore\"" in center
    assert "window.BillingManager.restore()" in center
    assert "window.BillingManager?.getProducts?.()" in subscriptions
    assert "Store price unavailable" in subscriptions
    assert "crump:billing-refresh-requested" in subscriptions

    bridge = read("public/mobile-bridge.js")
    for path in (
        "/api/billing/credits/checkout",
        "/api/stripe/create-checkout-session",
        "/api/stripe/customer-portal",
        "/api/stripe/finalize-checkout",
    ):
        assert path in bridge
    assert "crump:native-web-billing-blocked" in bridge
    assert "NATIVE_BILLING_REQUIRED" in bridge


def test_native_plan_center_browser_contract_proves_no_stripe_route_or_web_price():
    fixture = read("tests/fixtures/native-plan-center-billing.html")
    verifier = read("scripts/verify-native-plan-center-billing.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")

    assert "CrumpAPI = {isNative: true" in fixture
    assert "askcrump_credits_50" in fixture
    assert "askcrump_professional_monthly" in fixture
    assert "purchasePackage({aPackage})" in fixture
    assert "restorePurchases()" in fixture
    assert "/public/mobile-bridge.js?v=5.9.76-native-store-billing-1" in fixture
    assert "checkoutRequests" in verifier
    assert "assert.equal(evidence.checkoutRequests, 0)" in verifier
    assert "assert.equal(evidence.blockedWebBillingAttempts, 0)" in verifier
    assert "assert.equal(visible.creditPrice, '$4.49')" in verifier
    assert "assert.equal(visible.professionalPrice, '$18.99/month')" in verifier
    assert "verify-native-plan-center-billing.cjs" in matrix
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture.lower()


def test_native_plan_center_does_not_flash_web_prices_before_store_hydration():
    source = read("public/crump-5.2.js")
    assert "${installed ? 'Loading store price…' : '$20/month'}" in source
    assert "${installed ? 'Loading store price…' : '$50/month'}" in source
