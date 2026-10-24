from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import Request

from backend import auth_service
from backend.auth_service import verify_registered_and_create_session


def verification_request(
    *, installation_id: str = 'installation-atomic-verification'
) -> Request:
    return Request({
        'type': 'http',
        'method': 'GET',
        'path': '/api/auth/verify-email',
        'headers': [
            (b'host', b'www.askcrump.com'),
            (b'x-installation-id', installation_id.encode()),
            (b'user-agent', b'pytest'),
        ],
        'client': ('127.0.0.1', 12345),
    })


class VerificationRPCDB:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def rpc(self, name, payload):
        self.calls.append((name, dict(payload)))
        return self.result


@pytest.mark.asyncio
async def test_registered_verification_sends_only_hashed_bearers(monkeypatch) -> None:
    current_user = {
        'id': 'user-1',
        'email': 'person@example.com',
        'is_guest': False,
        'is_verified': True,
    }
    persisted_session = {
        'id': 'session-1',
        'expires_at': '2099-01-01T00:00:00+00:00',
    }
    database = VerificationRPCDB([{
        'verification_applied': True,
        'user_data': current_user,
        'session_data': persisted_session,
        'pruned_sessions': 0,
    }])
    monkeypatch.setattr(auth_service, 'random_token', lambda _length: 'raw-session-token')
    monkeypatch.setattr(auth_service, 'new_uuid', lambda: 'session-id')

    result = await verify_registered_and_create_session(
        database,
        SimpleNamespace(session_days=365),
        {'id': 'user-1', 'is_guest': False, 'is_verified': False},
        verification_request(),
        verification_token_hash='a' * 64,
        device_name='Verified email link',
        platform='web',
    )

    assert result == ('raw-session-token', current_user, persisted_session)
    assert len(database.calls) == 1
    name, payload = database.calls[0]
    assert name == 'verify_registered_and_create_session_v1'
    assert payload['p_verification_token_hash'] == 'a' * 64
    assert payload['p_session_id'] == 'session-id'
    assert payload['p_session_token_hash'] != 'raw-session-token'
    assert 'raw-session-token' not in json.dumps(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'result',
    [[], [{'verification_applied': False}], {}, None],
)
async def test_registered_verification_fails_closed_without_fallback(result) -> None:
    database = VerificationRPCDB(result)

    finalized = await verify_registered_and_create_session(
        database,
        SimpleNamespace(session_days=365),
        {'id': 'user-1', 'is_guest': False, 'is_verified': False},
        verification_request(),
        verification_token_hash='b' * 64,
    )

    assert finalized is None
    assert len(database.calls) == 1


@pytest.mark.asyncio
async def test_registered_verification_rejects_malformed_success_payload() -> None:
    database = VerificationRPCDB([{
        'verification_applied': True,
        'user_data': {'id': 'user-1'},
        'session_data': None,
    }])

    with pytest.raises(
        RuntimeError,
        match='Registered verification did not return its atomic session',
    ):
        await verify_registered_and_create_session(
            database,
            SimpleNamespace(session_days=365),
            {'id': 'user-1', 'is_guest': False, 'is_verified': False},
            verification_request(),
            verification_token_hash='c' * 64,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'user',
    [
        {'id': 'guest-1', 'is_guest': True, 'is_verified': False},
        {'id': 'verified-1', 'is_guest': False, 'is_verified': True},
    ],
)
async def test_registered_verification_never_calls_rpc_for_ineligible_user(user) -> None:
    database = VerificationRPCDB([])

    result = await verify_registered_and_create_session(
        database,
        SimpleNamespace(session_days=365),
        user,
        verification_request(),
        verification_token_hash='d' * 64,
    )

    assert result is None
    assert database.calls == []
