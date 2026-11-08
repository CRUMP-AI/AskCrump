"""Join the public connected-app service to the durable OAuth broker.

The lower-level OAuth modules deliberately own PKCE entropy, encrypted secret
custody, one-use exchange permits, provider dispatch, and completion.  This
module is the narrow composition boundary that turns those reviewed pieces
into the ``ConnectedAppOAuthControl`` used by the public control plane.

Raw state and authorization codes are accepted only as unserializable secret
objects.  The operator store persists content-free hashes and identities; it
never receives a raw code, state, verifier, access token, or refresh token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import re
from typing import Callable, Mapping, Protocol
from uuid import UUID, UUID as UUIDValue, uuid5

from .connected_app_contracts import ConnectionAuthorizationState
from .connected_app_oauth_code_custody import (
    ConnectedOAuthAuthorizationCodeVault,
)
from .connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthBrokerFlowCommand,
    OAuthBrokerGrant,
    OAuthCallbackAttempt,
    OAuthConsumeCommand,
    OAuthContractError,
    OAuthCredentialBroker,
    OAuthExchangeAmbiguous,
    OAuthExchangeCommand,
    OAuthFlowRecord,
    OAuthFlowConsumption,
    OAuthFlowRepository,
    OAuthFlowState,
    OAuthRedirectAllowlist,
    OAuthCompletionRepository,
    exchange_oauth_code_once,
    finalize_oauth_completion,
    prepare_oauth_consumption,
    prepare_oauth_exchange,
    read_oauth_exchange_terminal,
    recover_oauth_flow_consumption,
    start_oauth_flow,
)
from .connected_app_policy import ConnectorProvider
from .connected_app_provider_oauth import (
    ProviderOAuthRegistration,
    build_authorization_url,
)
from .connected_app_service import (
    ConnectedConnectionView,
    OAuthCallbackCommand,
    OAuthStartCommand,
    OAuthStartView,
    oauth_start_result_binding_sha256,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FLOW_NAMESPACE = UUIDValue("cde3df42-68e1-44b6-9cae-66fb0e0925b7")
_NONCE_NAMESPACE = UUIDValue("00cbbd87-3066-40f5-9788-b04f8c980a09")
_CONNECTION_NAMESPACE = UUIDValue("6b90cc3d-1ef0-4e0d-aa7c-ea0902c07f3b")
_INCARNATION_NAMESPACE = UUIDValue("03c4368f-0502-494b-b79b-5b769e4bb815")


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a UUID string")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} must be a UUID") from None
    if str(parsed) != value:
        raise ValueError(f"{name} must use canonical lowercase UUID form")
    return value


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _derived(namespace: UUIDValue, request_id: str) -> str:
    return str(uuid5(namespace, _uuid(request_id, "request_id")))


def oauth_start_command_binding_sha256(command: OAuthStartCommand) -> str:
    """Content-free exact binding persisted by the OAuth operator store."""

    if type(command) is not OAuthStartCommand:
        raise TypeError("command must be an OAuthStartCommand")
    encoded = json.dumps(
        {
            "version": "connected-oauth-operator-start-v1",
            "request_id": command.request_id,
            "owner_id": command.owner_id,
            "session_binding_sha256": command.session_binding_sha256,
            "provider": command.provider.value,
            "resource": command.resource.value,
            "account_kind": command.account_kind.value,
            "actions": sorted(action.value for action in command.actions),
            "redirect_uri_sha256": _digest(command.redirect_uri),
            "requested_connection_id": command.connection_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class OAuthStartReservation:
    """Database-owned start authority and deterministic recovery identities."""

    command: OAuthStartCommand
    flow_id: str
    nonce_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if type(self.command) is not OAuthStartCommand:
            raise TypeError("command must be an OAuthStartCommand")
        for name in (
            "flow_id",
            "nonce_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if type(self.expected_base_revision) is not int or self.expected_base_revision < 0:
            raise ValueError("expected_base_revision must be nonnegative")
        object.__setattr__(
            self,
            "current_flow_nonce_sha256",
            _sha(self.current_flow_nonce_sha256, "current_flow_nonce_sha256"),
        )
        if self.current_flow_nonce_sha256 != _digest(self.nonce_id):
            raise ValueError("current_flow_nonce_sha256 must bind nonce_id")
        created = _aware(self.created_at, "created_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)
        if created != self.command.requested_at or not created < expires:
            raise ValueError("OAuth reservation lifetime is invalid")

    def __repr__(self) -> str:
        return (
            "OAuthStartReservation("
            f"request_id={self.command.request_id!r}, flow_id={self.flow_id!r}, "
            f"provider={self.command.provider.value!r}, bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCallbackReservation:
    """Content-free callback candidate accepted by the database clock."""

    flow: OAuthFlowRecord
    accepted_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.flow, OAuthFlowRecord):
            raise TypeError("flow must be an OAuthFlowRecord")
        accepted = _aware(self.accepted_at, "accepted_at")
        object.__setattr__(self, "accepted_at", accepted)
        if accepted < self.flow.created_at or accepted >= self.flow.expires_at:
            raise ValueError("callback acceptance is outside the OAuth flow lifetime")

    def __repr__(self) -> str:
        return (
            "OAuthCallbackReservation("
            f"flow_id={self.flow.flow_id!r}, provider={self.flow.provider.value!r}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCallbackDenialReceipt:
    """Content-free proof that one exact owner/session OAuth denial retired."""

    owner_id: str
    connection_id: str
    flow_id: str
    provider: ConnectorProvider
    observed_at: datetime

    def __post_init__(self) -> None:
        for name in ("owner_id", "connection_id", "flow_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))

    def __repr__(self) -> str:
        return (
            "OAuthCallbackDenialReceipt("
            f"flow_id={self.flow_id!r}, provider={self.provider.value!r})"
        )


def oauth_denial_binding_sha256(
    *,
    owner_id: str,
    session_binding_sha256: str,
    provider: ConnectorProvider,
    state_sha256: str,
) -> str:
    """Bind denial retirement without retaining raw state or provider content."""

    owner_id = _uuid(owner_id, "owner_id")
    session_binding_sha256 = _sha(session_binding_sha256, "session_binding_sha256")
    state_sha256 = _sha(state_sha256, "state_sha256")
    if not isinstance(provider, ConnectorProvider):
        raise TypeError("provider must be a ConnectorProvider")
    return hashlib.sha256(
        json.dumps(
            {
                "version": "connected-oauth-denial-v1",
                "owner_id": owner_id,
                "session_binding_sha256": session_binding_sha256,
                "provider": provider.value,
                "state_sha256": state_sha256,
                "error": "access_denied",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class ConnectedOAuthOperatorStore(Protocol):
    """Content-free durable authority surrounding the encrypted OAuth core."""

    async def prepare_start(
        self,
        command: OAuthStartCommand,
        *,
        proposed_flow_id: str,
        proposed_nonce_id: str,
        proposed_connection_id: str,
        proposed_connection_incarnation_id: str,
    ) -> OAuthStartReservation: ...

    async def read_start(
        self, *, owner_id: str, request_id: str
    ) -> OAuthStartReservation | None: ...

    async def bind_callback(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        callback_binding_sha256: str,
        received_at: datetime,
    ) -> OAuthCallbackReservation: ...

    async def accept_callback(
        self,
        *,
        provider: ConnectorProvider,
        state_sha256: str,
        callback_binding_sha256: str,
        received_at: datetime,
        command: OAuthConsumeCommand,
    ) -> OAuthFlowConsumption: ...

    async def deny_callback(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        denial_binding_sha256: str,
        received_at: datetime,
    ) -> OAuthCallbackDenialReceipt: ...

    async def read_callback(
        self, *, provider: ConnectorProvider, callback_binding_sha256: str
    ) -> ConnectedConnectionView | None: ...


class ConnectedAppOAuthOrchestrator:
    """Exact, restart-safe implementation of ``ConnectedAppOAuthControl``."""

    def __init__(
        self,
        *,
        store: ConnectedOAuthOperatorStore,
        broker: OAuthCredentialBroker,
        flows: OAuthFlowRepository,
        completions: OAuthCompletionRepository,
        registrations: Mapping[ConnectorProvider, ProviderOAuthRegistration],
        redirect_allowlists: Mapping[ConnectorProvider, OAuthRedirectAllowlist],
        now: Callable[[], datetime],
        authorization_code_custody: ConnectedOAuthAuthorizationCodeVault | None = None,
    ) -> None:
        for name in (
            "prepare_start",
            "read_start",
            "bind_callback",
            "accept_callback",
            "deny_callback",
            "read_callback",
        ):
            if not callable(getattr(store, name, None)):
                raise TypeError("connected OAuth operator store is invalid")
        if not callable(now):
            raise TypeError("now must be callable")
        if set(registrations) != set(ConnectorProvider) or any(
            registration.provider is not provider
            for provider, registration in registrations.items()
        ):
            raise ValueError("every provider requires its exact OAuth registration")
        if set(redirect_allowlists) != set(ConnectorProvider):
            raise ValueError("every provider requires an OAuth redirect allowlist")
        self._store = store
        self._broker = broker
        self._flows = flows
        self._completions = completions
        self._registrations = dict(registrations)
        self._redirect_allowlists = dict(redirect_allowlists)
        self._now = now
        if authorization_code_custody is not None and not isinstance(
            authorization_code_custody,
            ConnectedOAuthAuthorizationCodeVault,
        ):
            raise TypeError("authorization_code_custody is invalid")
        self._authorization_code_custody = authorization_code_custody

    async def deny_once(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        received_at: datetime,
    ) -> OAuthCallbackDenialReceipt:
        binding = oauth_denial_binding_sha256(
            owner_id=owner_id,
            session_binding_sha256=session_binding_sha256,
            provider=provider,
            state_sha256=state_sha256,
        )
        receipt = await self._store.deny_callback(
            owner_id=owner_id,
            session_binding_sha256=session_binding_sha256,
            provider=provider,
            state_sha256=state_sha256,
            denial_binding_sha256=binding,
            received_at=_aware(received_at, "received_at"),
        )
        if (
            receipt.owner_id != owner_id
            or receipt.provider is not provider
        ):
            raise OAuthContractError("OAUTH_CALLBACK_BINDING_MISMATCH")
        return receipt

    @staticmethod
    def _broker_command(flow: OAuthFlowRecord) -> OAuthBrokerFlowCommand:
        return OAuthBrokerFlowCommand(
            flow_id=flow.flow_id,
            nonce_id=flow.nonce_id,
            owner_id=flow.owner_id,
            connection_id=flow.connection_id,
            connection_incarnation_id=flow.connection_incarnation_id,
            expected_base_revision=flow.expected_base_revision,
            current_flow_nonce_sha256=flow.current_flow_nonce_sha256,
            session_binding_sha256=flow.session_binding_sha256,
            provider=flow.provider,
            resource=flow.resource,
            account_kind=flow.account_kind,
            actions=flow.actions,
            actions_sha256=flow.actions_sha256,
            requested_scopes=flow.requested_scopes,
            requested_scopes_sha256=flow.requested_scopes_sha256,
            state_sha256=flow.state_sha256,
            pkce_challenge=flow.pkce_challenge,
            redirect_uri=flow.redirect_uri,
            created_at=flow.created_at,
            expires_at=flow.expires_at,
        )

    @staticmethod
    def _connection(completion: object) -> ConnectedConnectionView:
        authorization = getattr(completion, "authorization", None)
        if authorization is None or authorization.state is not ConnectionAuthorizationState.ACTIVE:
            raise OAuthContractError("OAUTH_COMPLETION_INVALID")
        return ConnectedConnectionView(
            connection_id=authorization.connection_id,
            provider=authorization.provider,
            resource=authorization.resource,
            account_kind=authorization.account_kind,
            granted_actions=tuple(
                sorted(authorization.granted_actions, key=lambda action: action.value)
            ),
            authorization_state=authorization.state,
            authorization_revision=authorization.revision,
            authorization_snapshot_sha256=authorization.snapshot_sha256,
            expires_at=authorization.expires_at,
            updated_at=authorization.issued_at,
        )

    async def _start(self, reservation: OAuthStartReservation) -> OAuthStartView:
        command = reservation.command
        result = await start_oauth_flow(
            flow_id=reservation.flow_id,
            nonce_id=reservation.nonce_id,
            owner_id=command.owner_id,
            connection_id=reservation.connection_id,
            connection_incarnation_id=reservation.connection_incarnation_id,
            expected_base_revision=reservation.expected_base_revision,
            current_flow_nonce_sha256=reservation.current_flow_nonce_sha256,
            session_binding_sha256=command.session_binding_sha256,
            provider=command.provider,
            resource=command.resource,
            account_kind=command.account_kind,
            actions=command.actions,
            redirect_uri=command.redirect_uri,
            redirect_allowlist=self._redirect_allowlists[command.provider],
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
            broker=self._broker,
            repository=self._flows,
        )
        flow = result.flow
        if (
            flow.flow_id != reservation.flow_id
            or flow.connection_id != reservation.connection_id
            or flow.owner_id != command.owner_id
        ):
            raise OAuthContractError("OAUTH_PENDING_FLOW_BINDING_MISMATCH")
        authorization_url = build_authorization_url(
            registration=self._registrations[command.provider],
            command=self._broker_command(flow),
            state=result.authorization_state,
        )
        return OAuthStartView(
            request_id=command.request_id,
            flow_id=flow.flow_id,
            connection_id=flow.connection_id,
            provider=flow.provider,
            authorization_url=authorization_url,
            state_sha256=flow.state_sha256,
            pkce_challenge=flow.pkce_challenge,
            command_binding_sha256=oauth_start_result_binding_sha256(
                command,
                flow_id=flow.flow_id,
                connection_id=flow.connection_id,
                authorization_url=authorization_url,
                state_sha256=flow.state_sha256,
                pkce_challenge=flow.pkce_challenge,
                expires_at=flow.expires_at,
            ),
            expires_at=flow.expires_at,
        )

    async def start_once(self, command: OAuthStartCommand) -> OAuthStartView:
        if type(command) is not OAuthStartCommand:
            raise TypeError("command must be an OAuthStartCommand")
        proposed_connection_id = command.connection_id or _derived(
            _CONNECTION_NAMESPACE, command.request_id
        )
        reservation = await self._store.prepare_start(
            command,
            proposed_flow_id=_derived(_FLOW_NAMESPACE, command.request_id),
            proposed_nonce_id=_derived(_NONCE_NAMESPACE, command.request_id),
            proposed_connection_id=proposed_connection_id,
            proposed_connection_incarnation_id=_derived(
                _INCARNATION_NAMESPACE, command.request_id
            ),
        )
        if (
            not hmac.compare_digest(
                oauth_start_command_binding_sha256(reservation.command),
                oauth_start_command_binding_sha256(command),
            )
            or reservation.command.request_id != command.request_id
            or reservation.command.owner_id != command.owner_id
            or (
            command.connection_id is not None
            and reservation.connection_id != command.connection_id
            )
        ):
            raise OAuthContractError("OAUTH_START_AUTHORITY_BINDING_MISMATCH")
        return await self._start(reservation)

    async def read_start(
        self, *, owner_id: str, request_id: str
    ) -> OAuthStartView | None:
        reservation = await self._store.read_start(
            owner_id=_uuid(owner_id, "owner_id"),
            request_id=_uuid(request_id, "request_id"),
        )
        if reservation is None:
            return None
        if reservation.command.owner_id != owner_id or reservation.command.request_id != request_id:
            raise OAuthContractError("OAUTH_START_AUTHORITY_BINDING_MISMATCH")
        # This is exact idempotent recovery.  It may finish a response-lost
        # durable start, but can never mint a different flow or authority.
        return await self._start(reservation)

    async def complete_once(
        self, command: OAuthCallbackCommand
    ) -> ConnectedConnectionView:
        if type(command) is not OAuthCallbackCommand:
            raise TypeError("command must be an OAuthCallbackCommand")
        existing = await self.read_completion(
            provider=command.provider,
            callback_binding_sha256=command.callback_binding_sha256,
        )
        if existing is not None:
            return existing
        state_sha256 = _digest(command.secrets.state.value)
        callback = await self._store.bind_callback(
            owner_id=command.owner_id,
            session_binding_sha256=command.session_binding_sha256,
            provider=command.provider,
            state_sha256=state_sha256,
            callback_binding_sha256=command.callback_binding_sha256,
            received_at=command.received_at,
        )
        flow = callback.flow
        if (
            flow.owner_id != command.owner_id
            or not hmac.compare_digest(
                flow.session_binding_sha256,
                command.session_binding_sha256,
            )
            or flow.provider is not command.provider
            or flow.state_sha256 != state_sha256
        ):
            raise OAuthContractError("OAUTH_CALLBACK_BINDING_MISMATCH")
        if flow.state is OAuthFlowState.PENDING:
            consume_command = prepare_oauth_consumption(
                flow,
                OAuthCallbackAttempt(
                    flow_id=flow.flow_id,
                    owner_id=command.owner_id,
                    session_binding_sha256=command.session_binding_sha256,
                    provider=flow.provider,
                    resource=flow.resource,
                    account_kind=flow.account_kind,
                    redirect_uri=flow.redirect_uri,
                    secrets=command.secrets,
                ),
                now=callback.accepted_at,
            )
            if self._authorization_code_custody is None:
                consumption = await self._store.accept_callback(
                    provider=command.provider,
                    state_sha256=state_sha256,
                    callback_binding_sha256=command.callback_binding_sha256,
                    received_at=command.received_at,
                    command=consume_command,
                )
            else:
                predicted = OAuthFlowConsumption.build_for_command(
                    consume_command,
                    consumed_at=callback.accepted_at,
                )
                exchange = prepare_oauth_exchange(flow, predicted)
                consumption, _custody_command = (
                    await self._authorization_code_custody.accept_callback_once(
                        consume=consume_command,
                        exchange=exchange,
                        callback_binding_sha256=(
                            command.callback_binding_sha256
                        ),
                        authorization_code=(
                            command.secrets.authorization_code
                        ),
                        received_at=callback.accepted_at,
                    )
                )
        else:
            consumption = await recover_oauth_flow_consumption(
                repository=self._flows,
                flow=flow,
            )
            if consumption is None:
                raise OAuthContractError("OAUTH_CONSUMPTION_UNCONFIRMED")
        terminal, exchange = await self._exchange_once(
            flow=flow,
            consumption=consumption,
            authorization_code=command.secrets.authorization_code,
            now=max(command.received_at, _aware(self._now(), "now")),
        )
        if not isinstance(terminal, OAuthBrokerGrant):
            raise OAuthContractError("OAUTH_EXCHANGE_RECOVERY_REQUIRED")
        completion = await finalize_oauth_completion(
            flow,
            consumption,
            exchange,
            terminal,
            repository=self._completions,
        )
        return self._connection(completion)

    async def _exchange_once(
        self,
        *,
        flow: OAuthFlowRecord,
        consumption: OAuthFlowConsumption,
        authorization_code: OAuthAuthorizationCodeSecret | None,
        now: datetime,
    ) -> tuple[
        OAuthBrokerGrant | OAuthExchangeAmbiguous,
        OAuthExchangeCommand,
    ]:
        """Exchange from durable custody and erase custody after any terminal."""

        exchange = prepare_oauth_exchange(flow, consumption)
        custody = self._authorization_code_custody
        if custody is None:
            if not isinstance(authorization_code, OAuthAuthorizationCodeSecret):
                raise OAuthContractError(
                    "OAUTH_AUTHORIZATION_CODE_RECOVERY_REQUIRED"
                )
            return (
                await exchange_oauth_code_once(
                    broker=self._broker,
                    repository=self._flows,
                    command=exchange,
                    authorization_code=authorization_code,
                    now=now,
                ),
                exchange,
            )
        try:
            terminal = await read_oauth_exchange_terminal(
                broker=self._broker,
                command=exchange,
            )
        except OAuthContractError as exc:
            if exc.code in {
                "OAUTH_EXCHANGE_DEADLINE_EXPIRED",
                "OAUTH_EXCHANGE_RECOVERY_REQUIRED",
            }:
                await custody.retire_for_exchange(
                    exchange,
                    state_sha256=flow.state_sha256,
                    reason=(
                        "deadline"
                        if exc.code == "OAUTH_EXCHANGE_DEADLINE_EXPIRED"
                        else "ambiguous"
                    ),
                )
            raise
        if terminal is not None:
            if custody is not None:
                await custody.retire_for_exchange(
                    exchange,
                    state_sha256=flow.state_sha256,
                    reason=(
                        "ambiguous"
                        if isinstance(terminal, OAuthExchangeAmbiguous)
                        else "terminal"
                    ),
                )
            return terminal, exchange
        if custody is not None:
            authorization_code, _command = await custody.recover_code_for_exchange(
                exchange,
                state_sha256=flow.state_sha256,
                now=now,
            )
        if not isinstance(authorization_code, OAuthAuthorizationCodeSecret):
            raise OAuthContractError("OAUTH_AUTHORIZATION_CODE_RECOVERY_REQUIRED")
        try:
            terminal = await exchange_oauth_code_once(
                broker=self._broker,
                repository=self._flows,
                command=exchange,
                authorization_code=authorization_code,
                now=now,
            )
        except OAuthContractError as exc:
            if custody is not None and exc.code in {
                "OAUTH_EXCHANGE_DEADLINE_EXPIRED",
                "OAUTH_EXCHANGE_RECOVERY_REQUIRED",
            }:
                await custody.retire_for_exchange(
                    exchange,
                    state_sha256=flow.state_sha256,
                    reason=(
                        "deadline"
                        if exc.code == "OAUTH_EXCHANGE_DEADLINE_EXPIRED"
                        else "ambiguous"
                    ),
                )
            raise
        except Exception:
            if custody is not None:
                try:
                    recovered = await read_oauth_exchange_terminal(
                        broker=self._broker,
                        command=exchange,
                    )
                except Exception:
                    recovered = None
                if recovered is not None:
                    await custody.retire_for_exchange(
                        exchange,
                        state_sha256=flow.state_sha256,
                        reason=(
                            "ambiguous"
                            if isinstance(recovered, OAuthExchangeAmbiguous)
                            else "terminal"
                        ),
                    )
            raise
        if custody is not None:
            await custody.retire_for_exchange(
                exchange,
                state_sha256=flow.state_sha256,
                reason=(
                    "ambiguous"
                    if isinstance(terminal, OAuthExchangeAmbiguous)
                    else "terminal"
                ),
            )
        return terminal, exchange

    async def recover_exchange_once(
        self,
        *,
        flow: OAuthFlowRecord,
        consumption: OAuthFlowConsumption,
    ) -> OAuthBrokerGrant | OAuthExchangeAmbiguous:
        """Resume a consumed callback without any callback plaintext."""

        if self._authorization_code_custody is None:
            raise OAuthContractError("OAUTH_AUTHORIZATION_CODE_RECOVERY_REQUIRED")
        terminal, _exchange = await self._exchange_once(
            flow=flow,
            consumption=consumption,
            authorization_code=None,
            now=_aware(self._now(), "now"),
        )
        return terminal

    async def read_completion(
        self, *, provider: ConnectorProvider, callback_binding_sha256: str
    ) -> ConnectedConnectionView | None:
        if not isinstance(provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        result = await self._store.read_callback(
            provider=provider,
            callback_binding_sha256=_sha(
                callback_binding_sha256, "callback_binding_sha256"
            ),
        )
        if result is not None and (
            type(result) is not ConnectedConnectionView
            or result.provider is not provider
            or result.authorization_state is not ConnectionAuthorizationState.ACTIVE
        ):
            raise OAuthContractError("OAUTH_COMPLETION_BINDING_MISMATCH")
        return result


__all__ = [
    "ConnectedAppOAuthOrchestrator",
    "ConnectedOAuthOperatorStore",
    "OAuthCallbackDenialReceipt",
    "OAuthCallbackReservation",
    "OAuthStartReservation",
    "oauth_denial_binding_sha256",
    "oauth_start_command_binding_sha256",
]
