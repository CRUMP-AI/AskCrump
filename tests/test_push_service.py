from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from backend.push_service import PushService


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
