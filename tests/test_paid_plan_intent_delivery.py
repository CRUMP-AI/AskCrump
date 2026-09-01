from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_paid_plan_intent_waits_for_matching_consumer_acknowledgement():
    controller = read("public/auth-controller.js")
    delivery = controller[
        controller.index("function dispatchPendingPlanIntent()") :
        controller.index("function applyServerSettings")
    ]

    assert "let pagePlanIntent = null;" in controller
    assert "const PLAN_INTENT_DELIVERY_INTERVAL_MS = 500;" in controller
    assert "const PLAN_INTENT_DELIVERY_MAX_ATTEMPTS = 32;" in controller
    assert "pagePlanIntent = {" in controller
    assert "const pageIntent = normalize(pagePlanIntent);" in controller
    assert "window.dispatchEvent(new CustomEvent('crump:plan-intent'" in delivery
    assert "window.addEventListener('crump:plan-intent-consumed'" in delivery
    assert "event.detail?.plan !== intent.plan" in delivery
    assert "consumedAt !== intent.capturedAt" in delivery
    assert delivery.index("planIntentDispatched = true;") < delivery.index(
        "localStorage.removeItem(PLAN_INTENT_KEY)"
    )
    assert delivery.index("window.addEventListener('crump:plan-intent-consumed'") < delivery.index(
        "window.dispatchEvent(new CustomEvent('crump:plan-intent'"
    )


def test_plan_review_consumer_is_idempotent_and_never_starts_checkout():
    subscriptions = read("public/crump-subscriptions-5.3.2.js")
    listener = subscriptions[subscriptions.index("window.addEventListener('crump:plan-intent'") :]

    assert "const deliveryKey = `${plan}:${capturedAt}`;" in listener
    assert "modal.dataset.crumpPlanIntentReached !== deliveryKey" in listener
    assert "if (!applyPlanIntent(modal, plan)) return false;" in listener
    assert "detail: {plan, capturedAt}" in listener
    assert "openCheckout(" not in listener


def test_paid_plan_delivery_fixture_is_local_content_free_and_checks_checkout_boundary():
    fixture = read("tests/fixtures/cold-auth-entry-delay.html")
    verifier = read("scripts/verify-paid-plan-intent-delivery.cjs")

    assert "/public/crump-subscriptions-5.3.2.js?v=fixture-plan-delivery" in fixture
    assert "fixturePlanConsumerDelay" in fixture
    assert "planConsumerLoaded" in fixture
    assert "checkoutRequests" in fixture
    assert "Fixture blocks checkout." in fixture
    assert "askcrump.com" not in fixture
    assert "consumerDelays = [180, 260, 340, 420, 500, 580, 660, 740, 820, 900]" in verifier
    assert "const plans = ['professional', 'enterprise'];" in verifier
    assert "{name: 'phone', width: 390, height: 844}" in verifier
    assert "{name: 'desktop', width: 1280, height: 720}" in verifier
    assert "assert.equal(state.checkoutRequests, 0);" in verifier
    assert "assert.equal(state.pendingPlan, null);" in verifier
    assert "assert.equal(state.planConsumed, 1);" in verifier
