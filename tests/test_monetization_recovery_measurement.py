from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_both_plan_center_owners_preserve_only_fixed_recovery_categories():
    expected = {
        "CREDITS_REQUIRED": "recovery_credits",
        "SUBSCRIPTION_REQUIRED": "recovery_subscription",
        "FEATURE_LIMIT_REACHED": "recovery_feature",
        "PROJECT_LIMIT_REACHED": "recovery_project",
        "USAGE_LIMIT": "recovery_usage",
    }
    for asset in ("public/crump-billing-5.1.js", "public/crump-5.2.js"):
        source = read(asset)
        assert "const recoverySources = Object.freeze({" in source
        assert "const recoverySource = recoverySources[" in source
        assert "if (recoverySource) return recoverySource;" in source
        for access_code, recovery_source in expected.items():
            assert f"{access_code}: '{recovery_source}'" in source
        tracker = source[
            source.index("async function recordPlanCenterView"):
            source.index("async function jsonFetch")
        ]
        assert "prompt" not in tracker.lower()
        assert "filename" not in tracker.lower()
        assert "email" not in tracker.lower()
        assert "creditsRequired" not in tracker
        assert "creditBalance" not in tracker


def test_credit_checkout_milestones_are_server_authoritative_and_fail_open():
    analytics = read("backend/product_analytics.py")
    credits = read("backend/routes/credits.py")

    assert '"CreditCheckoutOpened"' in analytics
    assert '"CreditCheckoutCompleted"' in analytics
    assert '"CreditCheckoutOpened"' not in analytics[analytics.index("CLIENT_EVENT_NAMES"):analytics.index("OUTCOME_FEEDBACK_SOURCES")]
    assert "event_name='CreditCheckoutOpened'" in credits
    assert "event_name='CreditCheckoutCompleted'" in credits
    assert "event_key=session_id" in credits
    assert "event_key=transaction_id" in credits
    assert "source=pack.code" in credits
    assert "payment_intent" not in credits[
        credits.index("await record_product_event("):
        credits.index("return {'pack': pack.code")
    ]


def test_private_monetization_report_keeps_old_metrics_and_adds_credit_and_recovery_stages():
    migration = read("migrations/20260830053822_monetization_recovery_measurement.sql")
    index_migration = read("migrations/20260830055322_consolidate_monetization_index.sql")
    normalized = " ".join(migration.lower().split())

    for event_name in (
        "PlanCenterViewed",
        "SubscriptionCheckoutOpened",
        "SubscriptionCheckoutCompleted",
        "CreditCheckoutOpened",
        "CreditCheckoutCompleted",
    ):
        assert f"'{event_name}'" in migration
    for metric in (
        "plan_center_viewed",
        "checkout_opened_after_plan_view",
        "checkout_completed_after_plan_view",
        "credit_checkout_opened_after_plan_view",
        "credit_checkout_completed_after_plan_view",
        "recovery_credit_viewed",
        "recovery_subscription_viewed",
        "recovery_feature_limit_viewed",
        "recovery_project_limit_viewed",
        "recovery_usage_limit_viewed",
    ):
        assert f"'{metric}'" in migration
    assert "security invoker" in normalized
    assert ") from public, anon, authenticated;" in normalized
    assert ") to service_role;" in normalized
    assert "metadata jsonb" not in normalized
    assert "prompt" not in normalized
    assert "filename" not in normalized
    assert "email" not in normalized
    assert "payment_intent" not in normalized
    assert "drop index if exists public.product_events_monetization_recovery_idx" in index_migration
    assert "drop index if exists public.product_events_plan_conversion_idx" in index_migration
    assert "create index product_events_plan_conversion_idx" in index_migration
    assert "include (source)" in index_migration
    assert "'CreditCheckoutOpened'" in index_migration
    assert "'CreditCheckoutCompleted'" in index_migration


def test_monetization_measurement_assets_are_registered_for_web_pwa_and_native():
    version = "5.9.76-monetization-recovery-1"
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    native = read("scripts/build-native.mjs")

    assert f'/runtime-body-v1.js?v={version}' in read("public/app.html")
    for asset in (
        f"/crump-billing-5.1.js?v={version}",
        f"/crump-5.2.js?v={version}",
    ):
        assert asset in runtime
        assert asset in worker
        assert asset in native
    assert "ask-crump-new-body-v1-r148" in worker
