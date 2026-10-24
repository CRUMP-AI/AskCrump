from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from backend.push_service import SAFE_PUSH_BODY, SAFE_PUSH_TITLE, PushService


class RecordingPushDB:
    def __init__(self, row, session):
        self.row = dict(row)
        self.session = dict(session) if session else None
        self.session_filters = []
        self.updates = []

    async def select(self, table, **kwargs):
        assert table == "push_tokens"
        return [dict(self.row)]

    async def select_one(self, table, *, columns="*", filters=None):
        assert table == "sessions"
        self.session_filters.append(dict(filters or {}))
        if not self.session:
            return None
        expected = {
            "id": f"eq.{self.session['id']}",
            "user_id": f"eq.{self.session['user_id']}",
            "device_id": f"eq.{self.session['device_id']}",
            "token_hash": f"eq.{self.session['token_hash']}",
            "revoked_at": "is.null",
        }
        if any((filters or {}).get(key) != value for key, value in expected.items()):
            return None
        if self.session.get("revoked_at") is not None:
            return None
        raw_expiry = str(self.session["expires_at"]).replace("Z", "+00:00")
        expiry = datetime.fromisoformat(raw_expiry)
        threshold = datetime.fromisoformat(
            str((filters or {})["expires_at"])[3:].replace("Z", "+00:00")
        )
        return {"id": self.session["id"]} if expiry > threshold else None

    async def update(self, table, payload, *, filters, **kwargs):
        assert table == "push_tokens"
        self.updates.append((dict(payload), dict(filters)))
        return []


def push_row():
    return {
        "id": "73000000-0000-4000-8000-000000000001",
        "user_id": "70000000-0000-4000-8000-000000000001",
        "installation_id": "installation-push-fixture",
        "token": "provider-token-original-1234",
        "platform": "ios",
        "enabled": True,
        "registration_session_id": "71000000-0000-4000-8000-000000000001",
        "registration_session_token_hash": "a" * 64,
    }


def active_session():
    return {
        "id": "71000000-0000-4000-8000-000000000001",
        "user_id": "70000000-0000-4000-8000-000000000001",
        "device_id": "installation-push-fixture",
        "token_hash": "a" * 64,
        "revoked_at": None,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


def push_settings():
    return SimpleNamespace(
        google_service_account_json=None,
        fcm_project_id=None,
        apns_key_id=None,
        apns_team_id=None,
        apns_private_key=None,
        apns_bundle_id=None,
        apns_environment="sandbox",
    )


@pytest.mark.asyncio
async def test_send_user_requires_current_session_generation_before_provider_call(monkeypatch) -> None:
    db = RecordingPushDB(push_row(), active_session())
    provider_calls = []

    async def fake_send(_service, token, title, body, data):
        provider_calls.append((token, title, body, data))
        return True, False

    monkeypatch.setattr(PushService, "_send_ios", fake_send)

    result = await PushService(push_settings()).send_user(
        db,
        push_row()["user_id"],
        title="Private assistant",
        body="Private generated check-in",
    )

    assert result.delivered == 1
    assert result.attempted == 1
    assert provider_calls == [
        (
            push_row()["token"],
            SAFE_PUSH_TITLE,
            SAFE_PUSH_BODY,
            {"ownerId": push_row()["user_id"]},
        )
    ]
    assert "Private" not in provider_calls[0][1]
    assert "Private" not in provider_calls[0][2]
    assert db.session_filters[0]["id"] == f"eq.{push_row()['registration_session_id']}"
    assert db.session_filters[0]["token_hash"] == (
        f"eq.{push_row()['registration_session_token_hash']}"
    )
    payload, filters = db.updates[-1]
    assert "last_used_at" in payload
    assert filters == {
        "id": f"eq.{push_row()['id']}",
        "user_id": f"eq.{push_row()['user_id']}",
        "installation_id": f"eq.{push_row()['installation_id']}",
        "token": f"eq.{push_row()['token']}",
        "registration_session_id": f"eq.{push_row()['registration_session_id']}",
        "registration_session_token_hash": (
            f"eq.{push_row()['registration_session_token_hash']}"
        ),
        "enabled": "eq.true",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_patch", "row_patch"),
    [
        ({"revoked_at": "2026-10-24T00:00:00+00:00"}, {}),
        ({"expires_at": "2020-01-01T00:00:00+00:00"}, {}),
        ({"user_id": "70000000-0000-4000-8000-000000000002"}, {}),
        ({"device_id": "installation-other"}, {}),
        ({"token_hash": "b" * 64}, {}),
        ({}, {"registration_session_id": None}),
        ({}, {"registration_session_token_hash": None}),
    ],
)
async def test_send_user_disables_invalid_generation_without_private_delivery(
    monkeypatch, session_patch, row_patch
) -> None:
    row = push_row()
    row.update(row_patch)
    session = active_session()
    session.update(session_patch)
    db = RecordingPushDB(row, session)

    async def forbidden_send(*_args, **_kwargs):
        raise AssertionError("invalid registration generation reached the push provider")

    monkeypatch.setattr(PushService, "_send_ios", forbidden_send)
    result = await PushService(push_settings()).send_user(
        db,
        push_row()["user_id"],
        title="Private assistant",
        body="Private generated check-in",
    )

    assert result.attempted == 0
    assert result.delivered == 0
    assert result.disabled == 1
    payload, filters = db.updates[-1]
    assert payload["enabled"] is False
    assert filters["token"] == f"eq.{row['token']}"
    assert filters["installation_id"] == f"eq.{row['installation_id']}"
    assert filters["registration_session_id"] == (
        "is.null"
        if row.get("registration_session_id") is None
        else f"eq.{row['registration_session_id']}"
    )


@pytest.mark.asyncio
async def test_provider_stale_result_uses_full_generation_and_token_cas(monkeypatch) -> None:
    row = push_row()
    db = RecordingPushDB(row, active_session())

    async def stale_send(*_args, **_kwargs):
        return False, True

    monkeypatch.setattr(PushService, "_send_ios", stale_send)
    result = await PushService(push_settings()).send_user(
        db, row["user_id"], title="Title", body="Body"
    )

    assert result.disabled == 1
    payload, filters = db.updates[-1]
    assert payload["enabled"] is False
    assert filters["token"] == f"eq.{row['token']}"
    assert filters["installation_id"] == f"eq.{row['installation_id']}"
    assert filters["registration_session_id"] == f"eq.{row['registration_session_id']}"
    assert filters["registration_session_token_hash"] == (
        f"eq.{row['registration_session_token_hash']}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["ios", "android"])
async def test_owner_rebind_during_provider_send_never_exposes_private_check_in(
    monkeypatch,
    platform,
) -> None:
    row = push_row()
    row["platform"] = platform
    db = RecordingPushDB(row, active_session())
    provider_calls = []

    async def rebind_during_send(_service, token, title, body, data):
        # This runs after send_user validated A's stamped session generation.
        # Simulate the same installation revoking A and becoming B before the
        # provider accepts the already-started request.
        db.session["revoked_at"] = datetime.now(timezone.utc).isoformat()
        db.session["user_id"] = "70000000-0000-4000-8000-000000000002"
        provider_calls.append((token, title, body, data))
        return True, False

    provider_method = "_send_ios" if platform == "ios" else "_send_android"
    monkeypatch.setattr(PushService, provider_method, rebind_during_send)
    result = await PushService(push_settings()).send_user(
        db,
        row["user_id"],
        title="Private assistant name",
        body="Private conversation-derived check-in",
        data={
            "type": "check_in",
            "checkInId": "opaque-check-in",
            "ownerId": "70000000-0000-4000-8000-000000000002",
        },
    )

    assert result.delivered == 1
    assert provider_calls == [
        (
            row["token"],
            SAFE_PUSH_TITLE,
            SAFE_PUSH_BODY,
            {
                "type": "check_in",
                "checkInId": "opaque-check-in",
                "ownerId": row["user_id"],
            },
        )
    ]
    assert "Private" not in provider_calls[0][1]
    assert "Private" not in provider_calls[0][2]


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
