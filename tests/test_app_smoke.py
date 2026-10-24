from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['success'] is True
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert "default-src 'self'" in response.headers['content-security-policy']
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']


def test_local_app_shell_is_served():
    response = client.get('/app')
    assert response.status_code == 200
    assert 'Ask Crump' in response.text


def test_native_preflight_allows_installation_header():
    response = client.options('/api/auth/check-session', headers={
        'Origin': 'capacitor://localhost',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization,x-installation-id,x-crump-client',
    })
    assert response.status_code == 200
    allowed = response.headers.get('access-control-allow-headers', '').lower()
    assert 'x-installation-id' in allowed


def test_native_sync_preflight_allows_expected_owner_header():
    response = client.options('/api/sync/pull', headers={
        'Origin': 'capacitor://localhost',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization,x-ask-crump-sync-owner,x-crump-client',
    })
    assert response.status_code == 200
    allowed = response.headers.get('access-control-allow-headers', '').lower()
    assert 'x-ask-crump-sync-owner' in allowed


def test_account_bound_preflight_allows_generic_expected_owner_header():
    response = client.options('/api/account/profile', headers={
        'Origin': 'capacitor://localhost',
        'Access-Control-Request-Method': 'PATCH',
        'Access-Control-Request-Headers': 'authorization,x-ask-crump-expected-owner,x-crump-client',
    })
    assert response.status_code == 200
    allowed = response.headers.get('access-control-allow-headers', '').lower()
    assert 'x-ask-crump-expected-owner' in allowed
