from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
from types import SimpleNamespace
from uuid import UUID

import pytest

import backend.connected_app_oauth_control as subject
from backend.connected_app_contracts import (
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
)
from backend.connected_app_oauth import (
    OAuthBrokerFlowCommand,
    OAuthFlowConsumption,
    OAuthFlowRecord,
    OAuthFlowState,
    OAuthRedirectAllowlist,
    OAuthStartResult,
    OAuthStateSecret,
    pkce_s256_challenge,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from backend.connected_app_provider_oauth import (
    ProviderOAuthClientSecret,
    ProviderOAuthRegistration,
)
from backend.connected_app_scopes import delegated_scope_plan
from backend.connected_app_service import (
    ConnectedConnectionView,
    OAuthCallbackCommand,
    OAuthStartCommand,
)


OWNER = "10000000-0000-4000-8000-000000000001"
CONNECTION_ID = "10000000-0000-4000-8000-000000000002"
FLOW_ID = "10000000-0000-4000-8000-000000000003"
REQUEST = "20000000-0000-4000-8000-000000000002"
SESSION = "70000000-0000-4000-8000-000000000007"
SESSION_HASH = hashlib.sha256(SESSION.encode()).hexdigest()
REDIRECT = "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
NOW = datetime(2026, 11, 8, 1, 0, tzinfo=UTC)
ACTIONS = frozenset({ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND})


def command() -> OAuthStartCommand:
    return OAuthStartCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        actions=ACTIONS,
        redirect_uri=REDIRECT,
        connection_id=None,
        requested_at=NOW,
    )


def registrations() -> dict[ConnectorProvider, ProviderOAuthRegistration]:
    return {
        ConnectorProvider.GOOGLE: ProviderOAuthRegistration(
            provider=ConnectorProvider.GOOGLE,
            client_id="google-client-id.apps.googleusercontent.com",
            client_secret=ProviderOAuthClientSecret("g" * 32),
        ),
        ConnectorProvider.MICROSOFT: ProviderOAuthRegistration(
            provider=ConnectorProvider.MICROSOFT,
            client_id="00000000-0000-4000-8000-000000000777",
            client_secret=ProviderOAuthClientSecret("m" * 32),
        ),
    }


def allowlists() -> dict[ConnectorProvider, OAuthRedirectAllowlist]:
    return {
        ConnectorProvider.GOOGLE: OAuthRedirectAllowlist(frozenset({REDIRECT})),
        ConnectorProvider.MICROSOFT: OAuthRedirectAllowlist(
            frozenset(
                {
                    "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
                }
            )
        ),
    }


def flow_for(reservation: subject.OAuthStartReservation, *, state=OAuthFlowState.PENDING):
    raw_state = OAuthStateSecret("s" * 43)
    scopes = frozenset(
        delegated_scope_plan(
            reservation.command.provider,
            reservation.command.actions,
            account_kind=reservation.command.account_kind,
        ).delegated_scopes
    )
    broker_command = OAuthBrokerFlowCommand(
        flow_id=reservation.flow_id,
        nonce_id=reservation.nonce_id,
        owner_id=reservation.command.owner_id,
        connection_id=reservation.connection_id,
        connection_incarnation_id=reservation.connection_incarnation_id,
        expected_base_revision=reservation.expected_base_revision,
        current_flow_nonce_sha256=reservation.current_flow_nonce_sha256,
        session_binding_sha256=reservation.command.session_binding_sha256,
        provider=reservation.command.provider,
        resource=reservation.command.resource,
        account_kind=reservation.command.account_kind,
        actions=reservation.command.actions,
        actions_sha256=action_set_sha256(reservation.command.actions),
        requested_scopes=scopes,
        requested_scopes_sha256=hashlib.sha256(
            ("[" + ",".join(f'\"{value}\"' for value in sorted(scopes)) + "]").encode()
        ).hexdigest(),
        state_sha256=hashlib.sha256(raw_state.value.encode()).hexdigest(),
        pkce_challenge=pkce_s256_challenge("v" * 43),
        redirect_uri=reservation.command.redirect_uri,
        created_at=reservation.created_at,
        expires_at=reservation.expires_at,
    )
    record = OAuthFlowRecord.from_broker_command(broker_command)
    if state is OAuthFlowState.CONSUMED:
        record = OAuthFlowRecord(
            **{
                name: getattr(record, name)
                for name in record.__dataclass_fields__
                if name not in {"state", "consumed_at"}
            },
            state=OAuthFlowState.CONSUMED,
            consumed_at=NOW + timedelta(seconds=5),
        )
    return record, raw_state


class Store:
    def __init__(self) -> None:
        self.reservation = None
        self.prepared = []
        self.callbacks = []
        self.accepted_callbacks = []
        self.denied_callbacks = []
        self.callback_result = None
        self.callback_flow = None
        self.callback_consumption = None
        self.lose_accept_response = False

    async def prepare_start(self, cmd, **proposed):
        self.prepared.append((cmd, proposed))
        if self.reservation is not None:
            return self.reservation
        self.reservation = subject.OAuthStartReservation(
            command=cmd,
            flow_id=proposed["proposed_flow_id"],
            nonce_id=proposed["proposed_nonce_id"],
            connection_id=proposed["proposed_connection_id"],
            connection_incarnation_id=proposed["proposed_connection_incarnation_id"],
            expected_base_revision=0,
            current_flow_nonce_sha256=hashlib.sha256(
                proposed["proposed_nonce_id"].encode()
            ).hexdigest(),
            created_at=cmd.requested_at,
            expires_at=cmd.requested_at + timedelta(minutes=10),
        )
        return self.reservation

    async def read_start(self, **_kwargs):
        return self.reservation

    async def bind_callback(self, **kwargs):
        self.callbacks.append(kwargs)
        return subject.OAuthCallbackReservation(
            flow=self.callback_flow,
            accepted_at=NOW + timedelta(seconds=5),
        )

    async def accept_callback(self, **kwargs):
        self.accepted_callbacks.append(kwargs)
        command = kwargs["command"]
        if self.callback_consumption is None:
            self.callback_consumption = OAuthFlowConsumption.build_for_command(
                command,
                consumed_at=NOW + timedelta(seconds=5),
            )
            flow = self.callback_flow
            self.callback_flow = OAuthFlowRecord(
                **{
                    name: getattr(flow, name)
                    for name in flow.__dataclass_fields__
                    if name not in {"state", "consumed_at"}
                },
                state=OAuthFlowState.CONSUMED,
                consumed_at=NOW + timedelta(seconds=5),
            )
        if self.lose_accept_response:
            self.lose_accept_response = False
            raise RuntimeError("simulated response loss after atomic acceptance")
        return self.callback_consumption

    async def deny_callback(self, **kwargs):
        self.denied_callbacks.append(kwargs)
        return subject.OAuthCallbackDenialReceipt(
            owner_id=kwargs["owner_id"],
            connection_id=CONNECTION_ID,
            flow_id=FLOW_ID,
            provider=kwargs["provider"],
            observed_at=kwargs["received_at"],
        )

    async def read_callback(self, **_kwargs):
        return self.callback_result


def orchestrator(store: Store) -> subject.ConnectedAppOAuthOrchestrator:
    return subject.ConnectedAppOAuthOrchestrator(
        store=store,
        broker=object(),
        flows=object(),
        completions=object(),
        registrations=registrations(),
        redirect_allowlists=allowlists(),
        now=lambda: NOW + timedelta(seconds=6),
    )


@pytest.mark.asyncio
async def test_denial_is_exact_owner_session_state_bound_and_content_free():
    store = Store()
    controller = orchestrator(store)
    state_sha256 = hashlib.sha256(b"provider-state").hexdigest()

    receipt = await controller.deny_once(
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        state_sha256=state_sha256,
        received_at=NOW,
    )

    assert receipt.owner_id == OWNER
    assert receipt.flow_id == FLOW_ID
    assert receipt.provider is ConnectorProvider.GOOGLE
    assert len(store.denied_callbacks) == 1
    denial = store.denied_callbacks[0]
    assert denial["state_sha256"] == state_sha256
    assert denial["denial_binding_sha256"] == subject.oauth_denial_binding_sha256(
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        state_sha256=state_sha256,
    )
    assert "provider-state" not in repr(receipt)


@pytest.mark.asyncio
async def test_start_uses_stable_recovery_identities_and_builds_exact_provider_url(monkeypatch):
    store = Store()

    async def start(**kwargs):
        reservation = store.reservation
        assert kwargs["flow_id"] == reservation.flow_id
        assert kwargs["connection_id"] == reservation.connection_id
        record, raw_state = flow_for(reservation)
        return OAuthStartResult(flow=record, authorization_state=raw_state)

    monkeypatch.setattr(subject, "start_oauth_flow", start)
    service = orchestrator(store)
    first = await service.start_once(command())
    second = await service.start_once(command())
    assert first == second
    assert len(store.prepared) == 2
    assert store.prepared[0][1] == store.prepared[1][1]
    assert all(
        str(UUID(value)) == value for value in store.prepared[0][1].values()
    )
    query = first.query_parameters()
    assert query["client_id"] == "google-client-id.apps.googleusercontent.com"
    assert query["redirect_uri"] == REDIRECT
    assert query["code_challenge_method"] == "S256"
    assert "secret" not in repr(first).casefold()
    assert "verifier" not in repr(first).casefold()


@pytest.mark.asyncio
async def test_start_same_request_retry_ignores_later_transport_timestamp(monkeypatch):
    store = Store()

    async def start(**_kwargs):
        record, raw_state = flow_for(store.reservation)
        return OAuthStartResult(flow=record, authorization_state=raw_state)

    monkeypatch.setattr(subject, "start_oauth_flow", start)
    service = orchestrator(store)
    first_command = command()
    first = await service.start_once(first_command)
    retry = await service.start_once(
        replace(first_command, requested_at=NOW + timedelta(minutes=1))
    )
    assert retry == first
    assert store.reservation.command.requested_at == NOW
    assert len(store.prepared) == 2


@pytest.mark.asyncio
async def test_read_start_finishes_only_the_exact_durable_reservation(monkeypatch):
    store = Store()
    await store.prepare_start(
        command(),
        proposed_flow_id="30000000-0000-4000-8000-000000000003",
        proposed_nonce_id="40000000-0000-4000-8000-000000000004",
        proposed_connection_id="50000000-0000-4000-8000-000000000005",
        proposed_connection_incarnation_id="60000000-0000-4000-8000-000000000006",
    )

    async def start(**_kwargs):
        record, raw_state = flow_for(store.reservation)
        return OAuthStartResult(flow=record, authorization_state=raw_state)

    monkeypatch.setattr(subject, "start_oauth_flow", start)
    view = await orchestrator(store).read_start(owner_id=OWNER, request_id=REQUEST)
    assert view is not None
    assert view.flow_id == store.reservation.flow_id
    assert view.connection_id == store.reservation.connection_id


def active_view() -> ConnectedConnectionView:
    return ConnectedConnectionView(
        connection_id="50000000-0000-4000-8000-000000000005",
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        granted_actions=tuple(sorted(ACTIONS, key=lambda action: action.value)),
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256="a" * 64,
        expires_at=NOW + timedelta(hours=1),
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_callback_replay_returns_durable_completion_without_reusing_code(monkeypatch):
    store = Store()
    store.callback_result = active_view()

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("provider path must not run for a durable callback replay")

    monkeypatch.setattr(subject, "exchange_oauth_code_once", forbidden)
    callback = OAuthCallbackCommand.build(
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        code="c" * 43,
        received_at=NOW,
    )
    result = await orchestrator(store).complete_once(callback)
    assert result == store.callback_result
    assert store.callbacks == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner_id", "session_id"),
    (
        ("10000000-0000-4000-8000-000000000099", SESSION),
        (OWNER, "70000000-0000-4000-8000-000000000099"),
    ),
)
async def test_callback_rejects_current_browser_owner_or_session_mismatch_before_exchange(
    monkeypatch, owner_id, session_id
):
    store = Store()
    await store.prepare_start(
        command(),
        proposed_flow_id="30000000-0000-4000-8000-000000000003",
        proposed_nonce_id="40000000-0000-4000-8000-000000000004",
        proposed_connection_id="50000000-0000-4000-8000-000000000005",
        proposed_connection_incarnation_id="60000000-0000-4000-8000-000000000006",
    )
    store.callback_flow, _ = flow_for(store.reservation)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("cross-session callback must not reach provider exchange")

    monkeypatch.setattr(subject, "exchange_oauth_code_once", forbidden)
    callback = OAuthCallbackCommand.build(
        owner_id=owner_id,
        session_id=session_id,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        code="c" * 43,
        received_at=NOW + timedelta(seconds=6),
    )
    with pytest.raises(subject.OAuthContractError, match="OAUTH_CALLBACK_BINDING_MISMATCH"):
        await orchestrator(store).complete_once(callback)
    assert store.accepted_callbacks == []


@pytest.mark.asyncio
@pytest.mark.parametrize("flow_state", [OAuthFlowState.PENDING, OAuthFlowState.CONSUMED])
async def test_callback_joins_consume_exchange_completion_and_store_sees_hashes_only(
    monkeypatch, flow_state
):
    store = Store()
    await store.prepare_start(
        command(),
        proposed_flow_id="30000000-0000-4000-8000-000000000003",
        proposed_nonce_id="40000000-0000-4000-8000-000000000004",
        proposed_connection_id="50000000-0000-4000-8000-000000000005",
        proposed_connection_incarnation_id="60000000-0000-4000-8000-000000000006",
    )
    flow, _ = flow_for(store.reservation, state=flow_state)
    store.callback_flow = flow
    calls = []
    consumption = object()
    exchange = object()
    real_prepare_consumption = subject.prepare_oauth_consumption

    def prepare_consumption(*args, **kwargs):
        calls.append(("prepare", args, kwargs))
        return real_prepare_consumption(*args, **kwargs)

    async def recover(**_kwargs):
        calls.append(("recover",))
        return consumption

    def prepare_exchange(*_args):
        calls.append(("exchange-command",))
        return exchange

    class Grant:
        pass

    grant = Grant()

    async def exchange_once(**kwargs):
        calls.append(("provider", kwargs["authorization_code"]))
        return grant

    scopes = frozenset(
        delegated_scope_plan(
            ConnectorProvider.GOOGLE,
            ACTIONS,
            account_kind=ConnectorAccountKind.PERSONAL,
        ).delegated_scopes
    )
    authorization = ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER,
        connection_id=store.reservation.connection_id,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=1,
        granted_actions=ACTIONS,
        granted_scopes=scopes,
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW + timedelta(seconds=7),
        expires_at=NOW + timedelta(hours=1),
    )

    async def finalize(*_args, **_kwargs):
        calls.append(("complete",))
        return SimpleNamespace(authorization=authorization)

    monkeypatch.setattr(subject, "prepare_oauth_consumption", prepare_consumption)
    monkeypatch.setattr(subject, "recover_oauth_flow_consumption", recover)
    monkeypatch.setattr(subject, "prepare_oauth_exchange", prepare_exchange)
    monkeypatch.setattr(subject, "OAuthBrokerGrant", Grant)
    monkeypatch.setattr(subject, "exchange_oauth_code_once", exchange_once)
    monkeypatch.setattr(subject, "finalize_oauth_completion", finalize)
    callback = OAuthCallbackCommand.build(
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        code="c" * 43,
        received_at=NOW + timedelta(seconds=6),
    )
    result = await orchestrator(store).complete_once(callback)
    assert result.connection_id == store.reservation.connection_id
    assert store.callbacks[0]["state_sha256"] == hashlib.sha256(("s" * 43).encode()).hexdigest()
    assert store.callbacks[0]["callback_binding_sha256"] == callback.callback_binding_sha256
    assert "s" * 43 not in repr(store.callbacks)
    assert "c" * 43 not in repr(store.callbacks)
    names = [item[0] for item in calls]
    if flow_state is OAuthFlowState.PENDING:
        assert names[0] == "prepare"
        assert len(store.accepted_callbacks) == 1
        assert store.accepted_callbacks[0]["command"].flow_id == flow.flow_id
        assert store.callback_consumption.consumed_at == NOW + timedelta(seconds=5)
    else:
        assert names[0] == "recover"
        assert store.accepted_callbacks == []
    assert names[-3:] == ["exchange-command", "provider", "complete"]


@pytest.mark.asyncio
async def test_callback_atomic_accept_response_loss_recovers_without_second_accept(
    monkeypatch,
):
    store = Store()
    await store.prepare_start(
        command(),
        proposed_flow_id="30000000-0000-4000-8000-000000000003",
        proposed_nonce_id="40000000-0000-4000-8000-000000000004",
        proposed_connection_id="50000000-0000-4000-8000-000000000005",
        proposed_connection_incarnation_id="60000000-0000-4000-8000-000000000006",
    )
    flow, _ = flow_for(store.reservation)
    store.callback_flow = flow
    store.lose_accept_response = True
    provider_calls = []

    async def recover(**_kwargs):
        return store.callback_consumption

    def prepare_exchange(*_args):
        return object()

    class Grant:
        pass

    async def exchange_once(**_kwargs):
        provider_calls.append("exchange")
        return Grant()

    scopes = frozenset(
        delegated_scope_plan(
            ConnectorProvider.GOOGLE,
            ACTIONS,
            account_kind=ConnectorAccountKind.PERSONAL,
        ).delegated_scopes
    )
    authorization = ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER,
        connection_id=store.reservation.connection_id,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=1,
        granted_actions=ACTIONS,
        granted_scopes=scopes,
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW + timedelta(seconds=7),
        expires_at=NOW + timedelta(hours=1),
    )

    async def finalize(*_args, **_kwargs):
        return SimpleNamespace(authorization=authorization)

    monkeypatch.setattr(subject, "recover_oauth_flow_consumption", recover)
    monkeypatch.setattr(subject, "prepare_oauth_exchange", prepare_exchange)
    monkeypatch.setattr(subject, "OAuthBrokerGrant", Grant)
    monkeypatch.setattr(subject, "exchange_oauth_code_once", exchange_once)
    monkeypatch.setattr(subject, "finalize_oauth_completion", finalize)
    callback = OAuthCallbackCommand.build(
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        code="c" * 43,
        received_at=NOW + timedelta(seconds=6),
    )
    with pytest.raises(RuntimeError, match="simulated response loss"):
        await orchestrator(store).complete_once(callback)
    result = await orchestrator(store).complete_once(
        replace(callback, received_at=NOW + timedelta(minutes=20))
    )
    assert result.connection_id == store.reservation.connection_id
    assert len(store.accepted_callbacks) == 1
    assert provider_calls == ["exchange"]
