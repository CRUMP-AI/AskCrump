from app import app


EXPECTED_ROUTES = {
    ('GET', '/api/health'),
    ('POST', '/api/auth/register'),
    ('POST', '/api/auth/login'),
    ('GET', '/api/auth/check-session'),
    ('POST', '/api/auth/check-session'),
    ('POST', '/api/auth/refresh'),
    ('POST', '/api/auth/logout'),
    ('POST', '/api/auth/logout-all'),
    ('GET', '/api/auth/devices'),
    ('POST', '/api/auth/revoke-device'),
    ('POST', '/api/auth/forgot-password'),
    ('POST', '/api/auth/reset-password'),
    ('POST', '/api/auth/resend-verification'),
    ('GET', '/api/auth/verify-email'),
    ('PATCH', '/api/account/profile'),
    ('POST', '/api/account/accept-terms'),
    ('DELETE', '/api/account'),
    ('GET', '/api/sync/pull'),
    ('POST', '/api/sync/push'),
    ('GET', '/api/usage/check'),
    ('POST', '/api/chat/ack'),
    ('POST', '/api/chat'),
    ('GET', '/api/presence/preferences'),
    ('PATCH', '/api/presence/preferences'),
    ('POST', '/api/notifications/register'),
    ('DELETE', '/api/notifications/register'),
    ('GET', '/api/cron/check-ins'),
    ('POST', '/api/stripe/create-checkout-session'),
    ('POST', '/api/stripe/finalize-checkout'),
    ('POST', '/api/stripe/customer-portal'),
    ('POST', '/api/stripe/webhook'),
    ('POST', '/api/billing/revenuecat/sync'),
    ('GET', '/api/billing/status'),
    ('POST', '/api/billing/revenuecat/webhook'),
    ('POST', '/api/safety/reports'),
}


def test_public_api_route_contract_is_preserved():
    actual = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, 'methods', set())
        if method not in {'HEAD', 'OPTIONS'}
    }
    assert EXPECTED_ROUTES <= actual
