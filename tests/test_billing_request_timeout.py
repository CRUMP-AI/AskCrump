from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_every_live_billing_layer_bounds_stalled_requests_and_recovers():
    billing = read_public("crump-billing-5.1.js")
    credits = read_public("crump-5.2.2.js")
    subscriptions = read_public("crump-subscriptions-5.3.2.js")

    for source in (billing, credits, subscriptions):
        assert "const BILLING_REQUEST_TIMEOUT_MS = 15_000" in source
        assert "new AbortController()" in source
        assert "Billing took too long. Check your connection and try again." in source
        assert "window.clearTimeout(timeoutId)" in source

    assert "const data = await jsonFetch('/api/billing/credits/checkout'" in credits
    assert "setBusy(button, false)" in subscriptions
    assert "url.searchParams.delete('session_id')" in billing


def test_billing_timeout_assets_are_versioned_across_web_pwa_and_native():
    runtime = read_public("runtime-body-v1.js")
    worker = read_public("sw.js")
    native = (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8")

    assets = (
        "/crump-billing-5.1.js?v=5.9.76-weekly-growth-attribution-1",
        "/crump-5.2.2.js?v=5.9.76-weekly-growth-attribution-1",
        "/crump-subscriptions-5.3.2.js?v=5.9.76-intelligence-plan-handoff-1",
    )
    for asset in assets:
        assert asset in runtime
        assert asset in worker
        assert asset in native
    assert "ask-crump-new-body-v1-r165" in worker


def test_billing_stall_fixture_uses_real_layers_without_credentials_or_production():
    fixture = (ROOT / "tests" / "fixtures" / "billing-request-stall.html").read_text(
        encoding="utf-8"
    )

    assert "/public/crump-billing-5.1.js?v=billing-stall-fixture-1" in fixture
    assert "/public/crump-5.2.2.js?v=billing-stall-fixture-1" in fixture
    assert "/public/crump-subscriptions-5.3.2.js?v=billing-stall-fixture-1" in fixture
    assert "fixtureSurface === 'credit'" in fixture
    assert "fixtureSurface === 'plan'" in fixture
    assert "fixtureSurface === 'return'" in fixture
    assert "Number(delay) === 15_000 ? 250 : delay" in fixture
    assert 'aria-label="Aborted billing requests"' in fixture
    assert 'aria-label="Current query"' in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert "password" not in fixture.lower()
    assert "checkout.stripe.com" not in fixture
    assert "askcrump.com" not in fixture
