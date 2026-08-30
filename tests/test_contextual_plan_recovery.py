from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_both_live_plan_centers_render_only_sanitized_fixed_recovery_context():
    for asset in ("public/crump-billing-5.1.js", "public/crump-5.2.js"):
        source = read(asset)
        assert "function billingRecoveryContext(options = {})" in source
        assert "function billingRecoveryMarkup(context)" in source
        for code in (
            "CREDITS_REQUIRED",
            "SUBSCRIPTION_REQUIRED",
            "FEATURE_LIMIT_REACHED",
            "PROJECT_LIMIT_REACHED",
            "USAGE_LIMIT",
        ):
            assert code in source
        assert "creditsRequired.toLocaleString()" in source
        assert "creditBalance.toLocaleString()" in source
        assert "Nothing changes until you choose" in source
        assert "options.message" not in source
        assert "billingRecoveryMarkup(recovery)" in source
        assert "modal.dataset.crumpPlanIntent = recovery.plan" in source


def test_access_handoffs_preserve_structured_context_without_mislabeling_credit_need_as_plan_need():
    chat = read("public/chat-resilience.js")
    product = read("public/crump-product-5.3.js")

    for source in (chat, product):
        assert "accessCode: code" in source
        assert "creditsRequired" in source
        assert "creditBalance" in source
        assert "code === 'SUBSCRIPTION_REQUIRED'" in source
    assert "accessCode: 'USAGE_LIMIT'" in chat
    assert "usageLimit:" in chat


def test_recovery_summary_is_responsive_and_does_not_create_checkout():
    styles = read("public/crump-billing-5.1.css")
    fixture = read("tests/fixtures/contextual-plan-recovery.html")

    assert ".billing51-recovery" in styles
    assert '.billing51-recovery[data-recovery-kind="credits"]' in styles
    assert ".billing51-recovery + .billing51-balance-card" in styles
    assert "/public/crump-billing-5.1.js?v=contextual-recovery-fixture-1" in fixture
    assert "/public/crump-5.2.js?v=contextual-recovery-fixture-1" in fixture
    assert "60, creditBalance:12" in fixture
    assert "plan:'enterprise'" in fixture
    assert "PROJECT_LIMIT_REACHED" in fixture
    assert "usageLimit:25" in fixture
    assert "0 checkout requests" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture.lower()


def test_contextual_recovery_assets_are_registered_for_web_pwa_and_native():
    context_version = "5.9.76-contextual-plan-recovery-1"
    controller_version = "5.9.76-monetization-recovery-1"
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    native = read("scripts/build-native.mjs")

    for asset in (
        f"/crump-billing-5.1.js?v={controller_version}",
        f"/crump-5.2.js?v={controller_version}",
    ):
        assert asset in runtime
        assert asset in worker
        assert asset in native
    css = f"/crump-billing-5.1.css?v={context_version}"
    assert css in runtime
    assert css in worker
    assert css in native
    assert f"/chat-resilience.js?v={context_version}" in runtime
    assert f"/chat-resilience.js?v={context_version}" in worker
    assert f"/crump-product-5.3.js?v={context_version}" in runtime
    assert f"/crump-product-5.3.js?v={context_version}" in worker
    assert "ask-crump-new-body-v1-r146" in worker
