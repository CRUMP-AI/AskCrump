from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_chat_credit_and_plan_boundaries_open_review_without_starting_checkout():
    transport = read("public/chat-resilience.js")

    for code in ("SUBSCRIPTION_REQUIRED", "CREDITS_REQUIRED", "FEATURE_LIMIT_REACHED"):
        assert code in transport
    assert "error.data = data" in transport
    assert "offerPlanRecovery(data);" in transport
    assert "window.showUpgradePrompt?.({" in transport
    assert "source: 'feature_recovery'" in transport
    assert "checkout" not in transport.lower()


def test_creation_tools_offer_inline_recovery_only_for_feature_access_errors():
    product = read("public/crump-product-5.3.js")
    styles = read("public/crump-product-5.3.css")

    assert "const FEATURE_ACCESS_CODES = new Set" in product
    assert "'PROJECT_LIMIT_REACHED'" in product
    assert "function setFeatureAccessStatus" in product
    assert "if (!FEATURE_ACCESS_CODES.has(code)) return false;" in product
    assert "Add credits or compare plans" in product
    assert "Compare plans" in product
    assert "Review Plan & credits" in product
    assert product.count("setFeatureAccessStatus('crump53ManuscriptStatus'") >= 5
    assert product.count("setFeatureAccessStatus('crump53VideoStatus'") == 2
    assert "setFeatureAccessStatus('crump53ProjectStatus', error);" in product
    assert "featureAccessCode(error) === 'PROJECT_LIMIT_REACHED'" in product
    assert "run.status === 'awaiting_credits'" in product
    assert "crump53ManuscriptCredits" in product
    assert "window.showUpgradePrompt || window.showBillingCenter" in product
    assert "openCreditCheckout" not in product
    assert ".crump53-feature-recovery" in styles


def test_browser_fixture_uses_real_runtimes_and_credential_free_boundary_responses():
    fixture = read("tests/fixtures/feature-access-recovery.html")

    assert "/public/chat-resilience.js?v=feature-access-recovery-1" in fixture
    assert "/public/crump-product-5.3.js?v=feature-access-recovery-1" in fixture
    assert "code:'CREDITS_REQUIRED'" in fixture
    assert "status:402" in fixture
    assert "window.showUpgradePrompt = options" in fixture
    assert "error.data?.creditsRequired" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture.lower()
