from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx
import pytest

from backend.connected_app_cleanup_reconciliation import (
    ConnectedExternalReconciliationCoordinator,
    ConnectedExternalReconciliationError,
    EncryptedProviderGrantSecretResolver,
    SupabaseConnectedOAuthExpiryReconciler,
)
from backend.connected_app_credential_vault import ConnectedCredentialMasterKey
from backend.connected_app_durable_oauth import ConnectedOAuthMasterKey
from backend.connected_app_grant_cleanup import (
    ConnectedGrantCleanupClaim,
    ConnectedGrantCleanupWorker,
    GoogleOAuthGrantRevoker,
    MicrosoftOAuthGrantRevoker,
    SupabaseConnectedGrantCleanupStore,
)
from backend.connected_app_policy import ConnectorProvider


NOW = datetime(2026, 11, 8, 6, 30, tzinfo=UTC)
TOKEN = "refresh-" + "r" * 64
OWNER_ID = "10000000-0000-4000-8000-000000006501"
CONNECTION_ID = "20000000-0000-4000-8000-000000006501"
INCARNATION_ID = "20000000-0000-4000-8000-000000006502"
FLOW_ID = "30000000-0000-4000-8000-000000006501"
EXCHANGE_ID = "30000000-0000-4000-8000-000000006502"
PROVISIONAL_ID = "30000000-0000-4000-8000-000000006503"
CLEANUP_ID = "40000000-0000-4000-8000-000000006501"
CLAIM_ID = "40000000-0000-4000-8000-000000006502"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _digest(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: dict[str, object]) -> str:
    return _digest(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def _seal(
    *,
    key: bytes,
    key_id: str,
    aad: bytes,
    wrap_prefix: bytes,
    plaintext: bytes,
) -> dict[str, str]:
    data_key = bytes(range(32, 64))
    wrap_nonce = bytes(range(12))
    secret_nonce = bytes(range(12, 24))
    wrapped = AESGCM(key).encrypt(
        wrap_nonce,
        data_key,
        wrap_prefix + key_id.encode("ascii") + b"\x00" + aad,
    )
    ciphertext = AESGCM(data_key).encrypt(secret_nonce, plaintext, aad)
    return {
        "wrapped_key_nonce": _b64(wrap_nonce),
        "wrapped_key_ciphertext": _b64(wrapped),
        "secret_nonce": _b64(secret_nonce),
        "secret_ciphertext": _b64(ciphertext),
    }


def _credential_fixture() -> tuple[
    ConnectedCredentialMasterKey, dict[str, object]
]:
    key = ConnectedCredentialMasterKey("credential-key", bytes(range(32)))
    created = NOW.isoformat()
    updated = (NOW + timedelta(seconds=1)).isoformat()
    authorization_expires = (NOW + timedelta(days=30)).isoformat()
    row: dict[str, object] = {
        "credential_handle_sha256": "1" * 64,
        "owner_id": OWNER_ID,
        "connection_id": CONNECTION_ID,
        "provider": "google",
        "connection_incarnation_id": INCARNATION_ID,
        "oauth_client_id_sha256": "2" * 64,
        "account_kind": "personal",
        "authorization_revision": 2,
        "authorization_snapshot_sha256": "3" * 64,
        "granted_actions_sha256": "4" * 64,
        "granted_scopes_sha256": "5" * 64,
        "external_account_id_hash": "6" * 64,
        "authorization_expires_at": authorization_expires,
        "secret_revision": 3,
        "created_at": created,
        "updated_at": updated,
        "key_id": key.key_id,
    }
    authority_binding = _canonical_hash(
        {
            "version": "connected-credential-envelope-v1",
            "owner_id": OWNER_ID,
            "connection_id": CONNECTION_ID,
            "provider": "google",
            "credential_handle_sha256": "1" * 64,
            "connection_incarnation_id": INCARNATION_ID,
            "oauth_client_id_sha256": "2" * 64,
            "account_kind": "personal",
            "authorization_revision": 2,
            "authorization_snapshot_sha256": "3" * 64,
            "granted_actions_sha256": "4" * 64,
            "granted_scopes_sha256": "5" * 64,
            "external_account_id_hash": "6" * 64,
            "authorization_expires_at": authorization_expires,
        }
    )
    metadata_binding = _canonical_hash(
        {
            "version": "connected-credential-envelope-v1",
            "authority_binding_sha256": authority_binding,
            "secret_revision": 3,
            "created_at": created,
            "updated_at": updated,
        }
    )
    row["authority_binding_sha256"] = authority_binding
    row["metadata_binding_sha256"] = metadata_binding
    encrypted = _seal(
        key=key._key,
        key_id=key.key_id,
        aad=metadata_binding.encode("ascii"),
        wrap_prefix=b"connected-credential-key-v1\x00",
        plaintext=json.dumps(
            {"refresh_token": TOKEN}, sort_keys=True, separators=(",", ":")
        ).encode("ascii"),
    )
    row.update(encrypted)
    row["record_binding_sha256"] = _canonical_hash(
        {
            "version": "connected-credential-envelope-v1",
            "metadata_binding_sha256": metadata_binding,
            "key_id": key.key_id,
            "wrapped_key_nonce_sha256": _digest(
                base64.urlsafe_b64decode(encrypted["wrapped_key_nonce"] + "==")
            ),
            "wrapped_key_ciphertext_sha256": _digest(
                base64.urlsafe_b64decode(
                    encrypted["wrapped_key_ciphertext"] + "=="
                )
            ),
            "secret_nonce_sha256": _digest(
                base64.urlsafe_b64decode(encrypted["secret_nonce"] + "==")
            ),
            "secret_ciphertext_sha256": _digest(
                base64.urlsafe_b64decode(encrypted["secret_ciphertext"] + "==")
            ),
        }
    )
    return key, row


def _provisional_fixture(
    *, quarantine_access_only: bool = False
) -> tuple[ConnectedOAuthMasterKey, dict[str, object]]:
    key = ConnectedOAuthMasterKey("oauth-key", bytes(reversed(range(32))))
    issued = NOW.isoformat()
    expires = (NOW + timedelta(hours=1)).isoformat()
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    scope_binding = _digest(
        json.dumps(scopes, separators=(",", ":")).encode("ascii")
    )
    credential_handle = "credential-handle-" + "c" * 48
    row: dict[str, object] = {
        "provisional_id": PROVISIONAL_ID,
        "owner_id": OWNER_ID,
        "connection_id": CONNECTION_ID,
        "connection_incarnation_id": INCARNATION_ID,
        "flow_id": FLOW_ID,
        "exchange_id": EXCHANGE_ID,
        "provider": "google",
        "account_kind": "personal",
        "status": "quarantined" if quarantine_access_only else "provisional",
        "credential_handle_sha256": _digest(credential_handle),
        "oauth_client_id_sha256": "7" * 64,
        "external_account_id_hash": "8" * 64,
        "granted_scopes": scopes,
        "granted_scopes_sha256": scope_binding,
        "exchange_binding_sha256": "9" * 64,
        "issued_at": issued,
        "expires_at": expires,
        "key_id": key.key_id,
    }
    authority_binding = _canonical_hash(
        {
            "version": "connected-oauth-provisional-credential-v1",
            "provisional_id": PROVISIONAL_ID,
            "owner_id": OWNER_ID,
            "connection_id": CONNECTION_ID,
            "connection_incarnation_id": INCARNATION_ID,
            "flow_id": FLOW_ID,
            "exchange_id": EXCHANGE_ID,
            "provider": "google",
            "account_kind": "personal",
            "credential_handle_sha256": _digest(credential_handle),
            "oauth_client_id_sha256": "7" * 64,
            "external_account_id_hash": "8" * 64,
            "granted_scopes_sha256": scope_binding,
            "exchange_binding_sha256": "9" * 64,
            "issued_at": issued,
            "expires_at": expires,
        }
    )
    row["authority_binding_sha256"] = authority_binding
    envelope_kind = "quarantine" if quarantine_access_only else "provisional"
    secret: dict[str, object] = {
        "version": "connected-oauth-provisional-credential-v1",
        "provisional_binding_sha256": authority_binding,
        "credential_handle": credential_handle,
        "refresh_token": None if quarantine_access_only else TOKEN,
        "flow_binding_sha256": "a" * 64,
    }
    if quarantine_access_only:
        secret.update(
            {
                "access_token": TOKEN,
                "revocation_token_kind": "access",
            }
        )
    encrypted = _seal(
        key=key._key,
        key_id=key.key_id,
        aad=f"{envelope_kind}\x00{authority_binding}".encode("ascii"),
        wrap_prefix=b"connected-oauth-key-v1\x00",
        plaintext=json.dumps(
            secret,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii"),
    )
    row.update(encrypted)
    row["record_binding_sha256"] = _canonical_hash(
        {
            "version": "connected-oauth-envelope-v1",
            "envelope_kind": envelope_kind,
            "authority_binding_sha256": authority_binding,
            "key_id": key.key_id,
            "wrapped_key_nonce_sha256": _digest(
                base64.urlsafe_b64decode(encrypted["wrapped_key_nonce"] + "==")
            ),
            "wrapped_key_ciphertext_sha256": _digest(
                base64.urlsafe_b64decode(
                    encrypted["wrapped_key_ciphertext"] + "=="
                )
            ),
            "secret_nonce_sha256": _digest(
                base64.urlsafe_b64decode(encrypted["secret_nonce"] + "==")
            ),
            "secret_ciphertext_sha256": _digest(
                base64.urlsafe_b64decode(encrypted["secret_ciphertext"] + "==")
            ),
        }
    )
    return key, row


def _claim(
    row: dict[str, object],
    *,
    source_kind: str,
    provider: ConnectorProvider = ConnectorProvider.GOOGLE,
    cleanup_id: str = CLEANUP_ID,
    claim_id: str = CLAIM_ID,
) -> ConnectedGrantCleanupClaim:
    return ConnectedGrantCleanupClaim(
        cleanup_id=cleanup_id,
        provider=provider,
        source_kind=source_kind,
        source_binding_sha256=row["record_binding_sha256"],
        encrypted_record=row,
        claim_id=claim_id,
        claim_expires_at=NOW + timedelta(seconds=30),
        attempts=1,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", ["credential", "provisional"])
async def test_resolver_opens_exact_bound_encrypted_cleanup_record(source_kind):
    credential_key, credential_row = _credential_fixture()
    oauth_key, provisional_row = _provisional_fixture()
    resolver = EncryptedProviderGrantSecretResolver(
        credential_keys={credential_key.key_id: credential_key},
        oauth_keys={oauth_key.key_id: oauth_key},
    )
    row = credential_row if source_kind == "credential" else provisional_row

    secret = await resolver.resolve(_claim(row, source_kind=source_kind))

    assert secret.reveal_for_google_revocation() == TOKEN
    assert TOKEN not in repr(secret)
    assert TOKEN not in repr(resolver)


@pytest.mark.asyncio
async def test_resolver_opens_access_only_semantic_quarantine_for_cleanup():
    credential_key, _ = _credential_fixture()
    oauth_key, quarantine_row = _provisional_fixture(quarantine_access_only=True)
    resolver = EncryptedProviderGrantSecretResolver(
        credential_keys={credential_key.key_id: credential_key},
        oauth_keys={oauth_key.key_id: oauth_key},
    )

    secret = await resolver.resolve(
        _claim(quarantine_row, source_kind="provisional")
    )

    assert secret.reveal_for_google_revocation() == TOKEN
    assert TOKEN not in repr(secret)


@pytest.mark.asyncio
async def test_resolver_fails_closed_on_detached_metadata_ciphertext_or_missing_key():
    credential_key, credential_row = _credential_fixture()
    oauth_key, _ = _provisional_fixture()
    resolver = EncryptedProviderGrantSecretResolver(
        credential_keys={credential_key.key_id: credential_key},
        oauth_keys={oauth_key.key_id: oauth_key},
    )
    detached = dict(credential_row)
    detached["owner_id"] = "10000000-0000-4000-8000-000000006599"
    corrupt = dict(credential_row)
    corrupt["secret_ciphertext"] = (
        ("A" if corrupt["secret_ciphertext"][0] != "A" else "B")
        + corrupt["secret_ciphertext"][1:]
    )

    for row in (detached, corrupt):
        with pytest.raises(ConnectedExternalReconciliationError) as error:
            await resolver.resolve(_claim(row, source_kind="credential"))
        assert error.value.code == "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        assert TOKEN not in str(error.value)

    unavailable = EncryptedProviderGrantSecretResolver(
        credential_keys={
            "other-key": ConnectedCredentialMasterKey("other-key", b"x" * 32)
        },
        oauth_keys={oauth_key.key_id: oauth_key},
    )
    with pytest.raises(ConnectedExternalReconciliationError) as error:
        await unavailable.resolve(
            _claim(credential_row, source_kind="credential")
        )
    assert error.value.code == "CONNECTED_RECONCILIATION_KEY_UNAVAILABLE"


class ExpiryRPC:
    def __init__(self, values: list[object]) -> None:
        self.values = list(values)
        self.calls: list[tuple[str, dict[str, Any], bool]] = []

    async def rpc(self, function_name, payload, *, retry_transient=False):
        self.calls.append((function_name, payload, retry_transient))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.asyncio
async def test_expiry_adapter_is_exact_and_never_blind_retries_ambiguous_response():
    rpc = ExpiryRPC([RuntimeError("lost after commit")])
    subject = SupabaseConnectedOAuthExpiryReconciler(rpc)

    with pytest.raises(ConnectedExternalReconciliationError) as error:
        await subject.run_bounded(maximum=7)

    assert error.value.code == "CONNECTED_RECONCILIATION_STORE_UNAVAILABLE"
    assert rpc.calls == [
        (
            "connected_app_oauth_reconcile_expired_v1",
            {"p_limit": 7},
            False,
        )
    ]


class CleanupRPC:
    def __init__(self, claims: list[ConnectedGrantCleanupClaim]) -> None:
        self.claims = list(claims)
        self.live: ConnectedGrantCleanupClaim | None = None
        self.finished: list[str] = []
        self.lose_first_claim_response = True
        self.lose_first_finish_response = True

    @staticmethod
    def _envelope(claim: ConnectedGrantCleanupClaim) -> dict[str, object]:
        return {
            "status": "claimed",
            "record": {
                "cleanup_id": claim.cleanup_id,
                "provider": claim.provider.value,
                "source_kind": claim.source_kind,
                "source_binding_sha256": claim.source_binding_sha256,
                "encrypted_record": dict(claim.encrypted_record),
                "claim_id": claim.claim_id,
                "claim_expires_at": claim.claim_expires_at.isoformat(),
                "attempts": claim.attempts,
            },
        }

    async def rpc(self, function_name, payload, *, retry_transient=False):
        del retry_transient
        if function_name == "connected_app_provider_cleanup_claim_v1":
            if self.live is None:
                if not self.claims:
                    return {"status": "empty", "record": None}
                source = self.claims.pop(0)
                self.live = ConnectedGrantCleanupClaim(
                    cleanup_id=source.cleanup_id,
                    provider=source.provider,
                    source_kind=source.source_kind,
                    source_binding_sha256=source.source_binding_sha256,
                    encrypted_record=source.encrypted_record,
                    claim_id=payload["p_claim_id"],
                    claim_expires_at=source.claim_expires_at,
                    attempts=source.attempts,
                )
            envelope = self._envelope(self.live)
            if self.lose_first_claim_response:
                self.lose_first_claim_response = False
                raise RuntimeError("lost after durable claim")
            return envelope
        if function_name == "connected_app_provider_cleanup_recover_v1":
            if self.live is not None and payload["p_claim_id"] == self.live.claim_id:
                return self._envelope(self.live)
            return {"status": "absent", "record": None}
        if function_name == "connected_app_provider_cleanup_finish_v1":
            assert self.live is not None
            outcome = payload["p_outcome"]
            if not self.finished or self.finished[-1] != outcome:
                self.finished.append(outcome)
            cleanup_id = self.live.cleanup_id
            if self.lose_first_finish_response:
                self.lose_first_finish_response = False
                raise RuntimeError("lost after durable finish")
            self.live = None
            return {"status": outcome, "cleanup_id": cleanup_id}
        raise AssertionError(function_name)


@pytest.mark.asyncio
async def test_coordinator_recovers_cleanup_responses_and_preserves_provider_semantics():
    credential_key, _ = _credential_fixture()
    oauth_key, provisional_row = _provisional_fixture()
    resolver = EncryptedProviderGrantSecretResolver(
        credential_keys={credential_key.key_id: credential_key},
        oauth_keys={oauth_key.key_id: oauth_key},
    )
    microsoft_row = dict(provisional_row)
    microsoft_row["provider"] = "microsoft"
    google_claim = _claim(provisional_row, source_kind="provisional")
    microsoft_claim = _claim(
        microsoft_row,
        source_kind="provisional",
        provider=ConnectorProvider.MICROSOFT,
        cleanup_id="40000000-0000-4000-8000-000000006503",
        claim_id="40000000-0000-4000-8000-000000006504",
    )
    cleanup_rpc = CleanupRPC([google_claim, microsoft_claim])
    store = SupabaseConnectedGrantCleanupStore(cleanup_rpc)
    google_requests = 0

    async def google_handler(request: httpx.Request) -> httpx.Response:
        nonlocal google_requests
        google_requests += 1
        assert request.content == ("token=" + TOKEN).encode("ascii")
        return httpx.Response(200, json={})

    worker = ConnectedGrantCleanupWorker(
        store=store,
        secret_resolver=resolver,
        google=GoogleOAuthGrantRevoker(transport=httpx.MockTransport(google_handler)),
        microsoft=MicrosoftOAuthGrantRevoker(),
        now=lambda: NOW,
    )
    expiry_rpc = ExpiryRPC([{"expired_flows": 2, "expired_provisionals": 3}])
    coordinator = ConnectedExternalReconciliationCoordinator(
        cleanup=worker,
        oauth_expiry=SupabaseConnectedOAuthExpiryReconciler(expiry_rpc),
        now=lambda: NOW,
    )

    result = await coordinator.run_bounded(cleanup_maximum=8, expiry_maximum=9)

    assert result.cleanup_attempts == 2
    assert result.cleanup_terminal == 2
    assert result.expired_flows == 2
    assert result.expired_provisionals == 3
    assert not result.cleanup_failed
    assert not result.expiry_failed
    assert cleanup_rpc.finished == ["succeeded", "user_action_required"]
    assert google_requests == 1
    assert TOKEN not in repr(result)
    assert TOKEN not in repr(coordinator)


@pytest.mark.asyncio
async def test_coordinator_reports_privacy_safe_lane_failure_and_later_wake_recovers():
    credential_key, _ = _credential_fixture()
    oauth_key, _ = _provisional_fixture()
    resolver = EncryptedProviderGrantSecretResolver(
        credential_keys={credential_key.key_id: credential_key},
        oauth_keys={oauth_key.key_id: oauth_key},
    )
    cleanup_rpc = CleanupRPC([])
    cleanup_rpc.lose_first_claim_response = False
    worker = ConnectedGrantCleanupWorker(
        store=SupabaseConnectedGrantCleanupStore(cleanup_rpc),
        secret_resolver=resolver,
        google=GoogleOAuthGrantRevoker(transport=httpx.MockTransport(lambda _request: None)),
        microsoft=MicrosoftOAuthGrantRevoker(),
        now=lambda: NOW,
    )
    expiry_rpc = ExpiryRPC(
        [
            RuntimeError("lost after commit with provider/customer detail"),
            {"expired_flows": 0, "expired_provisionals": 0},
        ]
    )
    coordinator = ConnectedExternalReconciliationCoordinator(
        cleanup=worker,
        oauth_expiry=SupabaseConnectedOAuthExpiryReconciler(expiry_rpc),
        now=lambda: NOW,
    )

    first = await coordinator.run_bounded()
    second = await coordinator.run_bounded()

    assert first.expiry_failed
    assert not second.expiry_failed
    assert (second.expired_flows, second.expired_provisionals) == (0, 0)
    assert len(expiry_rpc.calls) == 2
    assert "provider/customer" not in repr(first)
