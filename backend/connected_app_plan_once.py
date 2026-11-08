"""Durable, exactly-once model planning for connected mail and calendars."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import json
import re
from typing import Any, Protocol
from uuid import UUID, uuid5

from .connected_app_agent import (
    ConnectedOperatorDisposition,
    ConnectedOperatorPlanError,
    ConnectedOperatorPlanner,
    ConnectedOperatorPlanningContext,
    ConnectedOperatorPlanningResult,
)
from .connected_app_plan_vault import (
    ConnectedPlanEnvelopeRef,
    ConnectedPlanEnvelopeVault,
    ConnectedPlanVaultError,
    EncryptedConnectedPlanEnvelope,
)
from .connected_app_policy import ConnectorActionKind, ConnectorProvider, ConnectorResource
from .connected_app_service import ConnectedConnectionView


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PLAN_NAMESPACE = UUID("7b41b57b-e3bb-5f1e-b9f9-1388bf36c47f")
_PAYLOAD_NAMESPACE = UUID("932ec370-df80-54c8-a783-d91d3fe9bd26")
_INVOCATION_NAMESPACE = UUID("a8113f97-8ba3-5376-b4d7-05301eef84df")
_MAX_LIFETIME = timedelta(minutes=30)
_MODEL_LEASE = timedelta(seconds=45)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID") from None
    if canonical != value:
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
    return value


def _key_id(value: object) -> str:
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
    return value


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
    return value.astimezone(UTC)


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
    return parsed.astimezone(UTC)


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


class ConnectedPlanOnceError(RuntimeError):
    """Fixed, content-free durable planning failure."""

    _ALLOWED = frozenset(
        {
            "CONNECTED_PLAN_ONCE_BUSY",
            "CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN",
            "CONNECTED_PLAN_ONCE_FAILED",
            "CONNECTED_PLAN_ONCE_INVALID",
            "CONNECTED_PLAN_ONCE_MODEL_FAILED",
            "CONNECTED_PLAN_ONCE_RESULT_INVALID",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            code = "CONNECTED_PLAN_ONCE_FAILED"
        self.code = code
        super().__init__(code)


class ConnectedPlanBindingKey:
    """Dedicated secret for one chat-turn/planning-operation commitment."""

    __slots__ = ("_key", "key_id")

    def __init__(self, key_id: str, raw_key: bytes) -> None:
        self.key_id = _key_id(key_id)
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        self._key = raw_key

    @classmethod
    def from_base64(cls, key_id: str, encoded: str) -> ConnectedPlanBindingKey:
        if not isinstance(encoded, str):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID") from None
        return cls(key_id, raw)

    def __repr__(self) -> str:
        return f"ConnectedPlanBindingKey(key_id={self.key_id!r}, key='<redacted>')"

    def __reduce_ex__(self, _protocol: int):
        raise TypeError("connected plan binding key cannot be serialized")


class ConnectedPlanOperationState(StrEnum):
    RESERVED = "reserved"
    INVOKED = "invoked"
    SETTLED = "settled"
    FAILED = "failed"
    EFFECT_UNKNOWN = "effect_unknown"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedPlanOnceCommand:
    owner_id: str
    session_id: str = field(repr=False)
    chat_id: str
    message_id: str
    turn_id: str
    claim_token: str = field(repr=False)
    origin_session_binding_sha256: str = field(repr=False)
    request_binding_sha256: str = field(repr=False)
    planning_id: str
    planning_binding_key_id: str
    planning_binding_sha256: str = field(repr=False)
    payload_id: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "owner_id",
            "session_id",
            "chat_id",
            "message_id",
            "turn_id",
            "claim_token",
            "planning_id",
            "payload_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name)))
        for name in (
            "origin_session_binding_sha256",
            "request_binding_sha256",
            "planning_binding_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        object.__setattr__(
            self,
            "planning_binding_key_id",
            _key_id(self.planning_binding_key_id),
        )
        requested_at = _aware(self.requested_at)
        expires_at = _aware(self.expires_at)
        if expires_at <= requested_at or expires_at - requested_at > _MAX_LIFETIME:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        object.__setattr__(self, "requested_at", requested_at)
        object.__setattr__(self, "expires_at", expires_at)

    @property
    def invocation_id(self) -> str:
        return str(uuid5(_INVOCATION_NAMESPACE, self.planning_id))

    @classmethod
    def build(
        cls,
        *,
        binding_key: ConnectedPlanBindingKey,
        owner_id: str,
        session_id: str,
        chat_id: str,
        message_id: str,
        turn_id: str,
        claim_token: str,
        origin_session_binding_sha256: str,
        request_binding_sha256: str,
        requested_at: datetime,
        expires_at: datetime,
    ) -> ConnectedPlanOnceCommand:
        if type(binding_key) is not ConnectedPlanBindingKey:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        planning_id = str(uuid5(_PLAN_NAMESPACE, _uuid(turn_id)))
        payload_id = str(uuid5(_PAYLOAD_NAMESPACE, planning_id))
        values = {
            "version": "connected-plan-operation-binding-v1",
            "keyId": binding_key.key_id,
            "ownerId": _uuid(owner_id),
            "sessionId": _uuid(session_id),
            "chatId": _uuid(chat_id),
            "messageId": _uuid(message_id),
            "turnId": turn_id,
            "claimToken": _uuid(claim_token),
            "originSessionBindingSha256": _sha(origin_session_binding_sha256),
            "requestBindingSha256": _sha(request_binding_sha256),
            "planningId": planning_id,
            "payloadId": payload_id,
            "requestedAt": _aware(requested_at).isoformat(),
            "expiresAt": _aware(expires_at).isoformat(),
        }
        binding = hmac.new(binding_key._key, _canonical(values), hashlib.sha256).hexdigest()
        return cls(
            owner_id=owner_id,
            session_id=session_id,
            chat_id=chat_id,
            message_id=message_id,
            turn_id=turn_id,
            claim_token=claim_token,
            origin_session_binding_sha256=origin_session_binding_sha256,
            request_binding_sha256=request_binding_sha256,
            planning_id=planning_id,
            planning_binding_key_id=binding_key.key_id,
            planning_binding_sha256=binding,
            payload_id=payload_id,
            requested_at=requested_at,
            expires_at=expires_at,
        )

    def __repr__(self) -> str:
        return (
            "ConnectedPlanOnceCommand("
            f"planning_id={self.planning_id!r}, turn_id={self.turn_id!r}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedPlanOperationRecord:
    state: ConnectedPlanOperationState
    planning_id: str
    owner_id: str
    turn_id: str
    planning_binding_key_id: str
    planning_binding_sha256: str = field(repr=False)
    payload_id: str
    invocation_id: str | None
    invocation_expires_at: datetime | None
    disposition: ConnectedOperatorDisposition | None
    connection_id: str | None
    provider: ConnectorProvider | None
    resource: ConnectorResource | None
    action: ConnectorActionKind | None
    payload_commitment_key_id: str | None
    payload_sha256: str | None = field(repr=False)
    payload_reference_binding_sha256: str | None = field(repr=False)
    error_code: str | None
    requested_at: datetime
    expires_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.state, ConnectedPlanOperationState):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        for name in ("planning_id", "owner_id", "turn_id", "payload_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name)))
        object.__setattr__(
            self,
            "planning_binding_key_id",
            _key_id(self.planning_binding_key_id),
        )
        object.__setattr__(self, "planning_binding_sha256", _sha(self.planning_binding_sha256))
        if self.invocation_id is not None:
            object.__setattr__(self, "invocation_id", _uuid(self.invocation_id))
        if self.connection_id is not None:
            object.__setattr__(self, "connection_id", _uuid(self.connection_id))
        for name in ("requested_at", "expires_at", "updated_at"):
            object.__setattr__(self, name, _aware(getattr(self, name)))
        if self.invocation_expires_at is not None:
            object.__setattr__(
                self,
                "invocation_expires_at",
                _aware(self.invocation_expires_at),
            )
        if self.expires_at <= self.requested_at:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        invoked = self.state in {
            ConnectedPlanOperationState.INVOKED,
            ConnectedPlanOperationState.SETTLED,
            ConnectedPlanOperationState.FAILED,
            ConnectedPlanOperationState.EFFECT_UNKNOWN,
        }
        if invoked != (self.invocation_id is not None):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if invoked != (self.invocation_expires_at is not None):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        settled = self.state is ConnectedPlanOperationState.SETTLED
        reference_values = (
            self.payload_commitment_key_id,
            self.payload_sha256,
            self.payload_reference_binding_sha256,
            self.disposition,
        )
        if settled != all(value is not None for value in reference_values):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if self.payload_commitment_key_id is not None:
            object.__setattr__(
                self,
                "payload_commitment_key_id",
                _key_id(self.payload_commitment_key_id),
            )
            object.__setattr__(self, "payload_sha256", _sha(self.payload_sha256))
            object.__setattr__(
                self,
                "payload_reference_binding_sha256",
                _sha(self.payload_reference_binding_sha256),
            )
        executable = self.disposition in {
            ConnectedOperatorDisposition.ACTION,
            ConnectedOperatorDisposition.SCHEDULE,
        }
        typed = (self.connection_id, self.provider, self.resource, self.action)
        if settled and executable != all(value is not None for value in typed):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if settled and not executable and any(value is not None for value in typed):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if self.error_code is not None and (
            not isinstance(self.error_code, str)
            or not re.fullmatch(r"[A-Z0-9_]{1,80}", self.error_code)
        ):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if (
            self.state
            in {
                ConnectedPlanOperationState.FAILED,
                ConnectedPlanOperationState.EFFECT_UNKNOWN,
            }
        ) != (self.error_code is not None):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")

    def __repr__(self) -> str:
        return (
            "ConnectedPlanOperationRecord("
            f"state={self.state.value!r}, planning_id={self.planning_id!r}, "
            "content='<encrypted>')"
        )


@dataclass(frozen=True, slots=True)
class ConnectedPlanInvocationClaim:
    record: ConnectedPlanOperationRecord
    invoke_permitted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.record, ConnectedPlanOperationRecord):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if type(self.invoke_permitted) is not bool:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if self.record.state is not ConnectedPlanOperationState.INVOKED:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")


class ConnectedPlanControlPlane(Protocol):
    async def begin(self, command: ConnectedPlanOnceCommand) -> ConnectedPlanOperationRecord: ...

    async def mark_invoked(
        self, command: ConnectedPlanOnceCommand
    ) -> ConnectedPlanInvocationClaim: ...

    async def settle(
        self,
        command: ConnectedPlanOnceCommand,
        *,
        reference: ConnectedPlanEnvelopeRef,
        result: ConnectedOperatorPlanningResult,
    ) -> ConnectedPlanOperationRecord: ...

    async def fail(
        self, command: ConnectedPlanOnceCommand, *, error_code: str
    ) -> ConnectedPlanOperationRecord: ...

    async def mark_effect_unknown(
        self, command: ConnectedPlanOnceCommand
    ) -> ConnectedPlanOperationRecord: ...

    async def read(
        self, command: ConnectedPlanOnceCommand
    ) -> ConnectedPlanOperationRecord | None: ...


class ConnectedPlanRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


_RECORD_KEYS = frozenset(
    {
        "state",
        "planning_id",
        "owner_id",
        "turn_id",
        "planning_binding_key_id",
        "planning_binding_sha256",
        "payload_id",
        "invocation_id",
        "invocation_expires_at",
        "disposition",
        "connection_id",
        "provider",
        "resource",
        "action",
        "payload_commitment_key_id",
        "payload_sha256",
        "payload_reference_binding_sha256",
        "error_code",
        "requested_at",
        "expires_at",
        "updated_at",
    }
)


def _enum_or_none(enum_type, value):
    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID") from None


def _record(value: object) -> ConnectedPlanOperationRecord:
    if type(value) is not dict or set(value) != _RECORD_KEYS:
        raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
    row = value
    return ConnectedPlanOperationRecord(
        state=ConnectedPlanOperationState(row["state"]),
        planning_id=_uuid(row["planning_id"]),
        owner_id=_uuid(row["owner_id"]),
        turn_id=_uuid(row["turn_id"]),
        planning_binding_key_id=_key_id(row["planning_binding_key_id"]),
        planning_binding_sha256=_sha(row["planning_binding_sha256"]),
        payload_id=_uuid(row["payload_id"]),
        invocation_id=None if row["invocation_id"] is None else _uuid(row["invocation_id"]),
        invocation_expires_at=(
            None if row["invocation_expires_at"] is None else _time(row["invocation_expires_at"])
        ),
        disposition=_enum_or_none(ConnectedOperatorDisposition, row["disposition"]),
        connection_id=(None if row["connection_id"] is None else _uuid(row["connection_id"])),
        provider=_enum_or_none(ConnectorProvider, row["provider"]),
        resource=_enum_or_none(ConnectorResource, row["resource"]),
        action=_enum_or_none(ConnectorActionKind, row["action"]),
        payload_commitment_key_id=row["payload_commitment_key_id"],
        payload_sha256=row["payload_sha256"],
        payload_reference_binding_sha256=row["payload_reference_binding_sha256"],
        error_code=row["error_code"],
        requested_at=_time(row["requested_at"]),
        expires_at=_time(row["expires_at"]),
        updated_at=_time(row["updated_at"]),
    )


class SupabaseConnectedPlanControlPlane:
    """Strict service-role adapter; mutation RPCs are never transient-retried."""

    def __init__(self, client: ConnectedPlanRPC) -> None:
        if not callable(getattr(client, "rpc", None)):
            raise TypeError("connected plan RPC client is invalid")
        self._client = client

    @staticmethod
    def _bindings(command: ConnectedPlanOnceCommand) -> dict[str, object]:
        if type(command) is not ConnectedPlanOnceCommand:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        return {
            "p_owner_id": command.owner_id,
            "p_session_id": command.session_id,
            "p_chat_id": command.chat_id,
            "p_message_id": command.message_id,
            "p_turn_id": command.turn_id,
            "p_claim_token": command.claim_token,
            "p_origin_session_binding_sha256": command.origin_session_binding_sha256,
            "p_request_binding_sha256": command.request_binding_sha256,
            "p_planning_id": command.planning_id,
            "p_planning_binding_key_id": command.planning_binding_key_id,
            "p_planning_binding_sha256": command.planning_binding_sha256,
            "p_payload_id": command.payload_id,
            "p_requested_at": command.requested_at.isoformat(),
            "p_expires_at": command.expires_at.isoformat(),
        }

    @staticmethod
    def _one(value: object) -> object:
        if isinstance(value, list):
            if len(value) != 1:
                raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
            return value[0]
        return value

    async def _call(self, name: str, payload: dict[str, object]) -> object:
        try:
            return self._one(await self._client.rpc(name, payload, retry_transient=False))
        except ConnectedPlanOnceError:
            raise
        except Exception:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_FAILED") from None

    async def begin(self, command: ConnectedPlanOnceCommand) -> ConnectedPlanOperationRecord:
        return _record(await self._call("connected_plan_begin_v1", self._bindings(command)))

    async def mark_invoked(self, command: ConnectedPlanOnceCommand) -> ConnectedPlanInvocationClaim:
        payload = self._bindings(command)
        payload["p_invocation_id"] = command.invocation_id
        value = await self._call("connected_plan_mark_invoked_v1", payload)
        if type(value) is not dict or set(value) != {"record", "invoke_permitted"}:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        return ConnectedPlanInvocationClaim(
            record=_record(value["record"]),
            invoke_permitted=value["invoke_permitted"],
        )

    async def settle(
        self,
        command: ConnectedPlanOnceCommand,
        *,
        reference: ConnectedPlanEnvelopeRef,
        result: ConnectedOperatorPlanningResult,
    ) -> ConnectedPlanOperationRecord:
        if not isinstance(reference, ConnectedPlanEnvelopeRef) or not isinstance(
            result, ConnectedOperatorPlanningResult
        ):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        plan = result.plan
        payload = self._bindings(command)
        payload.update(
            {
                "p_invocation_id": command.invocation_id,
                "p_disposition": result.disposition.value,
                "p_connection_id": None if plan is None else plan.connection_id,
                "p_provider": None if plan is None else plan.provider.value,
                "p_resource": None if plan is None else plan.resource.value,
                "p_action": None if plan is None else plan.action.value,
                "p_payload_commitment_key_id": reference.commitment_key_id,
                "p_payload_sha256": reference.payload_sha256,
                "p_payload_reference_binding_sha256": reference.binding_sha256,
            }
        )
        return _record(await self._call("connected_plan_settle_v1", payload))

    async def fail(
        self, command: ConnectedPlanOnceCommand, *, error_code: str
    ) -> ConnectedPlanOperationRecord:
        if not isinstance(error_code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", error_code):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        payload = self._bindings(command)
        payload.update({"p_invocation_id": command.invocation_id, "p_error_code": error_code})
        return _record(await self._call("connected_plan_fail_v1", payload))

    async def mark_effect_unknown(
        self, command: ConnectedPlanOnceCommand
    ) -> ConnectedPlanOperationRecord:
        payload = self._bindings(command)
        payload["p_invocation_id"] = command.invocation_id
        return _record(await self._call("connected_plan_mark_unknown_v1", payload))

    async def read(self, command: ConnectedPlanOnceCommand) -> ConnectedPlanOperationRecord | None:
        try:
            value = self._one(
                await self._client.rpc(
                    "connected_plan_read_v1",
                    self._bindings(command),
                    retry_transient=False,
                )
            )
        except Exception:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_FAILED") from None
        return None if value is None else _record(value)


class SupabaseConnectedPlanEnvelopeStore:
    """Strict encrypted-record adapter with response-loss readback."""

    def __init__(self, client: ConnectedPlanRPC) -> None:
        if not callable(getattr(client, "rpc", None)):
            raise TypeError("connected plan RPC client is invalid")
        self._client = client

    @staticmethod
    def _reference_payload(reference: ConnectedPlanEnvelopeRef) -> dict[str, object]:
        return {
            "p_owner_id": reference.owner_id,
            "p_turn_id": reference.turn_id,
            "p_planning_id": reference.planning_id,
            "p_planning_binding_sha256": reference.planning_binding_sha256,
            "p_payload_id": reference.payload_id,
        }

    @staticmethod
    def _decode(value: object) -> EncryptedConnectedPlanEnvelope | None:
        if value is None:
            return None
        if isinstance(value, list):
            if len(value) != 1:
                raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT")
            value = value[0]
        keys = {
            "payload_id",
            "owner_id",
            "turn_id",
            "planning_id",
            "planning_binding_sha256",
            "commitment_key_id",
            "payload_sha256",
            "created_at",
            "expires_at",
            "key_id",
            "wrapped_key_nonce",
            "wrapped_key_ciphertext",
            "payload_nonce",
            "payload_ciphertext",
            "record_binding_sha256",
        }
        if type(value) is not dict or set(value) != keys:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT")
        return EncryptedConnectedPlanEnvelope(
            reference=ConnectedPlanEnvelopeRef(
                payload_id=value["payload_id"],
                owner_id=value["owner_id"],
                turn_id=value["turn_id"],
                planning_id=value["planning_id"],
                planning_binding_sha256=value["planning_binding_sha256"],
                commitment_key_id=value["commitment_key_id"],
                payload_sha256=value["payload_sha256"],
                created_at=_time(value["created_at"]),
                expires_at=_time(value["expires_at"]),
            ),
            key_id=value["key_id"],
            wrapped_key_nonce=value["wrapped_key_nonce"],
            wrapped_key_ciphertext=value["wrapped_key_ciphertext"],
            payload_nonce=value["payload_nonce"],
            payload_ciphertext=value["payload_ciphertext"],
            record_binding_sha256=value["record_binding_sha256"],
        )

    async def read_exact(
        self,
        *,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        payload_id: str,
    ) -> EncryptedConnectedPlanEnvelope | None:
        try:
            value = await self._client.rpc(
                "connected_plan_envelope_read_v1",
                {
                    "p_owner_id": owner_id,
                    "p_turn_id": turn_id,
                    "p_planning_id": planning_id,
                    "p_planning_binding_sha256": planning_binding_sha256,
                    "p_payload_id": payload_id,
                },
                retry_transient=False,
            )
            return self._decode(value)
        except ConnectedPlanVaultError:
            raise
        except Exception:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_STORE_FAILED") from None

    async def put_once(
        self, record: EncryptedConnectedPlanEnvelope
    ) -> EncryptedConnectedPlanEnvelope | None:
        if not isinstance(record, EncryptedConnectedPlanEnvelope):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
        ref = record.reference
        payload = self._reference_payload(ref)
        payload.update(
            {
                "p_commitment_key_id": ref.commitment_key_id,
                "p_payload_sha256": ref.payload_sha256,
                "p_reference_binding_sha256": ref.binding_sha256,
                "p_created_at": ref.created_at.isoformat(),
                "p_expires_at": ref.expires_at.isoformat(),
                "p_key_id": record.key_id,
                "p_wrapped_key_nonce": record.wrapped_key_nonce,
                "p_wrapped_key_ciphertext": record.wrapped_key_ciphertext,
                "p_payload_nonce": record.payload_nonce,
                "p_payload_ciphertext": record.payload_ciphertext,
                "p_record_binding_sha256": record.record_binding_sha256,
            }
        )
        try:
            value = await self._client.rpc(
                "connected_plan_envelope_put_v1",
                payload,
                retry_transient=False,
            )
            decoded = self._decode(value)
        except Exception:
            decoded = await self.read_exact(
                owner_id=ref.owner_id,
                turn_id=ref.turn_id,
                planning_id=ref.planning_id,
                planning_binding_sha256=ref.planning_binding_sha256,
                payload_id=ref.payload_id,
            )
        return decoded

    async def delete_once(
        self,
        *,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        payload_id: str,
    ) -> bool:
        try:
            value = await self._client.rpc(
                "connected_plan_envelope_delete_v1",
                {
                    "p_owner_id": owner_id,
                    "p_turn_id": turn_id,
                    "p_planning_id": planning_id,
                    "p_planning_binding_sha256": planning_binding_sha256,
                    "p_payload_id": payload_id,
                },
                retry_transient=False,
            )
        except Exception:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_STORE_FAILED") from None
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if type(value) is not bool:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT")
        return value


class ConnectedPlanOnceCoordinator:
    """One model attempt, durable encrypted readback, no automatic duplicate."""

    def __init__(
        self,
        *,
        planner: ConnectedOperatorPlanner,
        control_plane: ConnectedPlanControlPlane,
        vault: ConnectedPlanEnvelopeVault,
        now=lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(planner, ConnectedOperatorPlanner):
            raise TypeError("connected planner is invalid")
        if any(
            not callable(getattr(control_plane, method, None))
            for method in (
                "begin",
                "mark_invoked",
                "settle",
                "fail",
                "mark_effect_unknown",
                "read",
            )
        ):
            raise TypeError("connected plan control plane is invalid")
        if not isinstance(vault, ConnectedPlanEnvelopeVault):
            raise TypeError("connected plan vault is invalid")
        if not callable(now):
            raise TypeError("connected plan clock is invalid")
        self._planner = planner
        self._control = control_plane
        self._vault = vault
        self._now = now

    @staticmethod
    def _envelope(raw: str) -> dict[str, object]:
        if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > 48_000:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        return {"version": "connected-plan-output-v1", "raw": raw}

    @staticmethod
    def _raw(value: object) -> str:
        if (
            type(value) is not dict
            or set(value) != {"version", "raw"}
            or value["version"] != "connected-plan-output-v1"
            or not isinstance(value["raw"], str)
            or not value["raw"]
            or len(value["raw"].encode("utf-8")) > 48_000
        ):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        return value["raw"]

    @staticmethod
    def _matches(
        command: ConnectedPlanOnceCommand,
        record: ConnectedPlanOperationRecord,
    ) -> bool:
        return bool(
            record.planning_id == command.planning_id
            and record.owner_id == command.owner_id
            and record.turn_id == command.turn_id
            and record.planning_binding_key_id == command.planning_binding_key_id
            and hmac.compare_digest(
                record.planning_binding_sha256,
                command.planning_binding_sha256,
            )
            and record.payload_id == command.payload_id
            and record.requested_at == command.requested_at
            and record.expires_at == command.expires_at
        )

    async def _readback(self, command: ConnectedPlanOnceCommand):
        try:
            record = await self._control.read(command)
        except Exception:
            return None
        if record is not None and not self._matches(command, record):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        return record

    async def _open_and_parse(
        self,
        command: ConnectedPlanOnceCommand,
        context: ConnectedOperatorPlanningContext,
    ) -> tuple[ConnectedPlanEnvelopeRef, ConnectedOperatorPlanningResult]:
        reference, value = await self._vault.open_json(
            owner_id=command.owner_id,
            turn_id=command.turn_id,
            planning_id=command.planning_id,
            planning_binding_sha256=command.planning_binding_sha256,
            payload_id=command.payload_id,
            now=_aware(self._now()),
        )
        return reference, self._planner.parse(context, self._raw(value))

    async def _settle(
        self,
        command: ConnectedPlanOnceCommand,
        *,
        reference: ConnectedPlanEnvelopeRef,
        result: ConnectedOperatorPlanningResult,
    ) -> ConnectedPlanOperationRecord:
        try:
            record = await self._control.settle(
                command,
                reference=reference,
                result=result,
            )
        except Exception:
            record = await self._readback(command)
        if (
            record is None
            or not self._matches(command, record)
            or record.state is not ConnectedPlanOperationState.SETTLED
            or record.disposition is not result.disposition
            or record.payload_commitment_key_id != reference.commitment_key_id
            or record.payload_sha256 != reference.payload_sha256
            or record.payload_reference_binding_sha256 != reference.binding_sha256
        ):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN")
        return record

    async def plan_once(
        self,
        command: ConnectedPlanOnceCommand,
        *,
        message: str,
        connections: tuple[ConnectedConnectionView, ...],
        user_time_zone: str,
    ) -> ConnectedOperatorPlanningResult:
        if type(command) is not ConnectedPlanOnceCommand:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_INVALID")
        prepared = self._planner.prepare(
            owner_id=command.owner_id,
            message=message,
            connections=connections,
            user_time_zone=user_time_zone,
        )
        if isinstance(prepared, ConnectedOperatorPlanningResult):
            return prepared
        context = prepared
        try:
            record = await self._control.begin(command)
        except Exception:
            record = await self._readback(command)
        if record is None or not self._matches(command, record):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_FAILED")
        if record.state is ConnectedPlanOperationState.SETTLED:
            reference, result = await self._open_and_parse(command, context)
            if (
                record.disposition is not result.disposition
                or record.payload_sha256 != reference.payload_sha256
                or record.payload_reference_binding_sha256 != reference.binding_sha256
            ):
                raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
            return result
        if record.state is ConnectedPlanOperationState.FAILED:
            code = (
                "CONNECTED_PLAN_ONCE_RESULT_INVALID"
                if record.error_code == "PLAN_INVALID"
                else "CONNECTED_PLAN_ONCE_MODEL_FAILED"
            )
            raise ConnectedPlanOnceError(code)
        if record.state is ConnectedPlanOperationState.EFFECT_UNKNOWN:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN")
        if record.state is ConnectedPlanOperationState.INVOKED:
            try:
                reference, result = await self._open_and_parse(command, context)
            except ConnectedPlanVaultError as exc:
                if exc.code != "CONNECTED_PLAN_VAULT_NOT_FOUND":
                    raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN") from None
                if record.invocation_expires_at and record.invocation_expires_at > _aware(
                    self._now()
                ):
                    raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_BUSY") from None
                try:
                    await self._control.mark_effect_unknown(command)
                except Exception:
                    pass
                raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN") from None
            await self._settle(command, reference=reference, result=result)
            return result
        try:
            invocation = await self._control.mark_invoked(command)
        except Exception:
            invoked = await self._readback(command)
            if invoked is None:
                raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_FAILED") from None
            invocation = ConnectedPlanInvocationClaim(invoked, False)
        if not self._matches(command, invocation.record):
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID")
        if not invocation.invoke_permitted:
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_BUSY")
        try:
            raw = await self._planner.complete(context)
        except Exception:
            try:
                await self._control.mark_effect_unknown(command)
            except Exception:
                pass
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN") from None
        try:
            reference = await self._vault.seal_json(
                payload_id=command.payload_id,
                owner_id=command.owner_id,
                turn_id=command.turn_id,
                planning_id=command.planning_id,
                planning_binding_sha256=command.planning_binding_sha256,
                value=self._envelope(raw),
                created_at=command.requested_at,
                expires_at=command.expires_at,
            )
        except Exception:
            try:
                reference, value = await self._vault.open_json(
                    owner_id=command.owner_id,
                    turn_id=command.turn_id,
                    planning_id=command.planning_id,
                    planning_binding_sha256=command.planning_binding_sha256,
                    payload_id=command.payload_id,
                    now=_aware(self._now()),
                )
                raw = self._raw(value)
            except Exception:
                try:
                    await self._control.mark_effect_unknown(command)
                except Exception:
                    pass
                raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN") from None
        try:
            result = self._planner.parse(context, raw)
        except ConnectedOperatorPlanError:
            try:
                await self._control.fail(command, error_code="PLAN_INVALID")
            except Exception:
                pass
            raise ConnectedPlanOnceError("CONNECTED_PLAN_ONCE_RESULT_INVALID") from None
        await self._settle(command, reference=reference, result=result)
        return result

    def __repr__(self) -> str:
        return "ConnectedPlanOnceCoordinator(dependencies='<redacted>')"
