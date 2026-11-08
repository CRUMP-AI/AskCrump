"""Encrypted, restart-safe connected schedule adapters.

Only the settled server-side chat plan can create a recurring action.  The
browser never supplies a payload handle.  The typed provider request is kept
in dedicated envelope-encrypted custody, while the scheduler sees only exact
content-free bindings and a fresh per-occurrence task grant.  Every mutating
occurrence still requires a separate, exact, short-lived approval.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Callable, Protocol
from uuid import UUID, uuid5

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .connected_app_agent import (
    ConnectedOperatorDisposition,
    ConnectedOperatorPlan,
)
from .connected_app_chat_operator import (
    ConnectedOperatorActionContext,
    ConnectedOperatorScheduleResult,
)
from .connected_app_payload_envelope import (
    ConnectedActionPayloadEnvelope,
    expected_resource_version,
)
from .connected_app_plan_once import (
    ConnectedPlanBindingKey,
    ConnectedPlanControlPlane,
    ConnectedPlanOnceCommand,
    ConnectedPlanOperationRecord,
    ConnectedPlanOperationState,
)
from .connected_app_policy import (
    ConnectedActionIntent,
    ConnectedActionPolicy,
    ConnectedApprovalEvidence,
    ConnectedTaskGrant,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from .connected_app_runtime import ConnectedActionInvocation
from .connected_app_scheduler import (
    ConnectedScheduleClaim,
    ConnectedScheduleCompletion,
    ConnectedScheduleFinish,
    ConnectedScheduleRunOutcome,
    ConnectedScheduledRun,
    ConnectedSchedulerError,
)
from .connected_app_service import ConnectedConnectionAuthorityView


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PLAINTEXT_BYTES = 64 * 1024
_IDENTITY_NAMESPACE = UUID("4d05f225-c5f2-5599-afb3-41f5b2661fc4")
_ACTION_NAMESPACE = UUID("728462e9-ec66-5cf4-8c3b-3de75490d2f5")
_OCCURRENCE_NAMESPACE = UUID("16ea52f6-795e-5aa3-875f-566bdd766a94")
_OCCURRENCE_ACTION_NAMESPACE = UUID("884b4769-a1a8-5099-ae05-b1555b0414e7")
_OCCURRENCE_APPROVAL_NAMESPACE = UUID("95f103a5-d96a-5b98-ac56-1023ba3b654c")


class ConnectedScheduleAdapterError(RuntimeError):
    _CODES = frozenset(
        {
            "CONNECTED_SCHEDULE_AUTHORITY_CHANGED",
            "CONNECTED_SCHEDULE_CUSTODY_CORRUPT",
            "CONNECTED_SCHEDULE_CUSTODY_FAILED",
            "CONNECTED_SCHEDULE_CUSTODY_INVALID",
            "CONNECTED_SCHEDULE_CUSTODY_KEY_UNAVAILABLE",
            "CONNECTED_SCHEDULE_RESULT_INVALID",
            "CONNECTED_SCHEDULE_STAGE_FAILED",
            "CONNECTED_SCHEDULE_STAGE_INVALID",
            "CONNECTED_SCHEDULE_TEMPLATE_NOT_FOUND",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code if code in self._CODES else "CONNECTED_SCHEDULE_STAGE_FAILED"
        self.retryable = bool(retryable)
        super().__init__(self.code)


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_INVALID") from None
    if canonical != value:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_INVALID")
    return value


def _sha(value: object, name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_INVALID")
    return value


def _time(value: object, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and 1 <= len(value) <= 64:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID") from None
    else:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
    return parsed.astimezone(UTC)


def _canonical(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID") from None
    if not encoded or len(encoded) > _MAX_PLAINTEXT_BYTES:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
    return encoded


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: object, name: str, *, minimum: int, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > maximum * 2:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (TypeError, ValueError):
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT") from None
    if not minimum <= len(decoded) <= maximum or _b64(decoded) != value:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT")
    return decoded


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleTemplateKey:
    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("schedule template key ID is invalid")
        if type(self.secret) is not bytes or len(self.secret) != 32:
            raise ValueError("schedule template key must contain exactly 32 bytes")

    def __repr__(self) -> str:
        return f"ConnectedScheduleTemplateKey(key_id={self.key_id!r}, secret='<redacted>')"

    def __reduce_ex__(self, _protocol: int):
        raise TypeError("schedule template key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleTemplateCommitmentKey:
    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("schedule commitment key ID is invalid")
        if type(self.secret) is not bytes or len(self.secret) != 32:
            raise ValueError("schedule commitment key must contain exactly 32 bytes")

    def __repr__(self) -> str:
        return (
            f"ConnectedScheduleTemplateCommitmentKey(key_id={self.key_id!r}, "
            "secret='<redacted>')"
        )

    def __reduce_ex__(self, _protocol: int):
        raise TypeError("schedule commitment key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleTemplateReference:
    template_id: str
    schedule_id: str
    owner_id: str
    turn_id: str
    connection_id: str
    task_id: str
    plan_payload_id: str
    plan_reference_binding_sha256: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    commitment_key_id: str
    parameters_sha256: str = field(repr=False)
    resource_version_sha256: str | None = field(default=None, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for name in (
            "template_id",
            "schedule_id",
            "owner_id",
            "turn_id",
            "connection_id",
            "task_id",
            "plan_payload_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        for name in (
            "plan_reference_binding_sha256",
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
            "parameters_sha256",
        ):
            _sha(getattr(self, name), name)
        _sha(self.resource_version_sha256, "resource_version_sha256", nullable=True)
        if not isinstance(self.provider, ConnectorProvider) or not isinstance(
            self.resource, ConnectorResource
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        if not isinstance(self.action, ConnectorActionKind):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        if ConnectedActionPolicy.requirement(self.action).resource is not self.resource:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        if not isinstance(self.commitment_key_id, str) or not _KEY_ID.fullmatch(
            self.commitment_key_id
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        object.__setattr__(self, "created_at", _time(self.created_at, "created_at"))

    @property
    def binding_sha256(self) -> str:
        return _hash(
            {
                "version": "connected-schedule-template-reference-v1",
                "templateId": self.template_id,
                "scheduleId": self.schedule_id,
                "ownerId": self.owner_id,
                "turnId": self.turn_id,
                "connectionId": self.connection_id,
                "taskId": self.task_id,
                "planPayloadId": self.plan_payload_id,
                "planReferenceBindingSha256": self.plan_reference_binding_sha256,
                "provider": self.provider.value,
                "resource": self.resource.value,
                "action": self.action.value,
                "authorizationRevision": self.authorization_revision,
                "authorizationSnapshotSha256": self.authorization_snapshot_sha256,
                "grantedActionsSha256": self.granted_actions_sha256,
                "grantedScopesSha256": self.granted_scopes_sha256,
                "commitmentKeyId": self.commitment_key_id,
                "parametersSha256": self.parameters_sha256,
                "resourceVersionSha256": self.resource_version_sha256,
                "createdAt": self.created_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "ConnectedScheduleTemplateReference("
            f"template_id={self.template_id!r}, schedule_id={self.schedule_id!r}, "
            "content='<encrypted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedConnectedScheduleTemplate:
    reference: ConnectedScheduleTemplateReference
    key_id: str
    wrapped_key_nonce: str = field(repr=False)
    wrapped_key_ciphertext: str = field(repr=False)
    payload_nonce: str = field(repr=False)
    payload_ciphertext: str = field(repr=False)
    record_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ConnectedScheduleTemplateReference):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        _unb64(self.wrapped_key_nonce, "wrapped_key_nonce", minimum=12, maximum=12)
        _unb64(
            self.wrapped_key_ciphertext,
            "wrapped_key_ciphertext",
            minimum=48,
            maximum=48,
        )
        _unb64(self.payload_nonce, "payload_nonce", minimum=12, maximum=12)
        _unb64(
            self.payload_ciphertext,
            "payload_ciphertext",
            minimum=17,
            maximum=_MAX_PLAINTEXT_BYTES + 16,
        )
        _sha(self.record_binding_sha256, "record_binding_sha256")
        if not hmac.compare_digest(
            self.record_binding_sha256, self.expected_record_binding_sha256
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT")

    @property
    def expected_record_binding_sha256(self) -> str:
        return _hash(
            {
                "version": "connected-schedule-template-record-v1",
                "referenceBindingSha256": self.reference.binding_sha256,
                "keyId": self.key_id,
                "wrappedKeyNonce": self.wrapped_key_nonce,
                "wrappedKeyCiphertext": self.wrapped_key_ciphertext,
                "payloadNonce": self.payload_nonce,
                "payloadCiphertext": self.payload_ciphertext,
            }
        )

    def __repr__(self) -> str:
        return (
            "EncryptedConnectedScheduleTemplate("
            f"template_id={self.reference.template_id!r}, ciphertext='<redacted>')"
        )


class ConnectedScheduleTemplateVault:
    """Process-local keys for long-lived, database-custodied templates."""

    def __init__(
        self,
        *,
        primary_key: ConnectedScheduleTemplateKey,
        commitment_key: ConnectedScheduleTemplateCommitmentKey,
        decryption_keys: tuple[ConnectedScheduleTemplateKey, ...] = (),
    ) -> None:
        if type(primary_key) is not ConnectedScheduleTemplateKey or type(
            commitment_key
        ) is not ConnectedScheduleTemplateCommitmentKey:
            raise TypeError("schedule template key is invalid")
        keys = (primary_key, *decryption_keys)
        if any(type(item) is not ConnectedScheduleTemplateKey for item in keys):
            raise TypeError("schedule template key ring is invalid")
        if len({item.key_id for item in keys}) != len(keys):
            raise ValueError("schedule template key IDs must be unique")
        self._primary = primary_key
        self._commitment = commitment_key
        self._keys = {item.key_id: item for item in keys}

    @staticmethod
    def _envelope(
        *,
        schedule_id: str,
        turn_id: str,
        plan_payload_id: str,
        plan_reference_binding_sha256: str,
        action_payload: ConnectedActionPayloadEnvelope,
    ) -> dict[str, object]:
        return {
            "version": "connected-schedule-template-envelope-v1",
            "scheduleId": schedule_id,
            "turnId": turn_id,
            "planPayloadId": plan_payload_id,
            "planReferenceBindingSha256": plan_reference_binding_sha256,
            "actionPayload": action_payload.to_value(),
        }

    def prepare(
        self,
        *,
        template_id: str,
        schedule_id: str,
        owner_id: str,
        turn_id: str,
        connection_id: str,
        task_id: str,
        plan_payload_id: str,
        plan_reference_binding_sha256: str,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        action: ConnectorActionKind,
        authorization_revision: int,
        authorization_snapshot_sha256: str,
        granted_actions_sha256: str,
        granted_scopes_sha256: str,
        request: object,
        created_at: datetime,
    ) -> EncryptedConnectedScheduleTemplate:
        action_payload = ConnectedActionPayloadEnvelope.build(action=action, request=request)
        envelope = self._envelope(
            schedule_id=_uuid(schedule_id, "schedule_id"),
            turn_id=_uuid(turn_id, "turn_id"),
            plan_payload_id=_uuid(plan_payload_id, "plan_payload_id"),
            plan_reference_binding_sha256=str(
                _sha(plan_reference_binding_sha256, "plan_reference_binding_sha256")
            ),
            action_payload=action_payload,
        )
        plaintext = _canonical(envelope)
        parameters_sha256 = hmac.new(
            self._commitment.secret,
            b"connected-schedule-template-commitment-v1\x00" + plaintext,
            hashlib.sha256,
        ).hexdigest()
        expected_version = expected_resource_version(action_payload.request)
        resource_version_sha256 = (
            None
            if expected_version is None
            else hashlib.sha256(expected_version.encode("utf-8")).hexdigest()
        )
        reference = ConnectedScheduleTemplateReference(
            template_id=template_id,
            schedule_id=schedule_id,
            owner_id=owner_id,
            turn_id=turn_id,
            connection_id=connection_id,
            task_id=task_id,
            plan_payload_id=plan_payload_id,
            plan_reference_binding_sha256=plan_reference_binding_sha256,
            provider=provider,
            resource=resource,
            action=action,
            authorization_revision=authorization_revision,
            authorization_snapshot_sha256=authorization_snapshot_sha256,
            granted_actions_sha256=granted_actions_sha256,
            granted_scopes_sha256=granted_scopes_sha256,
            commitment_key_id=self._commitment.key_id,
            parameters_sha256=parameters_sha256,
            resource_version_sha256=resource_version_sha256,
            created_at=created_at,
        )
        aad = _canonical(
            {
                "version": "connected-schedule-template-aad-v1",
                "referenceBindingSha256": reference.binding_sha256,
                "keyId": self._primary.key_id,
            }
        )
        data_key = secrets.token_bytes(32)
        wrap_nonce = secrets.token_bytes(12)
        payload_nonce = secrets.token_bytes(12)
        wrapped = AESGCM(self._primary.secret).encrypt(wrap_nonce, data_key, aad)
        ciphertext = AESGCM(data_key).encrypt(payload_nonce, plaintext, aad)
        provisional = EncryptedConnectedScheduleTemplate.__new__(
            EncryptedConnectedScheduleTemplate
        )
        object.__setattr__(provisional, "reference", reference)
        object.__setattr__(provisional, "key_id", self._primary.key_id)
        object.__setattr__(provisional, "wrapped_key_nonce", _b64(wrap_nonce))
        object.__setattr__(provisional, "wrapped_key_ciphertext", _b64(wrapped))
        object.__setattr__(provisional, "payload_nonce", _b64(payload_nonce))
        object.__setattr__(provisional, "payload_ciphertext", _b64(ciphertext))
        object.__setattr__(provisional, "record_binding_sha256", "0" * 64)
        binding = provisional.expected_record_binding_sha256
        return EncryptedConnectedScheduleTemplate(
            reference=reference,
            key_id=self._primary.key_id,
            wrapped_key_nonce=_b64(wrap_nonce),
            wrapped_key_ciphertext=_b64(wrapped),
            payload_nonce=_b64(payload_nonce),
            payload_ciphertext=_b64(ciphertext),
            record_binding_sha256=binding,
        )

    def open(self, record: EncryptedConnectedScheduleTemplate) -> ConnectedActionPayloadEnvelope:
        if type(record) is not EncryptedConnectedScheduleTemplate:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_INVALID")
        key = self._keys.get(record.key_id)
        if key is None:
            raise ConnectedScheduleAdapterError(
                "CONNECTED_SCHEDULE_CUSTODY_KEY_UNAVAILABLE"
            )
        aad = _canonical(
            {
                "version": "connected-schedule-template-aad-v1",
                "referenceBindingSha256": record.reference.binding_sha256,
                "keyId": record.key_id,
            }
        )
        try:
            data_key = AESGCM(key.secret).decrypt(
                _unb64(record.wrapped_key_nonce, "wrapped_key_nonce", minimum=12, maximum=12),
                _unb64(
                    record.wrapped_key_ciphertext,
                    "wrapped_key_ciphertext",
                    minimum=48,
                    maximum=48,
                ),
                aad,
            )
            plaintext = AESGCM(data_key).decrypt(
                _unb64(record.payload_nonce, "payload_nonce", minimum=12, maximum=12),
                _unb64(
                    record.payload_ciphertext,
                    "payload_ciphertext",
                    minimum=17,
                    maximum=_MAX_PLAINTEXT_BYTES + 16,
                ),
                aad,
            )
        except InvalidTag:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT") from None
        expected_commitment = hmac.new(
            self._commitment.secret,
            b"connected-schedule-template-commitment-v1\x00" + plaintext,
            hashlib.sha256,
        ).hexdigest()
        if (
            self._commitment.key_id != record.reference.commitment_key_id
            or not hmac.compare_digest(expected_commitment, record.reference.parameters_sha256)
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT")
        try:
            value = json.loads(plaintext.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT") from None
        if type(value) is not dict or set(value) != {
            "version",
            "scheduleId",
            "turnId",
            "planPayloadId",
            "planReferenceBindingSha256",
            "actionPayload",
        }:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT")
        reference = record.reference
        if (
            value["version"] != "connected-schedule-template-envelope-v1"
            or value["scheduleId"] != reference.schedule_id
            or value["turnId"] != reference.turn_id
            or value["planPayloadId"] != reference.plan_payload_id
            or value["planReferenceBindingSha256"]
            != reference.plan_reference_binding_sha256
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT")
        try:
            envelope = ConnectedActionPayloadEnvelope.from_value(value["actionPayload"])
        except Exception:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT") from None
        version = expected_resource_version(envelope.request)
        version_sha = None if version is None else hashlib.sha256(version.encode()).hexdigest()
        if envelope.action is not reference.action or version_sha != reference.resource_version_sha256:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_CUSTODY_CORRUPT")
        return envelope


@dataclass(frozen=True, slots=True)
class ConnectedChatScheduleRecord:
    request_id: str
    schedule_id: str
    template_id: str
    owner_id: str
    turn_id: str
    task_id: str
    connection_id: str
    plan_payload_id: str
    plan_reference_binding_sha256: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    parameters_sha256: str
    template_reference_binding_sha256: str
    next_run_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "schedule_id",
            "template_id",
            "owner_id",
            "turn_id",
            "task_id",
            "connection_id",
            "plan_payload_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        for name in (
            "plan_reference_binding_sha256",
            "parameters_sha256",
            "template_reference_binding_sha256",
        ):
            _sha(getattr(self, name), name)
        object.__setattr__(self, "next_run_at", _time(self.next_run_at, "next_run_at"))
        object.__setattr__(self, "created_at", _time(self.created_at, "created_at"))


class ConnectedScheduleRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


_CHAT_RECORD_KEYS = frozenset(
    {
        "request_id",
        "schedule_id",
        "template_id",
        "owner_id",
        "turn_id",
        "task_id",
        "connection_id",
        "plan_payload_id",
        "plan_reference_binding_sha256",
        "provider",
        "resource",
        "action",
        "parameters_sha256",
        "template_reference_binding_sha256",
        "next_run_at",
        "created_at",
    }
)


def _one(value: object) -> object:
    if isinstance(value, list):
        if len(value) != 1:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
        return value[0]
    return value


def _chat_record(value: object) -> ConnectedChatScheduleRecord:
    value = _one(value)
    if type(value) is not dict or frozenset(value) != _CHAT_RECORD_KEYS:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
    row = value
    try:
        return ConnectedChatScheduleRecord(
            request_id=row["request_id"],
            schedule_id=row["schedule_id"],
            template_id=row["template_id"],
            owner_id=row["owner_id"],
            turn_id=row["turn_id"],
            task_id=row["task_id"],
            connection_id=row["connection_id"],
            plan_payload_id=row["plan_payload_id"],
            plan_reference_binding_sha256=row["plan_reference_binding_sha256"],
            provider=ConnectorProvider(row["provider"]),
            resource=ConnectorResource(row["resource"]),
            action=ConnectorActionKind(row["action"]),
            parameters_sha256=row["parameters_sha256"],
            template_reference_binding_sha256=row[
                "template_reference_binding_sha256"
            ],
            next_run_at=_time(row["next_run_at"], "next_run_at"),
            created_at=_time(row["created_at"], "created_at"),
        )
    except ConnectedScheduleAdapterError:
        raise
    except Exception:
        raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID") from None


class SupabaseConnectedChatScheduleStage:
    """Atomic settled-plan/template/schedule/turn transaction."""

    def __init__(self, database: ConnectedScheduleRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected schedule database is invalid")
        self._database = database

    async def read(
        self, *, owner_id: str, request_id: str
    ) -> ConnectedChatScheduleRecord | None:
        value = await self._database.rpc(
            "connected_operator_read_chat_schedule_v2",
            {"p_owner_id": _uuid(owner_id, "owner_id"), "p_request_id": _uuid(request_id, "request_id")},
            retry_transient=True,
        )
        value = _one(value)
        return None if value is None else _chat_record(value)

    async def create(
        self,
        *,
        context: ConnectedOperatorActionContext,
        planning: ConnectedPlanOnceCommand,
        request_id: str,
        task_id: str,
        record: EncryptedConnectedScheduleTemplate,
        cadence_seconds: int,
        time_zone: str,
        quiet_start_minute: int | None,
        quiet_end_minute: int | None,
        requires_approval_every_run: bool,
    ) -> ConnectedChatScheduleRecord:
        if type(context) is not ConnectedOperatorActionContext or type(
            planning
        ) is not ConnectedPlanOnceCommand:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_INVALID")
        reference = record.reference
        payload: dict[str, object] = {
            "p_owner_id": context.request.owner_id,
            "p_session_id": context.request.session_id,
            "p_chat_id": context.request.chat_id,
            "p_message_id": context.request.message_id,
            "p_turn_id": context.turn_id,
            "p_claim_token": context.claim_token,
            "p_origin_session_binding_sha256": context.origin_session_binding_sha256,
            "p_request_binding_sha256": context.request_binding_sha256,
            "p_planning_id": planning.planning_id,
            "p_plan_payload_id": planning.payload_id,
            "p_request_id": _uuid(request_id, "request_id"),
            "p_schedule_id": reference.schedule_id,
            "p_template_id": reference.template_id,
            "p_task_id": _uuid(task_id, "task_id"),
            "p_connection_id": reference.connection_id,
            "p_provider": reference.provider.value,
            "p_resource": reference.resource.value,
            "p_action": reference.action.value,
            "p_authorization_revision": reference.authorization_revision,
            "p_authorization_snapshot_sha256": reference.authorization_snapshot_sha256,
            "p_granted_actions_sha256": reference.granted_actions_sha256,
            "p_granted_scopes_sha256": reference.granted_scopes_sha256,
            "p_commitment_key_id": reference.commitment_key_id,
            "p_parameters_sha256": reference.parameters_sha256,
            "p_resource_version_sha256": reference.resource_version_sha256,
            "p_template_reference_binding_sha256": reference.binding_sha256,
            "p_key_id": record.key_id,
            "p_wrapped_key_nonce": record.wrapped_key_nonce,
            "p_wrapped_key_ciphertext": record.wrapped_key_ciphertext,
            "p_payload_nonce": record.payload_nonce,
            "p_payload_ciphertext": record.payload_ciphertext,
            "p_record_binding_sha256": record.record_binding_sha256,
            "p_time_zone": time_zone,
            "p_cadence_seconds": cadence_seconds,
            "p_quiet_start_minute": quiet_start_minute,
            "p_quiet_end_minute": quiet_end_minute,
            "p_requires_approval_every_run": requires_approval_every_run,
            "p_created_at": reference.created_at.isoformat(),
        }
        try:
            value = await self._database.rpc(
                "connected_operator_create_chat_schedule_v2",
                payload,
                retry_transient=False,
            )
            return _chat_record(value)
        except ConnectedScheduleAdapterError:
            raise
        except Exception:
            # A transport failure can occur after the database committed.  Do
            # not issue a second mutating RPC; recover the request-id receipt.
            pass
        try:
            recovered = await self.read(
                owner_id=context.request.owner_id, request_id=request_id
            )
        except Exception:
            recovered = None
        if recovered is None:
            raise ConnectedScheduleAdapterError(
                "CONNECTED_SCHEDULE_STAGE_FAILED", retryable=True
            ) from None
        return recovered


class ConnectedScheduleAuthoritySource(Protocol):
    async def get_connection_authority(
        self, *, owner_id: str, connection_id: str
    ) -> ConnectedConnectionAuthorityView | None: ...


class ConnectedOperatorScheduleCoordinator:
    """Server-owned schedule creation from one settled typed chat plan."""

    def __init__(
        self,
        *,
        planning_key: ConnectedPlanBindingKey,
        plans: ConnectedPlanControlPlane,
        authorities: ConnectedScheduleAuthoritySource,
        vault: ConnectedScheduleTemplateVault,
        stage: SupabaseConnectedChatScheduleStage,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(planning_key) is not ConnectedPlanBindingKey:
            raise TypeError("connected planning key is invalid")
        for dependency, method in (
            (plans, "read"),
            (authorities, "get_connection_authority"),
            (stage, "create"),
        ):
            if not callable(getattr(dependency, method, None)):
                raise TypeError("connected schedule dependency is invalid")
        if type(vault) is not ConnectedScheduleTemplateVault or not callable(now):
            raise TypeError("connected schedule dependency is invalid")
        self._planning_key = planning_key
        self._plans = plans
        self._authorities = authorities
        self._vault = vault
        self._stage = stage
        self._now = now

    @staticmethod
    def _id(turn_id: str, label: str) -> str:
        return str(uuid5(_IDENTITY_NAMESPACE, f"{turn_id}:{label}"))

    def _planning(self, context: ConnectedOperatorActionContext) -> ConnectedPlanOnceCommand:
        return ConnectedPlanOnceCommand.build(
            binding_key=self._planning_key,
            owner_id=context.request.owner_id,
            session_id=context.request.session_id,
            chat_id=context.request.chat_id,
            message_id=context.request.message_id,
            turn_id=context.turn_id,
            claim_token=context.claim_token,
            origin_session_binding_sha256=context.origin_session_binding_sha256,
            request_binding_sha256=context.request_binding_sha256,
            requested_at=context.requested_at,
            expires_at=context.expires_at,
        )

    @staticmethod
    def _matches(
        value: ConnectedChatScheduleRecord,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
        planning: ConnectedPlanOnceCommand,
        request_id: str,
    ) -> bool:
        return (
            value.request_id == request_id
            and value.owner_id == context.request.owner_id
            and value.turn_id == context.turn_id
            and value.plan_payload_id == planning.payload_id
            and value.connection_id == plan.connection_id
            and value.provider is plan.provider
            and value.resource is plan.resource
            and value.action is plan.action
        )

    async def create(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> ConnectedOperatorScheduleResult:
        if (
            type(context) is not ConnectedOperatorActionContext
            or type(plan) is not ConnectedOperatorPlan
            or plan.disposition is not ConnectedOperatorDisposition.SCHEDULE
            or plan.schedule is None
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_INVALID")
        requirement = ConnectedActionPolicy.requirement(plan.action)
        if plan.schedule.requires_approval_every_run is not requirement.mutates_external_state:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_INVALID")
        planning = self._planning(context)
        request_id = self._id(context.turn_id, "schedule-request")
        try:
            existing = await self._stage.read(
                owner_id=context.request.owner_id, request_id=request_id
            )
        except Exception:
            existing = None
        if existing is not None:
            if not self._matches(
                existing,
                context=context,
                plan=plan,
                planning=planning,
                request_id=request_id,
            ):
                raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
            return ConnectedOperatorScheduleResult(
                schedule_id=existing.schedule_id, next_run_at=existing.next_run_at
            )
        try:
            operation = await self._plans.read(planning)
        except Exception:
            raise ConnectedScheduleAdapterError(
                "CONNECTED_SCHEDULE_STAGE_FAILED", retryable=True
            ) from None
        if (
            type(operation) is not ConnectedPlanOperationRecord
            or operation.state is not ConnectedPlanOperationState.SETTLED
            or operation.disposition is not ConnectedOperatorDisposition.SCHEDULE
            or operation.payload_id != planning.payload_id
            or operation.connection_id != plan.connection_id
            or operation.provider is not plan.provider
            or operation.resource is not plan.resource
            or operation.action is not plan.action
            or operation.payload_reference_binding_sha256 is None
            or operation.expires_at <= self._now().astimezone(UTC)
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_AUTHORITY_CHANGED")
        try:
            authority = await self._authorities.get_connection_authority(
                owner_id=context.request.owner_id,
                connection_id=plan.connection_id,
            )
        except Exception:
            raise ConnectedScheduleAdapterError(
                "CONNECTED_SCHEDULE_STAGE_FAILED", retryable=True
            ) from None
        now = self._now()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_STAGE_FAILED")
        now = now.astimezone(UTC)
        if (
            type(authority) is not ConnectedConnectionAuthorityView
            or authority.connection_id != plan.connection_id
            or authority.provider is not plan.provider
            or authority.resource is not plan.resource
            or plan.action not in authority.granted_actions
            or authority.expires_at <= now
        ):
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_AUTHORITY_CHANGED")
        schedule_id = self._id(context.turn_id, "schedule")
        template_id = self._id(context.turn_id, "schedule-template")
        task_id = self._id(context.turn_id, "schedule-task")
        encrypted = self._vault.prepare(
            template_id=template_id,
            schedule_id=schedule_id,
            owner_id=context.request.owner_id,
            turn_id=context.turn_id,
            connection_id=plan.connection_id,
            task_id=task_id,
            plan_payload_id=planning.payload_id,
            plan_reference_binding_sha256=operation.payload_reference_binding_sha256,
            provider=plan.provider,
            resource=plan.resource,
            action=plan.action,
            authorization_revision=authority.authorization_revision,
            authorization_snapshot_sha256=authority.authorization_snapshot_sha256,
            granted_actions_sha256=action_set_sha256(authority.granted_actions),
            granted_scopes_sha256=authority.granted_scopes_sha256,
            request=plan.request,
            # Stable across a process restart.  Random ciphertext may differ,
            # but the immutable reference/commitment identity does not.
            created_at=context.requested_at,
        )
        quiet_start = plan.schedule.quiet_start
        quiet_end = plan.schedule.quiet_end
        quiet_start_minute = (
            None
            if quiet_start is None
            else int(quiet_start[:2]) * 60 + int(quiet_start[3:])
        )
        quiet_end_minute = (
            None if quiet_end is None else int(quiet_end[:2]) * 60 + int(quiet_end[3:])
        )
        created = await self._stage.create(
            context=context,
            planning=planning,
            request_id=request_id,
            task_id=task_id,
            record=encrypted,
            cadence_seconds=plan.schedule.cadence_seconds,
            time_zone=plan.schedule.time_zone,
            quiet_start_minute=quiet_start_minute,
            quiet_end_minute=quiet_end_minute,
            requires_approval_every_run=plan.schedule.requires_approval_every_run,
        )
        if not self._matches(
            created,
            context=context,
            plan=plan,
            planning=planning,
            request_id=request_id,
        ) or created.template_reference_binding_sha256 != encrypted.reference.binding_sha256:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
        return ConnectedOperatorScheduleResult(
            schedule_id=created.schedule_id, next_run_at=created.next_run_at
        )


class ConnectedScheduleFreshApprovalSource(Protocol):
    async def fresh_approval(
        self,
        *,
        claim: ConnectedScheduleClaim,
        intent: ConnectedActionIntent,
        action_payload: ConnectedActionPayloadEnvelope,
    ) -> ConnectedApprovalEvidence | None: ...


class ConnectedScheduleTemplateReader(Protocol):
    async def read_template(
        self, *, template_id: str
    ) -> EncryptedConnectedScheduleTemplate | None: ...


class ConnectedScheduleTemplateResolver:
    """Reconstruct a typed provider request solely from encrypted custody."""

    def __init__(
        self,
        *,
        templates: ConnectedScheduleTemplateReader,
        vault: ConnectedScheduleTemplateVault,
        approvals: ConnectedScheduleFreshApprovalSource | None = None,
    ) -> None:
        if not callable(getattr(templates, "read_template", None)):
            raise TypeError("connected schedule template reader is invalid")
        if type(vault) is not ConnectedScheduleTemplateVault:
            raise TypeError("connected schedule template vault is invalid")
        if approvals is not None and not callable(getattr(approvals, "fresh_approval", None)):
            raise TypeError("connected schedule approval source is invalid")
        self._templates = templates
        self._vault = vault
        self._approvals = approvals

    @staticmethod
    def _require_v2(claim: ConnectedScheduleClaim) -> None:
        if any(
            value is None
            for value in (
                claim.turn_id,
                claim.grant_id,
                claim.plan_payload_id,
                claim.plan_reference_binding_sha256,
                claim.authorization_revision,
                claim.authorization_snapshot_sha256,
                claim.granted_actions_sha256,
                claim.granted_scopes_sha256,
                claim.template_reference_binding_sha256,
            )
        ):
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_TEMPLATE_INVALID")

    async def prepare(self, claim: ConnectedScheduleClaim) -> ConnectedScheduledRun:
        if type(claim) is not ConnectedScheduleClaim:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_TEMPLATE_INVALID")
        self._require_v2(claim)
        try:
            record = await self._templates.read_template(
                template_id=claim.action_template_ref
            )
        except Exception:
            raise ConnectedSchedulerError(
                "CONNECTED_SCHEDULE_TEMPLATE_UNAVAILABLE", retryable=True
            ) from None
        if record is None:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_TEMPLATE_INVALID")
        reference = record.reference
        if (
            reference.template_id != claim.action_template_ref
            or reference.schedule_id != claim.schedule_id
            or reference.owner_id != claim.owner_id
            or reference.turn_id != claim.turn_id
            or reference.connection_id != claim.connection_id
            or reference.task_id != claim.task_id
            or reference.plan_payload_id != claim.plan_payload_id
            or reference.plan_reference_binding_sha256
            != claim.plan_reference_binding_sha256
            or reference.provider is not claim.provider
            or reference.resource is not claim.resource
            or reference.action is not claim.action
            or reference.authorization_revision != claim.authorization_revision
            or reference.authorization_snapshot_sha256
            != claim.authorization_snapshot_sha256
            or reference.granted_actions_sha256 != claim.granted_actions_sha256
            or reference.granted_scopes_sha256 != claim.granted_scopes_sha256
            or reference.parameters_sha256 != claim.parameters_sha256
            or reference.resource_version_sha256 != claim.resource_version_sha256
            or reference.binding_sha256 != claim.template_reference_binding_sha256
        ):
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_RUN_BINDING_MISMATCH")
        try:
            envelope = self._vault.open(record)
        except Exception:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_TEMPLATE_INVALID") from None
        expected_version = expected_resource_version(envelope.request)
        action_id = str(
            uuid5(
                _ACTION_NAMESPACE,
                f"{claim.schedule_id}:{claim.scheduled_for.isoformat()}",
            )
        )
        requested_at = claim.claimed_at
        if ConnectedActionPolicy.requirement(claim.action).mutates_external_state:
            if any(
                value is None
                for value in (
                    claim.occurrence_id,
                    claim.occurrence_action_id,
                    claim.occurrence_approval_id,
                    claim.occurrence_created_at,
                )
            ):
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
            action_id = str(claim.occurrence_action_id)
            requested_at = claim.occurrence_created_at  # type: ignore[assignment]
        intent = ConnectedActionIntent.build(
            action_id=action_id,
            owner_id=claim.owner_id,
            task_id=claim.task_id,
            turn_id=str(claim.turn_id),
            connection_id=claim.connection_id,
            provider=claim.provider,
            resource=claim.resource,
            authorization_revision=int(claim.authorization_revision),
            authorization_snapshot_sha256=str(claim.authorization_snapshot_sha256),
            action=claim.action,
            parameters_sha256=claim.parameters_sha256,
            resource_version_sha256=claim.resource_version_sha256,
            requested_at=requested_at,
        )
        invocation = ConnectedActionInvocation(
            intent=intent,
            request=envelope.request,
            payload_sha256=claim.parameters_sha256,
            request_target_binding_sha256=envelope.request.target_binding_sha256,
            expected_resource_version=expected_version,
        )
        grant = ConnectedTaskGrant(
            grant_id=str(claim.grant_id),
            owner_id=claim.owner_id,
            task_id=claim.task_id,
            turn_id=str(claim.turn_id),
            connection_id=claim.connection_id,
            provider=claim.provider,
            resource=claim.resource,
            authorization_revision=int(claim.authorization_revision),
            authorization_snapshot_sha256=str(claim.authorization_snapshot_sha256),
            actions=frozenset({claim.action}),
            actions_sha256=action_set_sha256({claim.action}),
            expires_at=claim.claim_expires_at,
        )
        approval = None
        if ConnectedActionPolicy.requirement(claim.action).mutates_external_state:
            if self._approvals is None:
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
            approval = await self._approvals.fresh_approval(
                claim=claim,
                intent=intent,
                action_payload=envelope,
            )
            requirement = ConnectedActionPolicy.requirement(claim.action)
            if (
                type(approval) is not ConnectedApprovalEvidence
                or approval.approval_id != claim.occurrence_approval_id
                or approval.action_id != intent.action_id
                or approval.owner_id != claim.owner_id
                or approval.task_id != claim.task_id
                or approval.turn_id != claim.turn_id
                or approval.connection_id != claim.connection_id
                or approval.provider is not claim.provider
                or approval.resource is not claim.resource
                or approval.action is not claim.action
                or approval.authorization_revision != claim.authorization_revision
                or approval.authorization_snapshot_sha256
                != claim.authorization_snapshot_sha256
                or approval.approval_class is not requirement.approval_class
                or approval.parameters_sha256 != claim.parameters_sha256
                or approval.resource_version_sha256 != claim.resource_version_sha256
                or approval.approved_at < requested_at
                or approval.expires_at <= claim.claimed_at
                or approval.approved_at > claim.claim_expires_at
            ):
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
        return ConnectedScheduledRun(invocation=invocation, grant=grant, approval=approval)


_CLAIM_KEYS_V2 = frozenset(
    {
        "schedule_id",
        "owner_id",
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
        "scheduled_for",
        "claim_id",
        "claimed_at",
        "claim_expires_at",
        "turn_id",
        "grant_id",
        "plan_payload_id",
        "plan_reference_binding_sha256",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "template_reference_binding_sha256",
        "resource_version_sha256",
    }
)
_CLAIM_KEYS = _CLAIM_KEYS_V2 | frozenset(
    {
        "occurrence_id",
        "occurrence_action_id",
        "occurrence_approval_id",
        "occurrence_created_at",
    }
)
_FINISH_KEYS_V2 = frozenset(
    {
        "completion_id",
        "schedule_id",
        "owner_id",
        "claim_id",
        "task_state_revision",
        "outcome",
        "operation_id",
        "next_run_at",
        "finished_at",
        "recorded_at",
    }
)
_FINISH_KEYS = _FINISH_KEYS_V2 | frozenset({"occurrence_id"})
_TEMPLATE_KEYS = frozenset(
    {
        "template_id",
        "schedule_id",
        "owner_id",
        "turn_id",
        "connection_id",
        "task_id",
        "plan_payload_id",
        "plan_reference_binding_sha256",
        "provider",
        "resource",
        "action",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "commitment_key_id",
        "parameters_sha256",
        "resource_version_sha256",
        "reference_binding_sha256",
        "created_at",
        "key_id",
        "wrapped_key_nonce",
        "wrapped_key_ciphertext",
        "payload_nonce",
        "payload_ciphertext",
        "record_binding_sha256",
    }
)


class SupabaseConnectedScheduleStore:
    """Concrete v2 scheduler store and encrypted-template reader."""

    def __init__(self, database: ConnectedScheduleRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected schedule database is invalid")
        self._database = database

    async def _rpc(self, name: str, payload: dict[str, object], *, read: bool) -> object:
        return _one(
            await self._database.rpc(name, payload, retry_transient=read)
        )

    @staticmethod
    def _claim(value: object) -> ConnectedScheduleClaim | None:
        if value is None:
            return None
        if type(value) is not dict or frozenset(value) not in {
            _CLAIM_KEYS_V2,
            _CLAIM_KEYS,
        }:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
        row = value
        v3 = frozenset(row) == _CLAIM_KEYS
        try:
            return ConnectedScheduleClaim(
                schedule_id=row["schedule_id"],
                owner_id=row["owner_id"],
                connection_id=row["connection_id"],
                task_id=row["task_id"],
                provider=ConnectorProvider(row["provider"]),
                resource=ConnectorResource(row["resource"]),
                action=ConnectorActionKind(row["action"]),
                action_template_ref=row["action_template_ref"],
                parameters_sha256=row["parameters_sha256"],
                task_state_revision=row["task_state_revision"],
                time_zone=row["time_zone"],
                cadence_seconds=row["cadence_seconds"],
                quiet_start_minute=row["quiet_start_minute"],
                quiet_end_minute=row["quiet_end_minute"],
                requires_approval_every_run=row["requires_approval_every_run"],
                scheduled_for=_time(row["scheduled_for"], "scheduled_for"),
                claim_id=row["claim_id"],
                claimed_at=_time(row["claimed_at"], "claimed_at"),
                claim_expires_at=_time(row["claim_expires_at"], "claim_expires_at"),
                turn_id=row["turn_id"],
                grant_id=row["grant_id"],
                plan_payload_id=row["plan_payload_id"],
                plan_reference_binding_sha256=row["plan_reference_binding_sha256"],
                authorization_revision=row["authorization_revision"],
                authorization_snapshot_sha256=row["authorization_snapshot_sha256"],
                granted_actions_sha256=row["granted_actions_sha256"],
                granted_scopes_sha256=row["granted_scopes_sha256"],
                template_reference_binding_sha256=row[
                    "template_reference_binding_sha256"
                ],
                resource_version_sha256=row["resource_version_sha256"],
                occurrence_id=row["occurrence_id"] if v3 else None,
                occurrence_action_id=row["occurrence_action_id"] if v3 else None,
                occurrence_approval_id=row["occurrence_approval_id"] if v3 else None,
                occurrence_created_at=(
                    _time(row["occurrence_created_at"], "occurrence_created_at")
                    if v3 and row["occurrence_created_at"] is not None
                    else None
                ),
            )
        except ConnectedScheduleAdapterError:
            raise
        except Exception:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID") from None

    @staticmethod
    def _completion(value: object) -> ConnectedScheduleCompletion:
        if type(value) is not dict or frozenset(value) not in {
            _FINISH_KEYS_V2,
            _FINISH_KEYS,
        }:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
        row = value
        v3 = frozenset(row) == _FINISH_KEYS
        try:
            finish = ConnectedScheduleFinish(
                completion_id=row["completion_id"],
                schedule_id=row["schedule_id"],
                owner_id=row["owner_id"],
                claim_id=row["claim_id"],
                task_state_revision=row["task_state_revision"],
                outcome=ConnectedScheduleRunOutcome(row["outcome"]),
                operation_id=row["operation_id"],
                next_run_at=_time(row["next_run_at"], "next_run_at"),
                finished_at=_time(row["finished_at"], "finished_at"),
                occurrence_id=row["occurrence_id"] if v3 else None,
            )
            return ConnectedScheduleCompletion(
                finish=finish,
                recorded_at=_time(row["recorded_at"], "recorded_at"),
            )
        except ConnectedScheduleAdapterError:
            raise
        except Exception:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID") from None

    async def claim_once(
        self, *, claim_id: str, lease_seconds: int
    ) -> ConnectedScheduleClaim | None:
        canonical_claim = _uuid(claim_id, "claim_id")
        value = await self._rpc(
            "connected_app_claim_schedule_v3",
            {
                "p_claim_id": canonical_claim,
                "p_occurrence_id": str(uuid5(_OCCURRENCE_NAMESPACE, canonical_claim)),
                "p_occurrence_action_id": str(
                    uuid5(_OCCURRENCE_ACTION_NAMESPACE, canonical_claim)
                ),
                "p_occurrence_approval_id": str(
                    uuid5(_OCCURRENCE_APPROVAL_NAMESPACE, canonical_claim)
                ),
                "p_lease_seconds": lease_seconds,
            },
            read=False,
        )
        return self._claim(value)

    async def readback_claim(self, *, claim_id: str) -> ConnectedScheduleClaim | None:
        value = await self._rpc(
            "connected_app_read_schedule_claim_v3",
            {"p_claim_id": _uuid(claim_id, "claim_id")},
            read=True,
        )
        return self._claim(value)

    async def finish_once(self, finish: ConnectedScheduleFinish) -> ConnectedScheduleCompletion:
        value = await self._rpc(
            "connected_app_finish_schedule_v3",
            {
                "p_completion_id": finish.completion_id,
                "p_schedule_id": finish.schedule_id,
                "p_owner_id": finish.owner_id,
                "p_claim_id": finish.claim_id,
                "p_task_state_revision": finish.task_state_revision,
                "p_outcome": finish.outcome.value,
                "p_operation_id": finish.operation_id,
                "p_next_run_at": finish.next_run_at.isoformat(),
                "p_finished_at": finish.finished_at.isoformat(),
                "p_occurrence_id": finish.occurrence_id,
            },
            read=False,
        )
        return self._completion(value)

    async def readback_finish(
        self, *, schedule_id: str, claim_id: str, completion_id: str
    ) -> ConnectedScheduleCompletion | None:
        value = await self._rpc(
            "connected_app_read_schedule_finish_v3",
            {
                "p_schedule_id": _uuid(schedule_id, "schedule_id"),
                "p_claim_id": _uuid(claim_id, "claim_id"),
                "p_completion_id": _uuid(completion_id, "completion_id"),
            },
            read=True,
        )
        return None if value is None else self._completion(value)

    async def read_template(
        self, *, template_id: str
    ) -> EncryptedConnectedScheduleTemplate | None:
        value = await self._rpc(
            "connected_app_read_schedule_template_v2",
            {"p_template_id": _uuid(template_id, "template_id")},
            read=True,
        )
        if value is None:
            return None
        if type(value) is not dict or frozenset(value) != _TEMPLATE_KEYS:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
        row = value
        try:
            reference = ConnectedScheduleTemplateReference(
                template_id=row["template_id"],
                schedule_id=row["schedule_id"],
                owner_id=row["owner_id"],
                turn_id=row["turn_id"],
                connection_id=row["connection_id"],
                task_id=row["task_id"],
                plan_payload_id=row["plan_payload_id"],
                plan_reference_binding_sha256=row["plan_reference_binding_sha256"],
                provider=ConnectorProvider(row["provider"]),
                resource=ConnectorResource(row["resource"]),
                action=ConnectorActionKind(row["action"]),
                authorization_revision=row["authorization_revision"],
                authorization_snapshot_sha256=row["authorization_snapshot_sha256"],
                granted_actions_sha256=row["granted_actions_sha256"],
                granted_scopes_sha256=row["granted_scopes_sha256"],
                commitment_key_id=row["commitment_key_id"],
                parameters_sha256=row["parameters_sha256"],
                resource_version_sha256=row["resource_version_sha256"],
                created_at=_time(row["created_at"], "created_at"),
            )
            if reference.binding_sha256 != row["reference_binding_sha256"]:
                raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID")
            return EncryptedConnectedScheduleTemplate(
                reference=reference,
                key_id=row["key_id"],
                wrapped_key_nonce=row["wrapped_key_nonce"],
                wrapped_key_ciphertext=row["wrapped_key_ciphertext"],
                payload_nonce=row["payload_nonce"],
                payload_ciphertext=row["payload_ciphertext"],
                record_binding_sha256=row["record_binding_sha256"],
            )
        except ConnectedScheduleAdapterError:
            raise
        except Exception:
            raise ConnectedScheduleAdapterError("CONNECTED_SCHEDULE_RESULT_INVALID") from None


__all__ = [
    "ConnectedChatScheduleRecord",
    "ConnectedOperatorScheduleCoordinator",
    "ConnectedScheduleAdapterError",
    "ConnectedScheduleAuthoritySource",
    "ConnectedScheduleFreshApprovalSource",
    "ConnectedScheduleRPC",
    "ConnectedScheduleTemplateCommitmentKey",
    "ConnectedScheduleTemplateKey",
    "ConnectedScheduleTemplateReader",
    "ConnectedScheduleTemplateReference",
    "ConnectedScheduleTemplateResolver",
    "ConnectedScheduleTemplateVault",
    "EncryptedConnectedScheduleTemplate",
    "SupabaseConnectedChatScheduleStage",
    "SupabaseConnectedScheduleStore",
]
