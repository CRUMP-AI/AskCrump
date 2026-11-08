"""Strict Supabase/PostgREST composition for the connected-app service boundary.

Only service-role RPCs are used.  Private connected-app tables are never a
Data API fallback.  OAuth secret custody and encrypted approval-preview
payloads stay behind injected, typed boundaries; this adapter persists and
parses only owner-scoped control metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any, Protocol
from uuid import UUID, uuid4

from .connected_app_contracts import ConnectionAuthorizationState
from .connected_app_action_preparation import (
    ConnectedActionPreparationCommand,
    ConnectedActionPreparationStatus,
    ConnectedActionPreparationView,
)
from .connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorApprovalClass,
    ConnectorProvider,
    ConnectorResource,
)
from .connected_app_service import (
    ApprovalDecisionCommand,
    ConnectedApprovalReviewPreview,
    ConnectedActionPublicStatus,
    ConnectedActionView,
    ConnectedAppServiceError,
    ConnectedApprovalStatus,
    ConnectedApprovalView,
    ConnectedConnectionAuthorityView,
    ConnectedConnectionView,
    ConnectedScheduleStatus,
    ConnectedScheduleView,
    DisconnectCommand,
    DisconnectView,
    OAuthCallbackCommand,
    OAuthStartCommand,
    OAuthStartView,
    ScheduleCreateCommand,
    ScheduleTransitionCommand,
)
from .connected_app_contracts import ConnectorAccountKind


class ConnectedAppRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class ConnectedAppOAuthControl(Protocol):
    """Secret-safe OAuth orchestration composed from the reviewed OAuth core."""

    async def start_once(self, command: OAuthStartCommand) -> OAuthStartView: ...

    async def read_start(self, *, owner_id: str, request_id: str) -> OAuthStartView | None: ...

    async def complete_once(self, command: OAuthCallbackCommand) -> ConnectedConnectionView: ...

    async def deny_once(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        received_at: datetime,
    ) -> object: ...

    async def read_completion(
        self, *, provider: ConnectorProvider, callback_binding_sha256: str
    ) -> ConnectedConnectionView | None: ...


class ConnectedApprovalPreviewResolver(Protocol):
    """Resolve one encrypted preview without exposing its plaintext to SQL."""

    async def resolve(
        self,
        *,
        owner_id: str,
        approval_id: str,
        connection_id: str,
        action_id: str,
        provider: ConnectorProvider,
        action: ConnectorActionKind,
        approval_binding_sha256: str,
        parameters_sha256: str,
        resource_version_sha256: str | None,
        review_payload_ref: str,
        preview_sha256: str,
    ) -> ConnectedApprovalReviewPreview: ...


class ConnectedControlPlaneError(RuntimeError):
    """Fixed, content-free storage/composition failure."""

    _ALLOWED = frozenset(
        {
            "CONNECTED_PREVIEW_FAILED",
            "CONNECTED_RPC_FAILED",
            "CONNECTED_RPC_SHAPE_INVALID",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            code = "CONNECTED_RPC_FAILED"
        super().__init__(code)
        self.code = code


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
_AUTHORITY_KEYS = frozenset(
    {
        "connection_id",
        "provider",
        "resource",
        "authorization_state",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_scopes_sha256",
        "granted_actions",
        "authorization_expires_at",
    }
)
_SCHEDULE_KEYS = frozenset(
    {
        "schedule_id",
        "connection_id",
        "task_id",
        "provider",
        "resource",
        "action",
        "action_template_ref",
        "parameters_sha256",
        "task_state_revision",
        "time_zone",
        "cadence_seconds",
        "quiet_start_minute",
        "quiet_end_minute",
        "requires_approval_every_run",
        "status",
        "next_run_at",
        "updated_at",
    }
)
_ACTION_KEYS = frozenset(
    {
        "action_id",
        "connection_id",
        "task_id",
        "turn_id",
        "provider",
        "resource",
        "action",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_scopes_sha256",
        "policy_version",
        "action_revision",
        "status",
        "parameters_sha256",
        "resource_version_sha256",
        "preview_sha256",
        "updated_at",
    }
)
_APPROVAL_KEYS = frozenset(
    {
        "approval_id",
        "action_id",
        "connection_id",
        "task_id",
        "turn_id",
        "provider",
        "resource",
        "action",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_scopes_sha256",
        "policy_version",
        "action_revision",
        "status",
        "approval_binding_sha256",
        "parameters_sha256",
        "resource_version_sha256",
        "preview_sha256",
        "review_payload_ref",
        "decision_id",
        "decision_session_binding_sha256",
        "expires_at",
        "decided_at",
    }
)
_PREPARATION_KEYS = frozenset(
    {
        "request_id",
        "owner_id",
        "command_binding_sha256",
        "grant_id",
        "action_id",
        "task_id",
        "turn_id",
        "connection_id",
        "provider",
        "resource",
        "action",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "grant_actions_sha256",
        "task_state_revision",
        "payload_id",
        "payload_reference_binding_sha256",
        "parameters_sha256",
        "resource_version_sha256",
        "policy_version",
        "mutates_external_state",
        "approval_class",
        "status",
        "approval_id",
        "approval_binding_sha256",
        "preview_payload_id",
        "preview_reference_binding_sha256",
        "preview_sha256",
        "requested_at",
        "expires_at",
    }
)


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return value  # type: ignore[return-value]


def _optional_object(value: object, keys: frozenset[str]) -> dict[str, object] | None:
    if value is None:
        return None
    return _object(value, keys)


def _list(value: object, keys: frozenset[str], *, maximum: int = 100) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > maximum:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return [_object(row, keys) for row in value]


def _text(value: object, *, nullable: bool = False, maximum: int = 1024) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum or value != value.strip():
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return value


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return value


def _uuid(value: object, *, nullable: bool = False) -> str | None:
    text = _text(value, nullable=nullable)
    if text is None:
        return None
    try:
        parsed = str(UUID(text))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID") from None
    if parsed != text:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return text


def _instant(value: object, *, nullable: bool = False) -> datetime | None:
    text = _text(value, nullable=nullable)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return parsed.astimezone(UTC)


def _enum(value: object, enum_type: type[Any]) -> Any:
    text = _text(value)
    try:
        return enum_type(text)
    except (TypeError, ValueError):
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID") from None


def _actions(value: object) -> tuple[ConnectorActionKind, ...]:
    if type(value) is not list or not value or len(value) > 16:
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    result = tuple(_enum(item, ConnectorActionKind) for item in value)
    if len(result) != len(set(result)) or result != tuple(
        sorted(result, key=lambda item: item.value)
    ):
        raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
    return result


def _command_hash(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )
    return hashlib.sha256(encoded).hexdigest()


def _record_guard(parser: Any) -> Any:
    """Quarantine constructor details from malformed database records."""

    def wrapped(row: dict[str, object]) -> Any:
        try:
            return parser(row)
        except ConnectedControlPlaneError:
            raise
        except Exception:
            raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID") from None

    return wrapped


@_record_guard
def _connection(row: dict[str, object]) -> ConnectedConnectionView:
    return ConnectedConnectionView(
        connection_id=_uuid(row["connection_id"]) or "",
        provider=_enum(row["provider"], ConnectorProvider),
        resource=_enum(row["resource"], ConnectorResource),
        account_kind=_enum(row["account_kind"], ConnectorAccountKind),
        granted_actions=_actions(row["granted_actions"]),
        authorization_state=_enum(row["authorization_state"], ConnectionAuthorizationState),
        authorization_revision=_integer(row["authorization_revision"]),
        authorization_snapshot_sha256=_text(row["authorization_snapshot_sha256"], nullable=True),
        expires_at=_instant(row["authorization_expires_at"], nullable=True),
        updated_at=_instant(row["updated_at"]) or datetime.min.replace(tzinfo=UTC),
    )


@_record_guard
def _authority(row: dict[str, object]) -> ConnectedConnectionAuthorityView:
    return ConnectedConnectionAuthorityView(
        connection_id=_uuid(row["connection_id"]) or "",
        provider=_enum(row["provider"], ConnectorProvider),
        resource=_enum(row["resource"], ConnectorResource),
        authorization_state=_enum(row["authorization_state"], ConnectionAuthorizationState),
        authorization_revision=_integer(row["authorization_revision"]),
        authorization_snapshot_sha256=_text(row["authorization_snapshot_sha256"]) or "",
        granted_scopes_sha256=_text(row["granted_scopes_sha256"]) or "",
        granted_actions=_actions(row["granted_actions"]),
        expires_at=_instant(row["authorization_expires_at"]) or datetime.min.replace(tzinfo=UTC),
    )


@_record_guard
def _schedule(row: dict[str, object]) -> ConnectedScheduleView:
    return ConnectedScheduleView(
        schedule_id=_uuid(row["schedule_id"]) or "",
        connection_id=_uuid(row["connection_id"]) or "",
        task_id=_uuid(row["task_id"]) or "",
        provider=_enum(row["provider"], ConnectorProvider),
        resource=_enum(row["resource"], ConnectorResource),
        action=_enum(row["action"], ConnectorActionKind),
        action_template_ref=_uuid(row["action_template_ref"]) or "",
        parameters_sha256=_text(row["parameters_sha256"]) or "",
        task_state_revision=_integer(row["task_state_revision"]),
        time_zone=_text(row["time_zone"]) or "",
        cadence_seconds=_integer(row["cadence_seconds"]),
        quiet_start_minute=(
            None if row["quiet_start_minute"] is None else _integer(row["quiet_start_minute"])
        ),
        quiet_end_minute=(
            None if row["quiet_end_minute"] is None else _integer(row["quiet_end_minute"])
        ),
        requires_approval_every_run=_boolean(row["requires_approval_every_run"]),
        status=_enum(row["status"], ConnectedScheduleStatus),
        next_run_at=_instant(row["next_run_at"], nullable=True),
        updated_at=_instant(row["updated_at"]) or datetime.min.replace(tzinfo=UTC),
    )


@_record_guard
def _action(row: dict[str, object]) -> ConnectedActionView:
    return ConnectedActionView(
        action_id=_uuid(row["action_id"]) or "",
        connection_id=_uuid(row["connection_id"]) or "",
        task_id=_uuid(row["task_id"]) or "",
        turn_id=_uuid(row["turn_id"]) or "",
        provider=_enum(row["provider"], ConnectorProvider),
        resource=_enum(row["resource"], ConnectorResource),
        action=_enum(row["action"], ConnectorActionKind),
        authorization_revision=_integer(row["authorization_revision"]),
        authorization_snapshot_sha256=_text(row["authorization_snapshot_sha256"]) or "",
        granted_scopes_sha256=_text(row["granted_scopes_sha256"]) or "",
        policy_version=_text(row["policy_version"], maximum=128) or "",
        action_revision=_integer(row["action_revision"]),
        status=_enum(row["status"], ConnectedActionPublicStatus),
        parameters_sha256=_text(row["parameters_sha256"]) or "",
        resource_version_sha256=_text(row["resource_version_sha256"], nullable=True),
        preview_sha256=_text(row["preview_sha256"], nullable=True),
        updated_at=_instant(row["updated_at"]) or datetime.min.replace(tzinfo=UTC),
    )


@_record_guard
def _preparation(row: dict[str, object]) -> ConnectedActionPreparationView:
    return ConnectedActionPreparationView(
        request_id=_uuid(row["request_id"]) or "",
        owner_id=_uuid(row["owner_id"]) or "",
        command_binding_sha256=_text(row["command_binding_sha256"]) or "",
        grant_id=_uuid(row["grant_id"]) or "",
        action_id=_uuid(row["action_id"]) or "",
        task_id=_uuid(row["task_id"]) or "",
        turn_id=_uuid(row["turn_id"]) or "",
        connection_id=_uuid(row["connection_id"]) or "",
        provider=_enum(row["provider"], ConnectorProvider),
        resource=_enum(row["resource"], ConnectorResource),
        action=_enum(row["action"], ConnectorActionKind),
        authorization_revision=_integer(row["authorization_revision"]),
        authorization_snapshot_sha256=_text(row["authorization_snapshot_sha256"]) or "",
        granted_actions_sha256=_text(row["granted_actions_sha256"]) or "",
        granted_scopes_sha256=_text(row["granted_scopes_sha256"]) or "",
        grant_actions_sha256=_text(row["grant_actions_sha256"]) or "",
        task_state_revision=_integer(row["task_state_revision"]),
        payload_id=_uuid(row["payload_id"]) or "",
        payload_reference_binding_sha256=(_text(row["payload_reference_binding_sha256"]) or ""),
        parameters_sha256=_text(row["parameters_sha256"]) or "",
        resource_version_sha256=_text(row["resource_version_sha256"], nullable=True),
        policy_version=_text(row["policy_version"], maximum=128) or "",
        mutates_external_state=_boolean(row["mutates_external_state"]),
        approval_class=_enum(row["approval_class"], ConnectorApprovalClass),
        status=_enum(row["status"], ConnectedActionPreparationStatus),
        approval_id=_uuid(row["approval_id"], nullable=True),
        approval_binding_sha256=_text(row["approval_binding_sha256"], nullable=True),
        preview_payload_id=_uuid(row["preview_payload_id"], nullable=True),
        preview_reference_binding_sha256=_text(
            row["preview_reference_binding_sha256"], nullable=True
        ),
        preview_sha256=_text(row["preview_sha256"], nullable=True),
        requested_at=_instant(row["requested_at"]) or datetime.min.replace(tzinfo=UTC),
        expires_at=_instant(row["expires_at"]) or datetime.min.replace(tzinfo=UTC),
    )


class SupabaseConnectedAppControlPlane:
    """Owner-scoped service control plane over exact, attested RPCs."""

    def __init__(
        self,
        *,
        database: ConnectedAppRPC,
        oauth: ConnectedAppOAuthControl,
        previews: ConnectedApprovalPreviewResolver,
        now: Any = lambda: datetime.now(UTC),
        new_uuid: Any = lambda: str(uuid4()),
    ) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected-app RPC boundary is invalid")
        if any(
            not callable(getattr(oauth, name, None))
            for name in ("start_once", "read_start", "complete_once", "read_completion")
        ):
            raise TypeError("connected-app OAuth boundary is invalid")
        if not callable(getattr(previews, "resolve", None)):
            raise TypeError("connected-app preview boundary is invalid")
        if not callable(now) or not callable(new_uuid):
            raise TypeError("connected-app control-plane factories are invalid")
        self._database = database
        self._oauth = oauth
        self._previews = previews
        self._now = now
        self._new_uuid = new_uuid

    async def _rpc(self, name: str, payload: dict[str, Any], *, read: bool = False) -> Any:
        try:
            return await self._database.rpc(name, payload, retry_transient=read)
        except ConnectedControlPlaneError:
            raise
        except Exception:
            raise ConnectedControlPlaneError("CONNECTED_RPC_FAILED") from None

    async def list_connections(self, *, owner_id: str) -> tuple[ConnectedConnectionView, ...]:
        rows = _list(
            await self._rpc(
                "connected_app_operator_list_connections_v1", {"p_owner_id": owner_id}, read=True
            ),
            _CONNECTION_KEYS,
            maximum=32,
        )
        result = tuple(_connection(row) for row in rows)
        if len({item.connection_id for item in result}) != len(result):
            raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
        return result

    async def get_connection_authority(
        self, *, owner_id: str, connection_id: str
    ) -> ConnectedConnectionAuthorityView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_get_connection_authority_v1",
                {"p_owner_id": owner_id, "p_connection_id": connection_id},
                read=True,
            ),
            _AUTHORITY_KEYS,
        )
        return None if row is None else _authority(row)

    async def start_oauth_once(self, command: OAuthStartCommand) -> OAuthStartView:
        return await self._oauth.start_once(command)

    async def readback_oauth_start(
        self, *, owner_id: str, request_id: str
    ) -> OAuthStartView | None:
        return await self._oauth.read_start(owner_id=owner_id, request_id=request_id)

    async def complete_oauth_callback(
        self, command: OAuthCallbackCommand
    ) -> ConnectedConnectionView:
        return await self._oauth.complete_once(command)

    async def deny_oauth_callback(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        received_at: datetime,
    ) -> None:
        await self._oauth.deny_once(
            owner_id=owner_id,
            session_binding_sha256=session_binding_sha256,
            provider=provider,
            state_sha256=state_sha256,
            received_at=received_at,
        )

    async def readback_oauth_callback(
        self, *, provider: ConnectorProvider, callback_binding_sha256: str
    ) -> ConnectedConnectionView | None:
        return await self._oauth.read_completion(
            provider=provider, callback_binding_sha256=callback_binding_sha256
        )

    async def disconnect_once(self, command: DisconnectCommand) -> DisconnectView:
        cleanup_id = self._new_uuid()
        command_binding = _command_hash(
            {
                "version": "connected-operator-disconnect-v1",
                "request_id": command.request_id,
                "owner_id": command.owner_id,
                "session_binding_sha256": command.session_binding_sha256,
                "connection_id": command.connection_id,
                "requested_at": command.requested_at.isoformat(),
            }
        )
        row = _object(
            await self._rpc(
                "connected_app_operator_disconnect_v1",
                {
                    "p_request_id": command.request_id,
                    "p_owner_id": command.owner_id,
                    "p_session_binding_sha256": command.session_binding_sha256,
                    "p_connection_id": command.connection_id,
                    "p_cleanup_id": cleanup_id,
                    "p_command_binding_sha256": command_binding,
                    "p_requested_at": command.requested_at.isoformat(),
                },
            ),
            _CONNECTION_KEYS,
        )
        return DisconnectView(
            connection=_connection(row),
            grants_invalidated=True,
            schedules_invalidated=True,
            broker_cleanup_enqueued=True,
            updated_at=_instant(row["updated_at"]) or datetime.min.replace(tzinfo=UTC),
        )

    async def readback_disconnect(
        self, *, owner_id: str, connection_id: str, request_id: str
    ) -> DisconnectView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_read_disconnect_v1",
                {
                    "p_owner_id": owner_id,
                    "p_connection_id": connection_id,
                    "p_request_id": request_id,
                },
                read=True,
            ),
            _CONNECTION_KEYS,
        )
        if row is None:
            return None
        return DisconnectView(
            connection=_connection(row),
            grants_invalidated=True,
            schedules_invalidated=True,
            broker_cleanup_enqueued=True,
            updated_at=_instant(row["updated_at"]) or datetime.min.replace(tzinfo=UTC),
        )

    async def list_schedules(self, *, owner_id: str) -> tuple[ConnectedScheduleView, ...]:
        rows = _list(
            await self._rpc(
                "connected_app_operator_list_schedules_v1", {"p_owner_id": owner_id}, read=True
            ),
            _SCHEDULE_KEYS,
        )
        result = tuple(_schedule(row) for row in rows)
        if len({item.schedule_id for item in result}) != len(result):
            raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
        return result

    async def get_schedule(
        self, *, owner_id: str, schedule_id: str
    ) -> ConnectedScheduleView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_get_schedule_v1",
                {"p_owner_id": owner_id, "p_schedule_id": schedule_id},
                read=True,
            ),
            _SCHEDULE_KEYS,
        )
        return None if row is None else _schedule(row)

    async def create_schedule_once(self, command: ScheduleCreateCommand) -> ConnectedScheduleView:
        schedule_id = self._new_uuid()
        next_run = command.requested_at.astimezone(UTC) + timedelta(seconds=command.cadence_seconds)
        command_binding = _command_hash(
            {
                "version": "connected-operator-schedule-create-v1",
                "request_id": command.request_id,
                "owner_id": command.owner_id,
                "session_binding_sha256": command.session_binding_sha256,
                "connection_id": command.connection_id,
                "task_id": command.task_id,
                "provider": command.provider.value,
                "resource": command.resource.value,
                "action": command.action.value,
                "action_template_ref": command.action_template_ref,
                "parameters_sha256": command.parameters_sha256,
                "time_zone": command.time_zone,
                "cadence_seconds": command.cadence_seconds,
                "quiet_start_minute": command.quiet_start_minute,
                "quiet_end_minute": command.quiet_end_minute,
                "requires_approval_every_run": command.requires_approval_every_run,
                "requested_at": command.requested_at.isoformat(),
            }
        )
        row = _object(
            await self._rpc(
                "connected_app_operator_create_schedule_v1",
                {
                    "p_request_id": command.request_id,
                    "p_schedule_id": schedule_id,
                    "p_owner_id": command.owner_id,
                    "p_session_binding_sha256": command.session_binding_sha256,
                    "p_command_binding_sha256": command_binding,
                    "p_connection_id": command.connection_id,
                    "p_task_id": command.task_id,
                    "p_provider": command.provider.value,
                    "p_resource": command.resource.value,
                    "p_action": command.action.value,
                    "p_action_template_ref": command.action_template_ref,
                    "p_parameters_sha256": command.parameters_sha256,
                    "p_time_zone": command.time_zone,
                    "p_cadence_seconds": command.cadence_seconds,
                    "p_quiet_start_minute": command.quiet_start_minute,
                    "p_quiet_end_minute": command.quiet_end_minute,
                    "p_requires_approval_every_run": command.requires_approval_every_run,
                    "p_requested_at": command.requested_at.isoformat(),
                    "p_next_run_at": next_run.isoformat(),
                },
            ),
            _SCHEDULE_KEYS,
        )
        return _schedule(row)

    async def readback_schedule_create(
        self, *, owner_id: str, request_id: str
    ) -> ConnectedScheduleView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_read_schedule_create_v1",
                {"p_owner_id": owner_id, "p_request_id": request_id},
                read=True,
            ),
            _SCHEDULE_KEYS,
        )
        return None if row is None else _schedule(row)

    async def transition_schedule_once(
        self, command: ScheduleTransitionCommand
    ) -> ConnectedScheduleView:
        command_binding = _command_hash(
            {
                "version": "connected-operator-schedule-transition-v1",
                "request_id": command.request_id,
                "owner_id": command.owner_id,
                "session_binding_sha256": command.session_binding_sha256,
                "schedule_id": command.schedule_id,
                "expected_task_state_revision": command.expected_task_state_revision,
                "expected_status": command.expected_status.value,
                "target_status": command.target.value,
                "requested_at": command.requested_at.isoformat(),
            }
        )
        row = _object(
            await self._rpc(
                "connected_app_operator_transition_schedule_v1",
                {
                    "p_request_id": command.request_id,
                    "p_owner_id": command.owner_id,
                    "p_session_binding_sha256": command.session_binding_sha256,
                    "p_command_binding_sha256": command_binding,
                    "p_schedule_id": command.schedule_id,
                    "p_expected_task_state_revision": command.expected_task_state_revision,
                    "p_expected_status": command.expected_status.value,
                    "p_target_status": command.target.value,
                    "p_requested_at": command.requested_at.isoformat(),
                },
            ),
            _SCHEDULE_KEYS,
        )
        return _schedule(row)

    async def readback_schedule_transition(
        self, *, owner_id: str, schedule_id: str, request_id: str
    ) -> ConnectedScheduleView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_read_schedule_transition_v1",
                {
                    "p_owner_id": owner_id,
                    "p_schedule_id": schedule_id,
                    "p_request_id": request_id,
                },
                read=True,
            ),
            _SCHEDULE_KEYS,
        )
        return None if row is None else _schedule(row)

    async def prepare_action_once(
        self,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView:
        review = command.review_payload
        row = _object(
            await self._rpc(
                "connected_app_operator_prepare_action_v1",
                {
                    "p_request_id": command.request_id,
                    "p_owner_id": command.owner_id,
                    "p_session_id": command.session_id,
                    "p_session_binding_sha256": command.session_binding_sha256,
                    "p_command_binding_sha256": command.command_binding_sha256,
                    "p_grant_id": command.grant_id,
                    "p_action_id": command.action_id,
                    "p_task_id": command.task_id,
                    "p_turn_id": command.turn_id,
                    "p_connection_id": command.connection_id,
                    "p_provider": command.provider.value,
                    "p_resource": command.resource.value,
                    "p_action": command.action.value,
                    "p_authorization_revision": command.authorization_revision,
                    "p_authorization_snapshot_sha256": (command.authorization_snapshot_sha256),
                    "p_granted_actions_sha256": command.granted_actions_sha256,
                    "p_granted_scopes_sha256": command.granted_scopes_sha256,
                    "p_task_state_revision": command.task_state_revision,
                    "p_payload_id": command.payload.payload_id,
                    "p_payload_reference_binding_sha256": command.payload.binding_sha256,
                    "p_parameters_sha256": command.payload.payload_sha256,
                    "p_resource_version_sha256": command.resource_version_sha256,
                    "p_policy_version": ConnectedActionPolicy.version,
                    "p_approval_id": command.approval_id,
                    "p_approval_binding_sha256": command.approval_binding_sha256,
                    "p_preview_payload_id": None if review is None else review.payload_id,
                    "p_preview_reference_binding_sha256": (
                        None if review is None else review.binding_sha256
                    ),
                    "p_preview_sha256": None if review is None else review.payload_sha256,
                    "p_requested_at": command.requested_at.isoformat(),
                    "p_expires_at": command.expires_at.isoformat(),
                },
            ),
            _PREPARATION_KEYS,
        )
        return _preparation(row)

    async def readback_action_preparation(
        self,
        *,
        owner_id: str,
        request_id: str,
    ) -> ConnectedActionPreparationView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_read_action_preparation_v1",
                {"p_owner_id": owner_id, "p_request_id": request_id},
                read=True,
            ),
            _PREPARATION_KEYS,
        )
        return None if row is None else _preparation(row)

    async def list_actions(self, *, owner_id: str) -> tuple[ConnectedActionView, ...]:
        rows = _list(
            await self._rpc(
                "connected_app_operator_list_actions_v1", {"p_owner_id": owner_id}, read=True
            ),
            _ACTION_KEYS,
        )
        result = tuple(_action(row) for row in rows)
        if len({item.action_id for item in result}) != len(result):
            raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
        return result

    async def get_action(self, *, owner_id: str, action_id: str) -> ConnectedActionView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_get_action_v1",
                {"p_owner_id": owner_id, "p_action_id": action_id},
                read=True,
            ),
            _ACTION_KEYS,
        )
        return None if row is None else _action(row)

    async def _approval(self, owner_id: str, row: dict[str, object]) -> ConnectedApprovalView:
        try:
            approval_id = _uuid(row["approval_id"]) or ""
            action_id = _uuid(row["action_id"]) or ""
            connection_id = _uuid(row["connection_id"]) or ""
            provider = _enum(row["provider"], ConnectorProvider)
            action = _enum(row["action"], ConnectorActionKind)
            preview = await self._previews.resolve(
                owner_id=owner_id,
                approval_id=approval_id,
                connection_id=connection_id,
                action_id=action_id,
                provider=provider,
                action=action,
                approval_binding_sha256=_text(row["approval_binding_sha256"]) or "",
                parameters_sha256=_text(row["parameters_sha256"]) or "",
                resource_version_sha256=_text(
                    row["resource_version_sha256"], nullable=True
                ),
                review_payload_ref=_uuid(row["review_payload_ref"]) or "",
                preview_sha256=_text(row["preview_sha256"]) or "",
            )
            return ConnectedApprovalView(
                approval_id=approval_id,
                action_id=action_id,
                connection_id=connection_id,
                task_id=_uuid(row["task_id"]) or "",
                turn_id=_uuid(row["turn_id"]) or "",
                provider=provider,
                resource=_enum(row["resource"], ConnectorResource),
                action=action,
                authorization_revision=_integer(row["authorization_revision"]),
                authorization_snapshot_sha256=_text(row["authorization_snapshot_sha256"]) or "",
                granted_scopes_sha256=_text(row["granted_scopes_sha256"]) or "",
                policy_version=_text(row["policy_version"], maximum=128) or "",
                action_revision=_integer(row["action_revision"]),
                status=_enum(row["status"], ConnectedApprovalStatus),
                approval_binding_sha256=_text(row["approval_binding_sha256"]) or "",
                parameters_sha256=_text(row["parameters_sha256"]) or "",
                resource_version_sha256=_text(row["resource_version_sha256"], nullable=True),
                preview_sha256=_text(row["preview_sha256"]) or "",
                review_preview=preview,
                decision_id=_uuid(row["decision_id"], nullable=True),
                decision_session_binding_sha256=_text(
                    row["decision_session_binding_sha256"], nullable=True
                ),
                expires_at=_instant(row["expires_at"]) or datetime.min.replace(tzinfo=UTC),
                decided_at=_instant(row["decided_at"], nullable=True),
            )
        except ConnectedControlPlaneError:
            raise
        except Exception:
            raise ConnectedControlPlaneError("CONNECTED_PREVIEW_FAILED") from None

    async def list_approvals(self, *, owner_id: str) -> tuple[ConnectedApprovalView, ...]:
        rows = _list(
            await self._rpc(
                "connected_app_operator_list_approvals_v1", {"p_owner_id": owner_id}, read=True
            ),
            _APPROVAL_KEYS,
            maximum=50,
        )
        result = tuple([await self._approval(owner_id, row) for row in rows])
        if len({item.approval_id for item in result}) != len(result):
            raise ConnectedControlPlaneError("CONNECTED_RPC_SHAPE_INVALID")
        return result

    async def get_approval(
        self, *, owner_id: str, approval_id: str
    ) -> ConnectedApprovalView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_get_approval_v1",
                {"p_owner_id": owner_id, "p_approval_id": approval_id},
                read=True,
            ),
            _APPROVAL_KEYS,
        )
        return None if row is None else await self._approval(owner_id, row)

    async def decide_approval_once(self, command: ApprovalDecisionCommand) -> ConnectedApprovalView:
        row = _object(
            await self._rpc(
                "connected_app_operator_decide_approval_v1",
                {
                    "p_decision_id": command.decision_id,
                    "p_owner_id": command.owner_id,
                    "p_session_binding_sha256": command.session_binding_sha256,
                    "p_approval_id": command.approval_id,
                    "p_action_id": command.action_id,
                    "p_connection_id": command.connection_id,
                    "p_task_id": command.task_id,
                    "p_turn_id": command.turn_id,
                    "p_provider": command.provider.value,
                    "p_resource": command.resource.value,
                    "p_action": command.action.value,
                    "p_authorization_revision": command.authorization_revision,
                    "p_authorization_snapshot_sha256": command.authorization_snapshot_sha256,
                    "p_granted_scopes_sha256": command.granted_scopes_sha256,
                    "p_policy_version": command.policy_version,
                    "p_action_revision": command.action_revision,
                    "p_approval_binding_sha256": command.approval_binding_sha256,
                    "p_parameters_sha256": command.parameters_sha256,
                    "p_resource_version_sha256": command.resource_version_sha256,
                    "p_preview_sha256": command.preview_sha256,
                    "p_decision": command.decision.value,
                    "p_decided_at": command.decided_at.isoformat(),
                },
            ),
            _APPROVAL_KEYS,
        )
        return await self._approval(command.owner_id, row)

    async def readback_approval_decision(
        self, *, owner_id: str, approval_id: str, decision_id: str
    ) -> ConnectedApprovalView | None:
        row = _optional_object(
            await self._rpc(
                "connected_app_operator_read_approval_decision_v1",
                {
                    "p_owner_id": owner_id,
                    "p_approval_id": approval_id,
                    "p_decision_id": decision_id,
                },
                read=True,
            ),
            _APPROVAL_KEYS,
        )
        return None if row is None else await self._approval(owner_id, row)


def require_control_plane_protocol(value: object) -> None:
    """Runtime structural smoke used by production composition tests."""

    required = (
        "list_connections",
        "get_connection_authority",
        "start_oauth_once",
        "readback_oauth_start",
        "complete_oauth_callback",
        "deny_oauth_callback",
        "readback_oauth_callback",
        "disconnect_once",
        "readback_disconnect",
        "list_schedules",
        "get_schedule",
        "create_schedule_once",
        "readback_schedule_create",
        "transition_schedule_once",
        "readback_schedule_transition",
        "list_actions",
        "get_action",
        "list_approvals",
        "get_approval",
        "decide_approval_once",
        "readback_approval_decision",
    )
    if any(not callable(getattr(value, name, None)) for name in required):
        raise ConnectedAppServiceError("CONNECTED_CONTROL_PLANE_INVALID", 503)


def require_action_preparation_protocol(value: object) -> None:
    """Fail closed unless atomic preparation and its readback are composed."""

    if any(
        not callable(getattr(value, name, None))
        for name in ("prepare_action_once", "readback_action_preparation")
    ):
        raise ConnectedAppServiceError("CONNECTED_CONTROL_PLANE_INVALID", 503)
