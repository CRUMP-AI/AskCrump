from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_checkout_session_recovery_is_bounded_and_never_auto_purchases():
    manager = read_public("billing-manager.js")
    auth = read_public("auth-controller.js")
    credits = read_public("crump-5.2.2.js")
    plans = read_public("crump-subscriptions-5.3.2.js")

    assert "const CHECKOUT_RECOVERY_TTL_MS = 15 * 60 * 1000;" in manager
    assert "new Set(['credits_50', 'credits_150', 'credits_400'])" in manager
    assert "new Set(['professional', 'enterprise'])" in manager
    assert "checkout: 'checkout.stripe.com'" in manager
    assert "portal: 'billing.stripe.com'" in manager
    assert "url.hostname !== expectedHost" in manager
    assert "detail: {reason: 'checkout'}" in manager
    assert "crump:authentication-required" in auth
    assert "Nothing has been charged." in auth
    assert "await reauthenticationPreparation;" in auth
    assert "requestCheckoutReauthentication?.('credit', code)" in credits
    assert "requestCheckoutReauthentication?.('plan', tier)" in plans
    assert "crump:authenticated-ready" in credits
    assert "consumeCheckoutRecovery?.(recovery)" in credits
    assert "Nothing has been purchased." in credits
    for source in (plans, read_public("crump-billing-5.1.js")):
        assert "`Review ${plan.name} in ${native() ? 'app store' : 'Stripe'}`" in source
        assert "`Choose ${plan.name}`" not in source
    for source in (
        credits,
        plans,
        read_public("crump-billing-5.1.js"),
        read_public("crump-5.2.js"),
    ):
        assert "requireStripeDestination?.(" in source
    resume = credits[credits.index("function resumeCheckoutAfterAuthentication()") :]
    assert "/api/billing/credits/checkout" not in resume
    assert "/api/stripe/create-checkout-session" not in resume


def test_checkout_recovery_fixture_is_local_and_content_free():
    fixture = (ROOT / "tests" / "fixtures" / "checkout-session-recovery.html").read_text(
        encoding="utf-8"
    )
    verifier = (ROOT / "scripts" / "verify-checkout-session-recovery.cjs").read_text(
        encoding="utf-8"
    )

    assert "/public/auth-controller.js" in fixture
    assert "/public/crump-5.2.2.js" in fixture
    assert "code:'AUTH_REQUIRED'" in fixture
    assert "checkout.stripe.com.evil.test" in fixture
    assert "https://checkout.stripe.com/c/pay/" not in fixture
    assert "askcrump.com" not in fixture
    assert "supabase" not in fixture.lower()
    assert "credit" in verifier
    assert "plan" in verifier
    assert "Review Professional in Stripe" in verifier
    assert "Review Enterprise in Stripe" in verifier


def test_checkout_recovery_assets_are_cache_addressable_on_web_pwa_and_native():
    integrity_version = "5.9.76-stripe-destination-integrity-1"
    label_version = "5.9.76-checkout-destination-label-1"
    runtime_version = "5.9.76-navigation-discovery-1"
    auth_version = "5.9.76-visible-workspace-return-1"
    shell = read_public("app.html")
    runtime = read_public("runtime-body-v1.js")
    worker = read_public("sw.js")
    native = (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8")

    assert f"/runtime-body-v1.js?v={runtime_version}" in shell
    assert f"/auth-controller.js?v={auth_version}" in shell
    for asset in ("billing-manager.js", "crump-5.2.2.js"):
        versioned = f"/{asset}?v={integrity_version}"
        assert versioned in runtime
        assert versioned in worker
        assert versioned in native
    for asset in ("crump-billing-5.1.js", "crump-subscriptions-5.3.2.js"):
        versioned = f"/{asset}?v={label_version}"
        assert versioned in runtime
        assert versioned in worker
        assert versioned in native
    assert f"/auth-controller.js?v={auth_version}" in worker
    assert "ask-crump-new-body-v1-r248" in worker
