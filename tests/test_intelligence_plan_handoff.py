from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_intelligence_plan_intent_reuses_the_open_billing_center():
    intelligence = read("public/crump-4.4.js")
    subscriptions = read("public/crump-subscriptions-5.3.2.js")
    listener = subscriptions[subscriptions.index("window.addEventListener('crump:plan-intent'") :]

    assert "window.showBillingCenter?.({ plan: 'professional' })" in intelligence
    assert "window.dispatchEvent(new CustomEvent('crump:plan-intent'" in intelligence
    assert "document.querySelector('.crump52-billing-modal')" in listener
    assert listener.index("document.querySelector('.crump52-billing-modal')") < listener.index(
        "window.showBillingCenter?.({plan})"
    )
    assert "openCheckout(plan" not in listener


def test_early_intelligence_upgrade_waits_for_the_workspace_runtime():
    intelligence = read("public/crump-4.4.js")

    assert "const PLAN_OPEN_TIMEOUT_MS = 15_000;" in intelligence
    assert "let planOpenPending = false;" in intelligence
    assert "Plans are loading. Crump will open them when ready." in intelligence
    assert "window.addEventListener('crump:body-runtime-ready', open, { once: true })" in intelligence
    assert "window.removeEventListener('crump:body-runtime-ready', open)" in intelligence
    assert "Plan & credits did not finish loading. Please try again." in intelligence


def test_changed_handoff_assets_are_versioned_and_fixture_is_content_free():
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    native = read("scripts/build-native.mjs")
    fixture = read("tests/fixtures/intelligence-plan-handoff.html")
    version = "5.9.76-intelligence-architecture-1"
    subscription_version = "5.9.76-intelligence-plan-handoff-1"

    assert f"/crump-4.4.js?v={version}" in runtime
    assert f"/crump-4.4.js?v={version}" in worker
    assert f"/crump-4.4.js?v={version}" in native
    assert f"/crump-subscriptions-5.3.2.js?v={subscription_version}" in runtime
    assert f"/crump-subscriptions-5.3.2.js?v={subscription_version}" in worker
    assert f"/crump-subscriptions-5.3.2.js?v={subscription_version}" in native
    assert "window.__billingOpenCount" in fixture
    assert 'aria-label="Billing opens"' in fixture
    assert 'aria-label="Billing status requests"' in fixture
    assert 'aria-label="Plan intent consumed"' in fixture
    assert "crump:body-runtime-ready" in fixture
    assert "/public/crump-4.4.js" in fixture
    assert "/public/crump-subscriptions-5.3.2.js" in fixture
    assert "fixture-user" in fixture
    assert "askcrump.com" not in fixture
