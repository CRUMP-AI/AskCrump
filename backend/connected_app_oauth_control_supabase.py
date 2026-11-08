"""Supabase authority store for the public-to-durable OAuth bridge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
from typing import Any, Mapping, Protocol
from uuid import UUID

from .connected_app_contracts import ConnectionAuthorizationState, ConnectorAccountKind
from .connected_app_oauth import (
    OAuthConsumeCommand,
    OAuthFlowConsumption,
    OAuthFlowRecord,
)
from .connected_app_oauth_control import (
    OAuthCallbackDenialReceipt,
    OAuthCallbackReservation,
    OAuthStartReservation,
    oauth_start_command_binding_sha256,
)
from .connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from .connected_app_service import (
    ConnectedConnectionView,
    OAuthStartCommand,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_START_KEYS = frozenset(
    {
        "request_id",
        "owner_id",
        "session_binding_sha256",
        "command_binding_sha256",
        "requested_connection_id",
        "flow_id",
        "nonce_id",
        "connection_id",
        "connection_incarnation_id",
        "expected_base_revision",
        "current_flow_nonce_sha256",
        "provider",
        "resource",
        "account_kind",
        "actions",
        "actions_sha256",
        "redirect_uri_sha256",
        "requested_at",
        "expires_at",
    }
)
_CONNECTION_KEYS = frozenset(
    {
        "connection_id",
        "provider",
        "resource",
        "account_kind",
        "granted_actions",
        "authorization_state",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "authorization_expires_at",
        "updated_at",
    }
)
_CALLBACK_CANDIDATE_KEYS = frozenset({"flow", "callback_received_at"})
_DENIAL_KEYS = frozenset({"denied", "flow_id", "connection_id", "observed_at"})
_CONSUMPTION_KEYS = frozenset(
    {
        "consumption_id",
        "flow_id",
        "connection_id",
        "connection_incarnation_id",
        "expected_base_revision",
        "current_flow_nonce_sha256",
        "consume_binding_sha256",
        "flow_binding_sha256",
        "consumed_at",
    }
)


class ConnectedOAuthBridgeRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class ConnectedOAuthFlowDecoder(Protocol):
    def decode_flow(self, value: object) -> OAuthFlowRecord: ...


class ConnectedOAuthOperatorStoreError(RuntimeError):
    pass


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _uuid(value: object, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID") from None
    if str(parsed) != value:
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    return value


def _time(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_SHAPE_INVALID"
            ) from None
    else:
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    return parsed.astimezone(UTC)


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    return dict(value)


def _enum(enum_type: type[Any], value: object) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID") from None


def _actions(value: object, resource: ConnectorResource) -> frozenset[ConnectorActionKind]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    actions = frozenset(_enum(ConnectorActionKind, item) for item in value)
    if len(actions) != len(value) or any(
        ConnectedActionPolicy.requirement(action).resource is not resource
        for action in actions
    ):
        raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_SHAPE_INVALID")
    return actions


class SupabaseConnectedOAuthOperatorStore:
    """Content-free start/callback replay ledger over four service-role RPCs."""

    def __init__(
        self,
        *,
        database: ConnectedOAuthBridgeRPC,
        flow_decoder: ConnectedOAuthFlowDecoder,
        redirect_uris: Mapping[ConnectorProvider, str],
    ) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected OAuth bridge RPC is invalid")
        if not callable(getattr(flow_decoder, "decode_flow", None)):
            raise TypeError("connected OAuth flow decoder is invalid")
        if set(redirect_uris) != set(ConnectorProvider) or any(
            not isinstance(value, str) or not value
            for value in redirect_uris.values()
        ):
            raise ValueError("every provider requires one exact redirect URI")
        self._database = database
        self._flow_decoder = flow_decoder
        self._redirect_uris = dict(redirect_uris)

    async def _rpc(self, name: str, payload: dict[str, object], *, read: bool) -> object:
        try:
            return await self._database.rpc(name, payload, retry_transient=read)
        except ConnectedOAuthOperatorStoreError:
            raise
        except Exception:
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_UNAVAILABLE"
            ) from None

    def _reservation(self, value: object) -> OAuthStartReservation:
        row = _object(value, _START_KEYS)
        provider = _enum(ConnectorProvider, row["provider"])
        resource = _enum(ConnectorResource, row["resource"])
        account_kind = _enum(ConnectorAccountKind, row["account_kind"])
        actions = _actions(row["actions"], resource)
        redirect_uri = self._redirect_uris[provider]
        if not hmac.compare_digest(_digest(redirect_uri), _sha(row["redirect_uri_sha256"])):
            raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_BINDING_MISMATCH")
        if not hmac.compare_digest(action_set_sha256(actions), _sha(row["actions_sha256"])):
            raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_BINDING_MISMATCH")
        try:
            command = OAuthStartCommand(
                request_id=_uuid(row["request_id"], "request_id") or "",
                owner_id=_uuid(row["owner_id"], "owner_id") or "",
                session_binding_sha256=_sha(row["session_binding_sha256"]),
                provider=provider,
                resource=resource,
                account_kind=account_kind,
                actions=actions,
                redirect_uri=redirect_uri,
                connection_id=_uuid(
                    row["requested_connection_id"],
                    "requested_connection_id",
                    nullable=True,
                ),
                requested_at=_time(row["requested_at"]),
            )
            reservation = OAuthStartReservation(
                command=command,
                flow_id=_uuid(row["flow_id"], "flow_id") or "",
                nonce_id=_uuid(row["nonce_id"], "nonce_id") or "",
                connection_id=_uuid(row["connection_id"], "connection_id") or "",
                connection_incarnation_id=_uuid(
                    row["connection_incarnation_id"], "connection_incarnation_id"
                )
                or "",
                expected_base_revision=int(row["expected_base_revision"]),
                current_flow_nonce_sha256=_sha(row["current_flow_nonce_sha256"]),
                created_at=_time(row["requested_at"]),
                expires_at=_time(row["expires_at"]),
            )
        except (TypeError, ValueError, OverflowError):
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_SHAPE_INVALID"
            ) from None
        if not hmac.compare_digest(
            oauth_start_command_binding_sha256(command),
            _sha(row["command_binding_sha256"]),
        ):
            raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_BINDING_MISMATCH")
        return reservation

    async def prepare_start(
        self,
        command: OAuthStartCommand,
        *,
        proposed_flow_id: str,
        proposed_nonce_id: str,
        proposed_connection_id: str,
        proposed_connection_incarnation_id: str,
    ) -> OAuthStartReservation:
        if type(command) is not OAuthStartCommand:
            raise TypeError("command must be an OAuthStartCommand")
        expires = command.requested_at + timedelta(minutes=10)
        value = await self._rpc(
            "connected_app_operator_prepare_oauth_start_v2",
            {
                "p_request_id": command.request_id,
                "p_owner_id": command.owner_id,
                "p_session_binding_sha256": command.session_binding_sha256,
                "p_command_binding_sha256": oauth_start_command_binding_sha256(command),
                "p_requested_connection_id": command.connection_id,
                "p_proposed_flow_id": proposed_flow_id,
                "p_proposed_nonce_id": proposed_nonce_id,
                "p_proposed_connection_id": proposed_connection_id,
                "p_proposed_connection_incarnation_id": proposed_connection_incarnation_id,
                "p_current_flow_nonce_sha256": _digest(proposed_nonce_id),
                "p_provider": command.provider.value,
                "p_resource": command.resource.value,
                "p_account_kind": command.account_kind.value,
                "p_actions": sorted(action.value for action in command.actions),
                "p_actions_sha256": action_set_sha256(command.actions),
                "p_redirect_uri_sha256": _digest(command.redirect_uri),
                "p_requested_at": command.requested_at.isoformat(),
                "p_expires_at": expires.isoformat(),
            },
            read=False,
        )
        reservation = self._reservation(value)
        if not hmac.compare_digest(
            oauth_start_command_binding_sha256(reservation.command),
            oauth_start_command_binding_sha256(command),
        ):
            raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_BINDING_MISMATCH")
        return reservation

    async def read_start(
        self, *, owner_id: str, request_id: str
    ) -> OAuthStartReservation | None:
        value = await self._rpc(
            "connected_app_operator_read_oauth_start_v1",
            {"p_owner_id": owner_id, "p_request_id": request_id},
            read=True,
        )
        return None if value is None else self._reservation(value)

    async def bind_callback(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        callback_binding_sha256: str,
        received_at: datetime,
    ) -> OAuthCallbackReservation:
        value = await self._rpc(
            "connected_app_operator_prepare_oauth_callback_v2",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_session_binding_sha256": _sha(session_binding_sha256),
                "p_provider": provider.value,
                "p_state_sha256": _sha(state_sha256),
                "p_callback_binding_sha256": _sha(callback_binding_sha256),
                "p_received_at": _time(received_at).isoformat(),
            },
            read=False,
        )
        row = _object(value, _CALLBACK_CANDIDATE_KEYS)
        try:
            flow = self._flow_decoder.decode_flow(row["flow"])
            result = OAuthCallbackReservation(
                flow=flow,
                accepted_at=_time(row["callback_received_at"]),
            )
        except ConnectedOAuthOperatorStoreError:
            raise
        except Exception:
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_SHAPE_INVALID"
            ) from None
        if (
            flow.owner_id != owner_id
            or not hmac.compare_digest(
                flow.session_binding_sha256,
                session_binding_sha256,
            )
            or flow.provider is not provider
            or not hmac.compare_digest(flow.state_sha256, state_sha256)
        ):
            raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_BINDING_MISMATCH")
        return result

    async def accept_callback(
        self,
        *,
        provider: ConnectorProvider,
        state_sha256: str,
        callback_binding_sha256: str,
        received_at: datetime,
        command: OAuthConsumeCommand,
    ) -> OAuthFlowConsumption:
        if not isinstance(command, OAuthConsumeCommand):
            raise TypeError("command must be an OAuthConsumeCommand")
        value = await self._rpc(
            "connected_app_operator_accept_oauth_callback_v1",
            {
                "p_provider": provider.value,
                "p_state_sha256": _sha(state_sha256),
                "p_callback_binding_sha256": _sha(callback_binding_sha256),
                "p_received_at": _time(received_at).isoformat(),
                "p_consumption_id": command.consumption_id,
                "p_owner_id": command.owner_id,
                "p_connection_id": command.connection_id,
                "p_connection_incarnation_id": command.connection_incarnation_id,
                "p_expected_base_revision": command.expected_base_revision,
                "p_current_flow_nonce_sha256": command.current_flow_nonce_sha256,
                "p_session_binding_sha256": command.session_binding_sha256,
                "p_flow_binding_sha256": command.flow_binding_sha256,
                "p_consume_binding_sha256": command.binding_sha256,
            },
            read=False,
        )
        row = _object(value, _CONSUMPTION_KEYS)
        try:
            result = OAuthFlowConsumption(
                consumption_id=_uuid(row["consumption_id"], "consumption_id") or "",
                flow_id=_uuid(row["flow_id"], "flow_id") or "",
                connection_id=_uuid(row["connection_id"], "connection_id") or "",
                connection_incarnation_id=_uuid(
                    row["connection_incarnation_id"], "connection_incarnation_id"
                )
                or "",
                expected_base_revision=int(row["expected_base_revision"]),
                current_flow_nonce_sha256=_sha(row["current_flow_nonce_sha256"]),
                consume_binding_sha256=_sha(row["consume_binding_sha256"]),
                flow_binding_sha256=_sha(row["flow_binding_sha256"]),
                consumed_at=_time(row["consumed_at"]),
            )
        except (TypeError, ValueError, OverflowError):
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_SHAPE_INVALID"
            ) from None
        if (
            result.consumption_id != command.consumption_id
            or result.flow_id != command.flow_id
            or result.connection_id != command.connection_id
            or result.connection_incarnation_id != command.connection_incarnation_id
            or result.expected_base_revision != command.expected_base_revision
            or not hmac.compare_digest(
                result.current_flow_nonce_sha256,
                command.current_flow_nonce_sha256,
            )
            or not hmac.compare_digest(
                result.consume_binding_sha256,
                command.binding_sha256,
            )
            or not hmac.compare_digest(
                result.flow_binding_sha256,
                command.flow_binding_sha256,
            )
        ):
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_BINDING_MISMATCH"
            )
        return result

    async def deny_callback(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        denial_binding_sha256: str,
        received_at: datetime,
    ) -> OAuthCallbackDenialReceipt:
        value = await self._rpc(
            "connected_app_operator_deny_oauth_callback_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_session_binding_sha256": _sha(session_binding_sha256),
                "p_provider": provider.value,
                "p_state_sha256": _sha(state_sha256),
                "p_error": "access_denied",
                "p_denial_binding_sha256": _sha(denial_binding_sha256),
                "p_received_at": _time(received_at).isoformat(),
            },
            read=False,
        )
        row = _object(value, _DENIAL_KEYS)
        if row["denied"] is not True:
            raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_BINDING_MISMATCH")
        try:
            return OAuthCallbackDenialReceipt(
                owner_id=owner_id,
                connection_id=_uuid(row["connection_id"], "connection_id") or "",
                flow_id=_uuid(row["flow_id"], "flow_id") or "",
                provider=provider,
                observed_at=_time(row["observed_at"]),
            )
        except (TypeError, ValueError):
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_SHAPE_INVALID"
            ) from None

    @staticmethod
    def _connection(value: object) -> ConnectedConnectionView:
        row = _object(value, _CONNECTION_KEYS)
        provider = _enum(ConnectorProvider, row["provider"])
        resource = _enum(ConnectorResource, row["resource"])
        actions = _actions(row["granted_actions"], resource)
        try:
            return ConnectedConnectionView(
                connection_id=_uuid(row["connection_id"], "connection_id") or "",
                provider=provider,
                resource=resource,
                account_kind=_enum(ConnectorAccountKind, row["account_kind"]),
                granted_actions=tuple(sorted(actions, key=lambda item: item.value)),
                authorization_state=_enum(
                    ConnectionAuthorizationState, row["authorization_state"]
                ),
                authorization_revision=int(row["authorization_revision"]),
                authorization_snapshot_sha256=_sha(
                    row["authorization_snapshot_sha256"]
                ),
                expires_at=_time(row["authorization_expires_at"]),
                updated_at=_time(row["updated_at"]),
            )
        except (TypeError, ValueError, OverflowError):
            raise ConnectedOAuthOperatorStoreError(
                "OAUTH_OPERATOR_STORE_SHAPE_INVALID"
            ) from None

    async def read_callback(
        self, *, provider: ConnectorProvider, callback_binding_sha256: str
    ) -> ConnectedConnectionView | None:
        value = await self._rpc(
            "connected_app_operator_read_oauth_callback_v1",
            {
                "p_provider": provider.value,
                "p_callback_binding_sha256": _sha(callback_binding_sha256),
            },
            read=True,
        )
        if value is None:
            return None
        connection = self._connection(value)
        if connection.provider is not provider:
            raise ConnectedOAuthOperatorStoreError("OAUTH_OPERATOR_STORE_BINDING_MISMATCH")
        return connection


__all__ = [
    "ConnectedOAuthBridgeRPC",
    "ConnectedOAuthFlowDecoder",
    "ConnectedOAuthOperatorStoreError",
    "SupabaseConnectedOAuthOperatorStore",
]
