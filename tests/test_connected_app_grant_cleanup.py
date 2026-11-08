from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib

import httpx
import pytest

from backend.connected_app_grant_cleanup import (
    ConnectedGrantCleanupClaim,
    ConnectedGrantCleanupError,
    ConnectedGrantCleanupWorker,
    GoogleOAuthGrantRevoker,
    MicrosoftOAuthGrantRevoker,
    ProviderGrantCleanupOutcome,
    ProviderGrantRevocationSecret,
    SupabaseConnectedGrantCleanupStore,
)
from backend.connected_app_policy import ConnectorProvider


NOW = datetime(2026, 11, 8, 5, 0, tzinfo=UTC)
CLEANUP_ID = "10000000-0000-4000-8000-000000000001"
CLAIM_ID = "10000000-0000-4000-8000-000000000002"
BINDING = "a" * 64
TOKEN = "refresh-" + "r" * 64


def claim(provider: ConnectorProvider = ConnectorProvider.GOOGLE) -> ConnectedGrantCleanupClaim:
    return ConnectedGrantCleanupClaim(
        cleanup_id=CLEANUP_ID,
        provider=provider,
        source_kind="provisional",
        source_binding_sha256=BINDING,
        encrypted_record={"secret_ciphertext": "ciphertext", "record_binding_sha256": BINDING},
        claim_id=CLAIM_ID,
        claim_expires_at=NOW + timedelta(seconds=30),
        attempts=1,
    )


@pytest.mark.asyncio
async def test_google_revocation_uses_one_fixed_bounded_post_and_content_free_receipt():
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    subject = GoogleOAuthGrantRevoker(transport=httpx.MockTransport(handler))
    result = await subject.revoke(ProviderGrantRevocationSecret(TOKEN))

    assert result.outcome is ProviderGrantCleanupOutcome.SUCCEEDED
    assert result.provider_receipt_sha256 == hashlib.sha256(
        b"google\x00oauth-revoke\x00http-200"
    ).hexdigest()
    assert len(observed) == 1
    request = observed[0]
    assert request.method == "POST"
    assert str(request.url) == "https://oauth2.googleapis.com/revoke"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert request.headers["accept-encoding"] == "identity"
    assert request.content == ("token=" + TOKEN).encode("ascii")
    assert TOKEN not in repr(result)


@pytest.mark.asyncio
async def test_google_connect_failure_is_retry_but_ambiguous_timeout_requires_user_action():
    async def connect_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("redacted", request=request)

    async def read_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("redacted", request=request)

    retry = await GoogleOAuthGrantRevoker(
        transport=httpx.MockTransport(connect_failure)
    ).revoke(ProviderGrantRevocationSecret(TOKEN))
    unknown = await GoogleOAuthGrantRevoker(
        transport=httpx.MockTransport(read_timeout)
    ).revoke(ProviderGrantRevocationSecret(TOKEN))

    assert retry.outcome is ProviderGrantCleanupOutcome.RETRY
    assert unknown.outcome is ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED


@pytest.mark.asyncio
async def test_google_redirect_is_never_followed_or_reported_as_revoked():
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(302, headers={"location": "https://example.invalid/steal"})

    result = await GoogleOAuthGrantRevoker(transport=httpx.MockTransport(handler)).revoke(
        ProviderGrantRevocationSecret(TOKEN)
    )
    assert requests == 1
    assert result.outcome is ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED


@pytest.mark.asyncio
async def test_microsoft_never_claims_narrow_revocation_or_dispatches_network():
    subject = MicrosoftOAuthGrantRevoker()
    result = await subject.revoke(None)
    assert result.outcome is ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED
    assert result.provider_receipt_sha256 is None


def test_revocation_secret_and_claim_are_redacted_and_unserializable():
    secret = ProviderGrantRevocationSecret(TOKEN)
    assert TOKEN not in repr(secret)
    assert TOKEN not in str(secret)
    assert "ciphertext" not in repr(claim())
    with pytest.raises(TypeError):
        secret.__getstate__()


class CleanupRPC:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.lose_claim_after_commit = False
        self.claim_id: str | None = None
        self.finished: str | None = None

    def _claimed(self) -> dict[str, object]:
        return {
            "status": "claimed",
            "record": {
                "cleanup_id": CLEANUP_ID,
                "provider": "google",
                "source_kind": "provisional",
                "source_binding_sha256": BINDING,
                "encrypted_record": {
                    "secret_ciphertext": "ciphertext",
                    "record_binding_sha256": BINDING,
                },
                "claim_id": self.claim_id,
                "claim_expires_at": (NOW + timedelta(seconds=30)).isoformat(),
                "attempts": 1,
            },
        }

    async def rpc(self, function_name, payload, *, retry_transient=False):
        del retry_transient
        self.calls.append((function_name, payload))
        if function_name == "connected_app_provider_cleanup_claim_v1":
            self.claim_id = payload["p_claim_id"]
            if self.lose_claim_after_commit:
                self.lose_claim_after_commit = False
                raise RuntimeError("response lost")
            return self._claimed()
        if function_name == "connected_app_provider_cleanup_recover_v1":
            if payload["p_claim_id"] == self.claim_id:
                return self._claimed()
            return {"status": "absent", "record": None}
        if function_name == "connected_app_provider_cleanup_finish_v1":
            self.finished = payload["p_outcome"]
            return {"status": self.finished, "cleanup_id": CLEANUP_ID}
        raise AssertionError(function_name)


@pytest.mark.asyncio
async def test_lost_claim_response_recovers_exact_claim_without_second_winner():
    rpc = CleanupRPC()
    rpc.lose_claim_after_commit = True
    store = SupabaseConnectedGrantCleanupStore(rpc)

    recovered = await store.claim_next(lease_for=timedelta(seconds=30))

    assert recovered is not None
    assert recovered.claim_id == rpc.claim_id
    assert [name for name, _payload in rpc.calls] == [
        "connected_app_provider_cleanup_claim_v1",
        "connected_app_provider_cleanup_recover_v1",
    ]


class Resolver:
    async def resolve(self, value: ConnectedGrantCleanupClaim):
        assert value.provider is ConnectorProvider.GOOGLE
        return ProviderGrantRevocationSecret(TOKEN)


class ResultRevoker:
    def __init__(self, outcome: ProviderGrantCleanupOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    async def revoke(self, secret):
        self.calls += 1
        receipt = "b" * 64 if self.outcome is ProviderGrantCleanupOutcome.SUCCEEDED else None
        from backend.connected_app_grant_cleanup import ProviderGrantCleanupResult

        return ProviderGrantCleanupResult(self.outcome, receipt)


@pytest.mark.asyncio
async def test_worker_settles_google_claim_exactly_once():
    rpc = CleanupRPC()
    store = SupabaseConnectedGrantCleanupStore(rpc)
    google = ResultRevoker(ProviderGrantCleanupOutcome.SUCCEEDED)
    microsoft = ResultRevoker(ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED)
    worker = ConnectedGrantCleanupWorker(
        store=store,
        secret_resolver=Resolver(),
        google=google,
        microsoft=microsoft,
        now=lambda: NOW,
    )

    assert await worker.run_once() == "succeeded"
    assert rpc.finished == "succeeded"
    assert google.calls == 1
    assert microsoft.calls == 0


@pytest.mark.asyncio
async def test_stale_recovered_claim_is_never_revoked():
    class StaleRPC(CleanupRPC):
        async def rpc(self, function_name, payload, *, retry_transient=False):
            if function_name == "connected_app_provider_cleanup_claim_v1":
                return {"status": "stale", "record": None}
            return await super().rpc(
                function_name,
                payload,
                retry_transient=retry_transient,
            )

    store = SupabaseConnectedGrantCleanupStore(StaleRPC())
    with pytest.raises(ConnectedGrantCleanupError) as error:
        await store.claim_next()
    assert error.value.code == "GRANT_CLEANUP_STALE"
