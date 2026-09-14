from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from backend.push_service import PushService


@pytest.mark.asyncio
async def test_fcm_access_token_refreshes_with_google_service_account_and_is_cached(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    service_account_info = {
        "type": "service_account",
        "project_id": "ask-crump-test",
        "private_key_id": "test-key",
        "private_key": private_pem,
        "client_email": "push-test@ask-crump-test.iam.gserviceaccount.com",
        "client_id": "1234567890",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/push-test",
    }
    service = PushService(SimpleNamespace(google_service_account_json=json.dumps(service_account_info)))
    requests: list[dict[str, object]] = []

    class FakeResponse:
        status = 200
        data = b'{"access_token":"fcm-access-token","expires_in":3600,"token_type":"Bearer"}'
        headers: dict[str, str] = {}

    class FakeRequest:
        def __call__(self, *, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
            requests.append({
                "url": url,
                "method": method,
                "body": body,
                "headers": headers,
                "timeout": timeout,
                "kwargs": kwargs,
            })
            return FakeResponse()

    monkeypatch.setattr("google.auth.transport.requests.Request", FakeRequest)

    assert await service._fcm_access_token() == "fcm-access-token"
    assert await service._fcm_access_token() == "fcm-access-token"
    assert len(requests) == 1
    assert requests[0]["url"] == service_account_info["token_uri"]
    assert requests[0]["method"] == "POST"
    assert b"grant_type=" in requests[0]["body"]


def test_apns_provider_token_is_a_cached_es256_jwt() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    service = PushService(
        SimpleNamespace(
            apns_key_id="ASKCRUMP1",
            apns_team_id="CLEVERCRUMP",
            apns_private_key=private_pem,
        )
    )

    token = service._apns_provider_token()

    assert isinstance(token, str)
    assert jwt.get_unverified_header(token) == {
        "alg": "ES256",
        "kid": "ASKCRUMP1",
        "typ": "JWT",
    }
    claims = jwt.decode(token, private_key.public_key(), algorithms=["ES256"])
    assert claims["iss"] == "CLEVERCRUMP"
    assert abs(claims["iat"] - int(datetime.now(timezone.utc).timestamp())) < 5
    assert service._apns_provider_token() == token


def test_apns_provider_token_is_disabled_without_complete_credentials() -> None:
    service = PushService(
        SimpleNamespace(
            apns_key_id=None,
            apns_team_id="CLEVERCRUMP",
            apns_private_key="not-used",
        )
    )

    assert service._apns_provider_token() is None
