from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_credit_badge_is_event_driven_without_an_idle_poll_loop():
    billing = read_public("crump-billing-5.1.js")

    assert "const BALANCE_STALE_MS = 5 * 60 * 1000;" in billing
    assert "balanceRequest: null" in billing
    assert "if (state.balanceRequest) return state.balanceRequest;" in billing
    assert "document.addEventListener('visibilitychange'" in billing
    assert "window.addEventListener('focus', () => refreshBalance())" in billing
    assert "setInterval(() =>" not in billing
    assert "60_000" not in billing


def test_usage_responses_update_the_balance_without_an_extra_status_request():
    transport = read_public("chat-resilience.js")

    assert "function notifyCreditBalance(data)" in transport
    assert "data?.featureUsage?.creditBalance" in transport
    assert "data?.dailyUsage?.creditBalance" in transport
    assert "data?.credits?.balance" in transport
    assert "new CustomEvent('crump:credits-updated'" in transport
    assert transport.count("notifyCreditBalance(data);") >= 2


def test_credit_refresh_release_is_cache_addressable():
    runtime = read_public("runtime-body-v1.js")
    worker = read_public("sw.js")
    asset = "/crump-billing-5.1.js?v=5.9.76-credit-refresh-1"

    assert asset in runtime
    assert asset in worker
    assert "ask-crump-new-body-v1-r132" in worker


def test_credit_refresh_fixture_uses_only_local_mocked_responses():
    fixture = (
        ROOT / "tests" / "fixtures" / "credit-balance-refresh.html"
    ).read_text(encoding="utf-8")

    assert "/public/crump-billing-5.1.js" in fixture
    assert "window.__fixtureStatusCalls" in fixture
    assert "new CustomEvent('crump:credits-updated'" in fixture
    assert "fixture-user" in fixture
    assert "askcrump.com" not in fixture
    assert "supabase" not in fixture.lower()
