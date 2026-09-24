"""The native client can ask if server-side RevenueCat cleanup is ready."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import app
from backend.routes import billing as billing_routes


client = TestClient(app)


@pytest.mark.parametrize('enabled', (False, True))
def test_native_readiness_is_public_content_free_and_not_cached(monkeypatch, enabled):
    monkeypatch.setattr(
        billing_routes, 'settings', SimpleNamespace(native_billing_enabled=enabled)
    )

    response = client.get(
        '/api/billing/native-readiness',
        headers={'Origin': 'capacitor://localhost'},
    )

    assert response.status_code == 200
    assert response.json() == {'success': True, 'ready': enabled}
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['access-control-allow-origin'] == 'capacitor://localhost'
    assert 'set-cookie' not in response.headers
