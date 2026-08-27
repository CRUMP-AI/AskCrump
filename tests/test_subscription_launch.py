import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_subscription_launch_assets_are_wired():
    runtime = (ROOT / 'public' / 'runtime-body-v1.js').read_text(encoding='utf-8')
    sw = (ROOT / 'public' / 'sw.js').read_text(encoding='utf-8')
    launch = (ROOT / 'public' / 'crump-subscriptions-5.3.2.js').read_text(encoding='utf-8')
    billing = (ROOT / 'backend' / 'routes' / 'billing.py').read_text(encoding='utf-8')

    assert '/crump-subscriptions-5.3.2.js' in runtime
    assert '/crump-subscriptions-5.3.2.js' in sw
    assert 'SUBSCRIPTION_ALREADY_ACTIVE' in billing
    assert 'billing_portal/configurations' in billing
    assert 'LIVE_PROFESSIONAL_PRICE_ID' in billing
    assert 'LIVE_ENTERPRISE_PRICE_ID' in billing
    assert 'async def create_stripe_customer(user: dict[str, Any]) -> str:    customer' not in billing
    assert '/api/stripe/create-checkout-session' in launch
    assert '/api/stripe/customer-portal' in launch


def test_application_release_versions_match():
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    version = (ROOT / 'backend' / 'version.py').read_text(encoding='utf-8')
    assert package['version'] == '5.9.25'
    assert f"__version__ = '{package['version']}'" in version
