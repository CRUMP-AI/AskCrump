from __future__ import annotations

import hashlib
import json
import pickle
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

import backend.connected_app_oauth as oauth
from backend.connected_app_contracts import ConnectorAccountKind
from backend.connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthBrokerFlowCommand,
    OAuthPkceVerifierSecret,
    OAuthStateSecret,
    pkce_s256_challenge,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_provider_oauth import (
    ProviderOAuthAccessToken,
    ProviderOAuthClientSecret,
    ProviderOAuthEffectUnknown,
    ProviderOAuthHTTPSClient,
    ProviderOAuthNotDispatched,
    ProviderOAuthQuarantineRequired,
    ProviderOAuthRefreshToken,
    ProviderOAuthRegistration,
    ProviderOAuthRejected,
    ProviderOAuthTokenBinding,
    build_authorization_url,
)
from backend.connected_app_scopes import delegated_scope_plan


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
OWNER_ID = "00000000-0000-4000-8000-000000000201"
CONNECTION_ID = "00000000-0000-4000-8000-000000000202"
INCARNATION_ID = "00000000-0000-4000-8000-000000000203"
FLOW_ID = "00000000-0000-4000-8000-000000000204"
NONCE_ID = "00000000-0000-4000-8000-000000000205"
STATE = OAuthStateSecret("s" * 48)
VERIFIER = OAuthPkceVerifierSecret("v" * 64)
CODE = OAuthAuthorizationCodeSecret("code-" + "c" * 48)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def registration(provider: ConnectorProvider) -> ProviderOAuthRegistration:
    return ProviderOAuthRegistration(
        provider=provider,
        client_id=(
            "google-client-id.apps.googleusercontent.com"
            if provider is ConnectorProvider.GOOGLE
            else "00000000-0000-4000-8000-000000000299"
        ),
        client_secret=ProviderOAuthClientSecret("client-secret-material-00000001"),
    )


def flow(
    provider: ConnectorProvider,
    *,
    account_kind: ConnectorAccountKind = ConnectorAccountKind.PERSONAL,
) -> OAuthBrokerFlowCommand:
    action = ConnectorActionKind.MAIL_SEARCH
    actions = frozenset({action})
    scopes = frozenset(
        delegated_scope_plan(
            provider,
            actions,
            account_kind=account_kind,
        ).delegated_scopes
    )
    return OAuthBrokerFlowCommand(
        flow_id=FLOW_ID,
        nonce_id=NONCE_ID,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=1,
        current_flow_nonce_sha256=digest(NONCE_ID),
        session_binding_sha256="a" * 64,
        provider=provider,
        resource=ConnectorResource.MAIL,
        account_kind=account_kind,
        actions=actions,
        actions_sha256=oauth._action_hash(actions),
        requested_scopes=scopes,
        requested_scopes_sha256=oauth._scope_hash(scopes),
        state_sha256=digest(STATE.value),
        pkce_challenge=pkce_s256_challenge(VERIFIER.value),
        redirect_uri="https://www.askcrump.com/api/connected-apps/oauth/callback",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


def persisted_binding(
    provider: ConnectorProvider,
    *,
    account_kind: ConnectorAccountKind = ConnectorAccountKind.PERSONAL,
) -> ProviderOAuthTokenBinding:
    initial = registration(provider).token_binding_for_flow(
        flow(provider, account_kind=account_kind)
    )
    return ProviderOAuthTokenBinding(
        provider=initial.provider,
        oauth_client_id_sha256=initial.oauth_client_id_sha256,
        owner_id=initial.owner_id,
        connection_id=initial.connection_id,
        connection_incarnation_id=initial.connection_incarnation_id,
        account_kind=initial.account_kind,
        credential_handle_sha256="d" * 64,
        external_account_id_hash="e" * 64,
    )


def token_body(command: OAuthBrokerFlowCommand, *, refresh: bool = True) -> dict[str, object]:
    body: dict[str, object] = {
        "access_token": "access-token-material-00000001",
        "expires_in": 3600,
        "scope": " ".join(sorted(command.requested_scopes)),
        "token_type": "Bearer",
    }
    if refresh:
        body["refresh_token"] = "refresh-token-material-00000001"
    return body


@pytest.mark.parametrize(
    ("provider", "expected_host", "expected_path"),
    [
        (ConnectorProvider.GOOGLE, "accounts.google.com", "/o/oauth2/v2/auth"),
        (
            ConnectorProvider.MICROSOFT,
            "login.microsoftonline.com",
            "/consumers/oauth2/v2.0/authorize",
        ),
    ],
)
def test_authorization_url_is_fixed_and_exactly_bound(provider, expected_host, expected_path):
    command = flow(provider)
    result = build_authorization_url(
        registration=registration(provider),
        command=command,
        state=STATE,
    )
    parsed = urlsplit(result)
    query = parse_qs(parsed.query, strict_parsing=True)

    assert parsed.scheme == "https"
    assert parsed.hostname == expected_host
    assert parsed.path == expected_path
    assert query["scope"] == [" ".join(sorted(command.requested_scopes))]
    assert query["state"] == [STATE.value]
    assert query["code_challenge"] == [command.pkce_challenge]
    assert query["code_challenge_method"] == ["S256"]
    assert "client-secret-material" not in result
    if provider is ConnectorProvider.GOOGLE:
        assert query["access_type"] == ["offline"]
        assert query["include_granted_scopes"] == ["false"]
    else:
        assert query["response_mode"] == ["query"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_url"),
    [
        (ConnectorProvider.GOOGLE, "https://oauth2.googleapis.com/token"),
        (
            ConnectorProvider.MICROSOFT,
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        ),
    ],
)
async def test_code_exchange_uses_fixed_endpoint_pkce_and_redacted_tokens(
    provider,
    expected_url,
):
    command = flow(provider)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=token_body(command),
            headers={"Content-Type": "application/json"},
        )

    result = await ProviderOAuthHTTPSClient(
        registration(provider),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    ).exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)

    assert str(requests[0].url) == expected_url
    form = parse_qs(requests[0].content.decode(), strict_parsing=True)
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == [CODE.value]
    assert form["code_verifier"] == [VERIFIER.value]
    assert form["redirect_uri"] == [command.redirect_uri]
    assert result.granted_scopes == command.requested_scopes
    assert result.expires_at == NOW + timedelta(hours=1)
    assert "access-token-material" not in repr(result)
    assert "refresh-token-material" not in repr(result)
    with pytest.raises(TypeError):
        pickle.dumps(result.access_token)
    with pytest.raises(TypeError):
        json.dumps(result.refresh_token)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", tuple(ConnectorProvider))
async def test_code_exchange_accepts_rfc_compliant_omitted_scope(provider):
    command = flow(provider)

    async def handler(_: httpx.Request) -> httpx.Response:
        body = token_body(command)
        del body["scope"]
        return httpx.Response(200, json=body)

    result = await ProviderOAuthHTTPSClient(
        registration(provider),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    ).exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert result.granted_scopes == command.requested_scopes
    assert result.refresh_token is not None


@pytest.mark.asyncio
async def test_microsoft_access_scope_may_omit_offline_access_but_not_api_authority():
    command = flow(ConnectorProvider.MICROSOFT)

    async def handler(_: httpx.Request) -> httpx.Response:
        body = token_body(command)
        body["scope"] = " ".join(
            sorted(command.requested_scopes.difference({"offline_access"}))
        )
        return httpx.Response(200, json=body)

    result = await ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.MICROSOFT),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    ).exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert result.granted_scopes == command.requested_scopes
    assert result.refresh_token is not None

    async def missing_api_scope(_: httpx.Request) -> httpx.Response:
        body = token_body(command)
        body["scope"] = "User.Read"
        return httpx.Response(200, json=body)

    with pytest.raises(ProviderOAuthQuarantineRequired) as quarantined:
        await ProviderOAuthHTTPSClient(
            registration(ConnectorProvider.MICROSOFT),
            transport=httpx.MockTransport(missing_api_scope),
            now=lambda: NOW,
        ).exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert quarantined.value.token_set.refresh_token is not None
    assert "refresh-token-material" not in repr(quarantined.value.token_set)


@pytest.mark.asyncio
async def test_scope_drift_or_missing_refresh_token_is_quarantined():
    command = flow(ConnectorProvider.GOOGLE)

    async def drift(_: httpx.Request) -> httpx.Response:
        body = token_body(command)
        body["scope"] = "openid unexpected.scope"
        return httpx.Response(200, json=body)

    subject = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(drift),
        now=lambda: NOW,
    )
    with pytest.raises(ProviderOAuthQuarantineRequired) as drifted:
        await subject.exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert drifted.value.token_set.access_token is not None
    assert drifted.value.token_set.refresh_token is not None

    async def missing(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=token_body(command, refresh=False))

    subject = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(missing),
        now=lambda: NOW,
    )
    with pytest.raises(ProviderOAuthQuarantineRequired) as missing_refresh:
        await subject.exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert missing_refresh.value.token_set.access_token is not None
    assert missing_refresh.value.token_set.refresh_token is None
    assert "access-token-material" not in repr(missing_refresh.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    (("token_type", "MAC"), ("expires_in", "3600"), ("scope", ["mail.read"])),
)
async def test_tokens_are_quarantined_when_200_metadata_is_malformed(field, value):
    command = flow(ConnectorProvider.GOOGLE)

    async def malformed_metadata(_: httpx.Request) -> httpx.Response:
        body = token_body(command)
        body[field] = value
        return httpx.Response(200, json=body)

    subject = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(malformed_metadata),
        now=lambda: NOW,
    )
    with pytest.raises(ProviderOAuthQuarantineRequired) as quarantined:
        await subject.exchange_code(
            command=command,
            authorization_code=CODE,
            verifier=VERIFIER,
        )
    assert quarantined.value.token_set.access_token is not None
    assert quarantined.value.token_set.refresh_token is not None
    assert "access-token-material" not in repr(quarantined.value)
    assert "refresh-token-material" not in str(quarantined.value)


@pytest.mark.asyncio
async def test_connect_failure_is_proven_not_dispatched_and_malformed_reply_is_ambiguous():
    command = flow(ConnectorProvider.GOOGLE)

    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sensitive network detail", request=request)

    subject = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(unavailable),
    )
    with pytest.raises(ProviderOAuthNotDispatched) as not_sent:
        await subject.exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert str(not_sent.value) == "PROVIDER_OAUTH_NOT_DISPATCHED"

    def malformed(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"access_token":"secret",')

    subject = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(malformed),
    )
    with pytest.raises(ProviderOAuthEffectUnknown) as unknown:
        await subject.exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert "secret" not in str(unknown.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_url", "identity"),
    [
        (
            ConnectorProvider.GOOGLE,
            "https://openidconnect.googleapis.com/v1/userinfo",
            {"sub": "stable-google-subject", "email_verified": True},
        ),
        (
            ConnectorProvider.MICROSOFT,
            "https://graph.microsoft.com/v1.0/me?%24select=id",
            {"id": "stable-microsoft-object-id"},
        ),
    ],
)
async def test_identity_lookup_is_fixed_bearer_bound_and_content_free(
    provider, expected_url, identity
):
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=identity)

    binding = registration(provider).token_binding_for_flow(flow(provider))
    result = await ProviderOAuthHTTPSClient(
        registration(provider),
        transport=httpx.MockTransport(handler),
    ).identify(
        ProviderOAuthAccessToken(
            "access-token-material-00000001",
            binding,
        ),
        binding=binding,
    )

    assert str(requests[0].url) == expected_url
    assert requests[0].headers["authorization"] == "Bearer access-token-material-00000001"
    stable = identity["sub"] if provider is ConnectorProvider.GOOGLE else identity["id"]
    assert result.external_account_id_hash == digest(f"{provider.value}\x00{stable}")
    assert result.account_kind is ConnectorAccountKind.PERSONAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("account_kind", "identity", "accepted"),
    [
        (
            ConnectorAccountKind.PERSONAL,
            {"sub": "google-personal-subject", "email_verified": True},
            True,
        ),
        (
            ConnectorAccountKind.WORK_SCHOOL,
            {
                "sub": "google-workspace-subject",
                "email_verified": True,
                "hd": "example.com",
            },
            True,
        ),
        (
            ConnectorAccountKind.PERSONAL,
            {
                "sub": "google-workspace-subject",
                "email_verified": True,
                "hd": "example.com",
            },
            False,
        ),
        (
            ConnectorAccountKind.WORK_SCHOOL,
            {"sub": "google-personal-subject", "email_verified": True},
            False,
        ),
        (
            ConnectorAccountKind.WORK_SCHOOL,
            {
                "sub": "google-workspace-subject",
                "email_verified": True,
                "hd": "not a domain",
            },
            False,
        ),
        (
            ConnectorAccountKind.PERSONAL,
            {
                "sub": "google-personal-subject",
                "email_verified": True,
                "hd": None,
            },
            False,
        ),
    ],
)
async def test_google_identity_authoritatively_matches_selected_account_kind(
    account_kind,
    identity,
    accepted,
):
    command = flow(ConnectorProvider.GOOGLE, account_kind=account_kind)
    binding = registration(ConnectorProvider.GOOGLE).token_binding_for_flow(command)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=identity)

    operation = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(handler),
    ).identify(
        ProviderOAuthAccessToken("access-token-material-00000001", binding),
        binding=binding,
    )
    if accepted:
        result = await operation
        assert result.account_kind is account_kind
    else:
        with pytest.raises(ProviderOAuthRejected):
            await operation


@pytest.mark.asyncio
async def test_refresh_retains_unrotated_refresh_token_and_binds_microsoft_scope():
    command = flow(ConnectorProvider.MICROSOFT)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=token_body(command, refresh=False))

    binding = persisted_binding(ConnectorProvider.MICROSOFT)
    original = ProviderOAuthRefreshToken("refresh-token-material-00000001", binding)
    result = await ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.MICROSOFT),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    ).refresh(
        refresh_token=original,
        expected_scopes=command.requested_scopes,
        binding=binding,
    )

    form = parse_qs(requests[0].content.decode(), strict_parsing=True)
    assert form["grant_type"] == ["refresh_token"]
    assert form["refresh_token"] == ["refresh-token-material-00000001"]
    assert form["scope"] == [" ".join(sorted(command.requested_scopes))]
    assert result.refresh_token is original


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_mode", ("omitted", "access_only"))
async def test_microsoft_refresh_accepts_provider_scope_response_semantics(scope_mode):
    command = flow(ConnectorProvider.MICROSOFT)

    async def handler(_: httpx.Request) -> httpx.Response:
        body = token_body(command, refresh=False)
        if scope_mode == "omitted":
            del body["scope"]
        else:
            body["scope"] = " ".join(
                sorted(command.requested_scopes.difference({"offline_access"}))
            )
        return httpx.Response(200, json=body)

    binding = persisted_binding(ConnectorProvider.MICROSOFT)
    original = ProviderOAuthRefreshToken("refresh-token-material-00000001", binding)
    result = await ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.MICROSOFT),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    ).refresh(
        refresh_token=original,
        expected_scopes=command.requested_scopes,
        binding=binding,
    )
    assert result.granted_scopes == command.requested_scopes
    assert result.refresh_token is original


@pytest.mark.parametrize(
    ("account_kind", "tenant"),
    [
        (ConnectorAccountKind.PERSONAL, "consumers"),
        (ConnectorAccountKind.WORK_SCHOOL, "organizations"),
    ],
)
@pytest.mark.asyncio
async def test_microsoft_tenant_is_provider_enforced_for_authorize_exchange_and_refresh(
    account_kind,
    tenant,
):
    command = flow(ConnectorProvider.MICROSOFT, account_kind=account_kind)
    authorize = build_authorization_url(
        registration=registration(ConnectorProvider.MICROSOFT),
        command=command,
        state=STATE,
    )
    assert urlsplit(authorize).path == f"/{tenant}/oauth2/v2.0/authorize"
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=token_body(command))

    client = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.MICROSOFT),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    )
    await client.exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert requests[-1].url.path == f"/{tenant}/oauth2/v2.0/token"

    binding = persisted_binding(
        ConnectorProvider.MICROSOFT,
        account_kind=account_kind,
    )
    refresh = ProviderOAuthRefreshToken("refresh-token-material-00000001", binding)
    await client.refresh(
        refresh_token=refresh,
        expected_scopes=command.requested_scopes,
        binding=binding,
    )
    assert requests[-1].url.path == f"/{tenant}/oauth2/v2.0/token"


@pytest.mark.asyncio
async def test_token_provenance_mismatch_is_rejected_before_network_dispatch():
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    microsoft_binding = persisted_binding(ConnectorProvider.MICROSOFT)
    token = ProviderOAuthRefreshToken(
        "refresh-token-material-00000001",
        microsoft_binding,
    )
    google = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderOAuthRejected):
        await google.refresh(
            refresh_token=token,
            expected_scopes=frozenset({"openid", "email"}),
            binding=microsoft_binding,
        )
    with pytest.raises(ProviderOAuthRejected):
        await google.identify(
            ProviderOAuthAccessToken(
                "access-token-material-00000001",
                microsoft_binding,
            ),
            binding=microsoft_binding,
        )
    google_binding = persisted_binding(ConnectorProvider.GOOGLE)
    wrong_owner_binding = ProviderOAuthTokenBinding(
        provider=google_binding.provider,
        oauth_client_id_sha256=google_binding.oauth_client_id_sha256,
        owner_id="00000000-0000-4000-8000-000000000298",
        connection_id=google_binding.connection_id,
        connection_incarnation_id=google_binding.connection_incarnation_id,
        account_kind=google_binding.account_kind,
        credential_handle_sha256=google_binding.credential_handle_sha256,
        external_account_id_hash=google_binding.external_account_id_hash,
    )
    with pytest.raises(ProviderOAuthRejected):
        await google.identify(
            ProviderOAuthAccessToken(
                "access-token-material-00000001",
                google_binding,
            ),
            binding=wrong_owner_binding,
        )
    assert called is False


@pytest.mark.asyncio
async def test_malformed_token_fields_use_content_free_error_taxonomy():
    command = flow(ConnectorProvider.GOOGLE)

    async def handler(_: httpx.Request) -> httpx.Response:
        body = token_body(command)
        body["access_token"] = "short"
        return httpx.Response(200, json=body)

    client = ProviderOAuthHTTPSClient(
        registration(ConnectorProvider.GOOGLE),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderOAuthQuarantineRequired) as raised:
        await client.exchange_code(command=command, authorization_code=CODE, verifier=VERIFIER)
    assert str(raised.value) == "PROVIDER_OAUTH_QUARANTINE_REQUIRED"
    assert raised.value.token_set.access_token is None
    assert raised.value.token_set.refresh_token is not None
