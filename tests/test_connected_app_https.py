from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import pickle

import httpx
import pytest

from backend.connected_app_contracts import (
    ConnectedAccountRef,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from backend.connected_app_google import (
    GMAIL_HOST,
    GoogleNotDispatched,
    GoogleTransportRequest,
    GoogleTransportSecurityPolicy,
)
from backend.connected_app_https import (
    ConnectedAccessToken,
    GoogleHTTPSCredentialTransport,
    MicrosoftHTTPSCredentialTransport,
)
from backend.connected_app_microsoft import (
    GRAPH_HOST,
    MicrosoftEffectUnknown,
    MicrosoftNotDispatched,
    MicrosoftTransportRequest,
    MicrosoftTransportSecurityPolicy,
)
from backend.connected_app_policy import ConnectorProvider, ConnectorResource


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "00000000-0000-4000-8000-000000000001"
CONNECTION = "00000000-0000-4000-8000-000000000002"
HANDLE = "broker/connected-app/credential-handle-0001"
TOKEN = "access-token-" + "x" * 64


def account(provider: ConnectorProvider) -> ConnectedAccountRef:
    return ConnectedAccountRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=provider,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        external_account_id_hash="a" * 64,
    )


def credential(provider: ConnectorProvider) -> CredentialHandleRef:
    return CredentialHandleRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=provider,
        handle_id=HANDLE,
    )


class TokenSource:
    def __init__(self, provider: ConnectorProvider, *, expires_at: datetime | None = None):
        self.provider = provider
        self.expires_at = expires_at or NOW + timedelta(minutes=30)
        self.calls = 0

    async def issue_access_token(self, *, account, credential):
        self.calls += 1
        return ConnectedAccessToken(
            owner_id=account.owner_id,
            connection_id=account.connection_id,
            provider=self.provider,
            credential_handle_sha256=hashlib.sha256(credential.handle_id.encode()).hexdigest(),
            expires_at=self.expires_at,
            token=TOKEN,
        )


def test_access_token_is_bound_redacted_and_not_serializable():
    subject = ConnectedAccessToken(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        credential_handle_sha256=hashlib.sha256(HANDLE.encode()).hexdigest(),
        expires_at=NOW + timedelta(minutes=20),
        token=TOKEN,
    )
    assert TOKEN not in repr(subject)
    assert TOKEN not in str(subject)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(subject)
    with pytest.raises(ValueError, match="binding"):
        subject.reveal_for_transport(
            account=account(ConnectorProvider.MICROSOFT),
            credential=credential(ConnectorProvider.MICROSOFT),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_google_transport_uses_fixed_https_host_bearer_and_bounded_json():
    observed = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["request"] = request
        return httpx.Response(
            200,
            json={"messages": [], "resultSizeEstimate": 0},
            headers={"X-Request-Id": "provider-request-1"},
        )

    source = TokenSource(ConnectorProvider.GOOGLE)
    subject = GoogleHTTPSCredentialTransport(
        source,
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    )
    response = await subject.request(
        account=account(ConnectorProvider.GOOGLE),
        credential=credential(ConnectorProvider.GOOGLE),
        request=GoogleTransportRequest(
            "GET",
            GMAIL_HOST,
            "/gmail/v1/users/me/messages",
            query=(("maxResults", "25"),),
        ),
    )

    request = observed["request"]
    assert request.url == "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=25"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.headers["accept-encoding"] == "gzip, identity"
    assert response.body == {"messages": [], "resultSizeEstimate": 0}
    assert response.raw_size_bytes and response.raw_size_bytes > 0
    assert response.decompressed_size_bytes == response.raw_size_bytes
    assert source.calls == 1
    assert subject.security_policy == GoogleTransportSecurityPolicy()


@pytest.mark.asyncio
async def test_microsoft_transport_streams_gzip_and_preserves_transport_attestation():
    payload = json.dumps({"value": [{"id": "m1"}]}, separators=(",", ":")).encode()
    compressed = gzip.compress(payload)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=httpx.ByteStream(compressed),
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
        )

    source = TokenSource(ConnectorProvider.MICROSOFT)
    subject = MicrosoftHTTPSCredentialTransport(
        source,
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    )
    response = await subject.request(
        account=account(ConnectorProvider.MICROSOFT),
        credential=credential(ConnectorProvider.MICROSOFT),
        request=MicrosoftTransportRequest(
            "GET",
            GRAPH_HOST,
            "/v1.0/me/messages",
            query=(("$top", "25"),),
        ),
    )

    assert response.body == {"value": [{"id": "m1"}]}
    assert response.raw_size_bytes == len(compressed)
    assert response.decompressed_size_bytes == len(payload)
    assert subject.security_policy == MicrosoftTransportSecurityPolicy()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "transport_type", "provider_request", "error"),
    [
        (
            ConnectorProvider.GOOGLE,
            GoogleHTTPSCredentialTransport,
            GoogleTransportRequest("GET", GMAIL_HOST, "/gmail/v1/users/me/messages"),
            GoogleNotDispatched,
        ),
        (
            ConnectorProvider.MICROSOFT,
            MicrosoftHTTPSCredentialTransport,
            MicrosoftTransportRequest("GET", GRAPH_HOST, "/v1.0/me/messages"),
            MicrosoftNotDispatched,
        ),
    ],
)
async def test_token_expiry_fails_before_dispatch(
    provider, transport_type, provider_request, error
):
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    subject = transport_type(
        TokenSource(provider, expires_at=NOW + timedelta(seconds=5)),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    )
    with pytest.raises(error):
        await subject.request(
            account=account(provider), credential=credential(provider), request=provider_request
        )
    assert called is False


@pytest.mark.asyncio
async def test_connect_failure_is_proven_not_dispatched_but_read_failure_is_ambiguous():
    def connect_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("redacted", request=request)

    google = GoogleHTTPSCredentialTransport(
        TokenSource(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(connect_failure),
        now=lambda: NOW,
    )
    with pytest.raises(GoogleNotDispatched):
        await google.request(
            account=account(ConnectorProvider.GOOGLE),
            credential=credential(ConnectorProvider.GOOGLE),
            request=GoogleTransportRequest("GET", GMAIL_HOST, "/gmail/v1/users/me/messages"),
        )

    def malformed(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"value":1,"value":2}',
            headers={"Content-Type": "application/json"},
        )

    microsoft = MicrosoftHTTPSCredentialTransport(
        TokenSource(ConnectorProvider.MICROSOFT),
        transport=httpx.MockTransport(malformed),
        now=lambda: NOW,
    )
    with pytest.raises(MicrosoftEffectUnknown):
        await microsoft.request(
            account=account(ConnectorProvider.MICROSOFT),
            credential=credential(ConnectorProvider.MICROSOFT),
            request=MicrosoftTransportRequest("GET", GRAPH_HOST, "/v1.0/me/messages"),
        )


@pytest.mark.asyncio
async def test_concatenated_gzip_and_nonfinite_json_are_rejected():
    first = gzip.compress(b'{"value":[]}')
    hidden_second_member = gzip.compress(b'{"hidden":"smuggled"}')

    async def concatenated(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=httpx.ByteStream(first + hidden_second_member),
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
        )

    subject = MicrosoftHTTPSCredentialTransport(
        TokenSource(ConnectorProvider.MICROSOFT),
        transport=httpx.MockTransport(concatenated),
        now=lambda: NOW,
    )
    with pytest.raises(MicrosoftEffectUnknown):
        await subject.request(
            account=account(ConnectorProvider.MICROSOFT),
            credential=credential(ConnectorProvider.MICROSOFT),
            request=MicrosoftTransportRequest("GET", GRAPH_HOST, "/v1.0/me/messages"),
        )

    async def nonfinite(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"value":NaN}',
            headers={"Content-Type": "application/json"},
        )

    subject = MicrosoftHTTPSCredentialTransport(
        TokenSource(ConnectorProvider.MICROSOFT),
        transport=httpx.MockTransport(nonfinite),
        now=lambda: NOW,
    )
    with pytest.raises(MicrosoftEffectUnknown):
        await subject.request(
            account=account(ConnectorProvider.MICROSOFT),
            credential=credential(ConnectorProvider.MICROSOFT),
            request=MicrosoftTransportRequest("GET", GRAPH_HOST, "/v1.0/me/messages"),
        )


@pytest.mark.asyncio
async def test_transport_does_not_follow_provider_redirects():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"Location": "https://evil.example.test/steal"})

    subject = GoogleHTTPSCredentialTransport(
        TokenSource(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    )
    response = await subject.request(
        account=account(ConnectorProvider.GOOGLE),
        credential=credential(ConnectorProvider.GOOGLE),
        request=GoogleTransportRequest("GET", GMAIL_HOST, "/gmail/v1/users/me/messages"),
    )
    assert response.status == 302
    assert calls == 1
