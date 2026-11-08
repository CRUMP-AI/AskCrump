"""Strict PostgREST stores for encrypted connected-app custody records.

Only encrypted envelopes and content-free authority metadata cross this module.
The database functions are deliberately idempotent so a lost HTTP response can
be resolved by authoritative readback without repeating a provider effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
from typing import Any, Protocol
from uuid import UUID, uuid4

from .connected_app_contracts import ConnectorAccountKind, CredentialHandleRef
from .connected_app_credential_vault import (
    ConnectedCredentialMetadata,
    ConnectedCredentialSecretStore,
    EncryptedConnectedCredential,
)
from .connected_app_payload_vault import (
    ConnectedPayloadRef,
    ConnectedPayloadStore,
    EncryptedConnectedPayload,
)
from .connected_app_policy import ConnectorActionKind, ConnectorProvider


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]{1,699999}$")
_MAX_LEASE = timedelta(seconds=30)


class ConnectedDurableStoreError(RuntimeError):
    """Content-free durable-store failure."""

    _ALLOWED = frozenset(
        {
            "CONNECTED_STORE_AMBIGUOUS",
            "CONNECTED_STORE_BINDING_MISMATCH",
            "CONNECTED_STORE_BUSY",
            "CONNECTED_STORE_INVALID",
            "CONNECTED_STORE_TOMBSTONED",
            "CONNECTED_STORE_UNAVAILABLE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid connected durable-store error")
        self.code = code
        super().__init__(code)


class ConnectedStoreRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class ConnectedPayloadReferenceResolver(Protocol):
    """Recover immutable nonsecret payload metadata after a host restart."""

    async def resolve_reference(
        self,
        *,
        owner_id: str,
        payload_id: str,
        connection_id: str,
        action_id: str,
        provider: ConnectorProvider,
        action: ConnectorActionKind,
    ) -> ConnectedPayloadRef | None: ...


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID") from None
    if str(parsed) != value:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    return value


def _text(value: object, *, maximum: int, pattern: re.Pattern[str] | None = None) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or (pattern is not None and not pattern.fullmatch(value))
    ):
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    return value


def _positive_int(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    return value.astimezone(UTC).isoformat()


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    return value


def _enum(enum_type: type[Any], value: object) -> Any:
    if not isinstance(value, str):
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
    try:
        return enum_type(value)
    except ValueError:
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID") from None


def _handle_sha256(credential: CredentialHandleRef) -> str:
    return hashlib.sha256(credential.handle_id.encode("utf-8")).hexdigest()


async def _rpc(rpc: ConnectedStoreRPC, name: str, payload: dict[str, object]) -> object:
    try:
        return await rpc.rpc(name, payload, retry_transient=True)
    except ConnectedDurableStoreError:
        raise
    except Exception:
        raise ConnectedDurableStoreError("CONNECTED_STORE_UNAVAILABLE") from None


_PAYLOAD_RECORD_KEYS = frozenset(
    {
        "payload_id",
        "owner_id",
        "connection_id",
        "action_id",
        "provider",
        "action",
        "commitment_key_id",
        "payload_sha256",
        "created_at",
        "expires_at",
        "identity_sha256",
        "reference_binding_sha256",
        "key_id",
        "wrapped_key_nonce",
        "wrapped_key_ciphertext",
        "payload_nonce",
        "payload_ciphertext",
        "record_binding_sha256",
    }
)

_PAYLOAD_REFERENCE_KEYS = frozenset(
    {
        "payload_id",
        "owner_id",
        "connection_id",
        "action_id",
        "provider",
        "action",
        "commitment_key_id",
        "payload_sha256",
        "created_at",
        "expires_at",
        "identity_sha256",
        "reference_binding_sha256",
    }
)


def _payload_reference(value: object) -> ConnectedPayloadRef:
    row = _object(value, _PAYLOAD_REFERENCE_KEYS)
    reference = ConnectedPayloadRef(
        payload_id=_uuid(row["payload_id"], "payload_id"),
        owner_id=_uuid(row["owner_id"], "owner_id"),
        connection_id=_uuid(row["connection_id"], "connection_id"),
        action_id=_uuid(row["action_id"], "action_id"),
        provider=_enum(ConnectorProvider, row["provider"]),
        action=_enum(ConnectorActionKind, row["action"]),
        commitment_key_id=_text(row["commitment_key_id"], maximum=64, pattern=_KEY_ID),
        payload_sha256=_sha(row["payload_sha256"]),
        created_at=_time(row["created_at"]),
        expires_at=_time(row["expires_at"]),
    )
    if not hmac.compare_digest(
        reference.identity_sha256, _sha(row["identity_sha256"])
    ) or not hmac.compare_digest(reference.binding_sha256, _sha(row["reference_binding_sha256"])):
        raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
    return reference


def _payload_record(value: object) -> EncryptedConnectedPayload:
    row = _object(value, _PAYLOAD_RECORD_KEYS)
    reference = ConnectedPayloadRef(
        payload_id=_uuid(row["payload_id"], "payload_id"),
        owner_id=_uuid(row["owner_id"], "owner_id"),
        connection_id=_uuid(row["connection_id"], "connection_id"),
        action_id=_uuid(row["action_id"], "action_id"),
        provider=_enum(ConnectorProvider, row["provider"]),
        action=_enum(ConnectorActionKind, row["action"]),
        commitment_key_id=_text(row["commitment_key_id"], maximum=64, pattern=_KEY_ID),
        payload_sha256=_sha(row["payload_sha256"]),
        created_at=_time(row["created_at"]),
        expires_at=_time(row["expires_at"]),
    )
    if not hmac.compare_digest(
        reference.identity_sha256, _sha(row["identity_sha256"])
    ) or not hmac.compare_digest(reference.binding_sha256, _sha(row["reference_binding_sha256"])):
        raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
    try:
        return EncryptedConnectedPayload(
            reference=reference,
            key_id=_text(row["key_id"], maximum=64, pattern=_KEY_ID),
            wrapped_key_nonce=_text(row["wrapped_key_nonce"], maximum=64, pattern=_B64URL),
            wrapped_key_ciphertext=_text(
                row["wrapped_key_ciphertext"], maximum=128, pattern=_B64URL
            ),
            payload_nonce=_text(row["payload_nonce"], maximum=64, pattern=_B64URL),
            payload_ciphertext=_text(row["payload_ciphertext"], maximum=699999, pattern=_B64URL),
            record_binding_sha256=_sha(row["record_binding_sha256"]),
        )
    except (TypeError, ValueError):
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID") from None


def _payload_parameters(record: EncryptedConnectedPayload) -> dict[str, object]:
    ref = record.reference
    return {
        "p_payload_id": ref.payload_id,
        "p_owner_id": ref.owner_id,
        "p_connection_id": ref.connection_id,
        "p_action_id": ref.action_id,
        "p_provider": ref.provider.value,
        "p_action": ref.action.value,
        "p_commitment_key_id": ref.commitment_key_id,
        "p_payload_sha256": ref.payload_sha256,
        "p_created_at": _iso(ref.created_at),
        "p_expires_at": _iso(ref.expires_at),
        "p_identity_sha256": ref.identity_sha256,
        "p_reference_binding_sha256": ref.binding_sha256,
        "p_key_id": record.key_id,
        "p_wrapped_key_nonce": record.wrapped_key_nonce,
        "p_wrapped_key_ciphertext": record.wrapped_key_ciphertext,
        "p_payload_nonce": record.payload_nonce,
        "p_payload_ciphertext": record.payload_ciphertext,
        "p_record_binding_sha256": record.record_binding_sha256,
    }


class SupabaseConnectedPayloadStore(ConnectedPayloadStore):
    """Atomic encrypted payload store backed only by service-role RPCs."""

    def __init__(self, rpc: ConnectedStoreRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("connected payload RPC boundary is invalid")
        self._rpc = rpc

    async def _state(self, reference: ConnectedPayloadRef) -> tuple[str, object | None]:
        result = await _rpc(
            self._rpc,
            "connected_app_payload_read_v1",
            {
                "p_payload_id": reference.payload_id,
                "p_identity_sha256": reference.identity_sha256,
            },
        )
        envelope = _object(result, frozenset({"status", "record"}))
        status = envelope["status"]
        if status not in {"absent", "erased", "present"}:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        if (status == "present") is (envelope["record"] is None):
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        return status, envelope["record"]

    async def put_once(self, record: EncryptedConnectedPayload) -> EncryptedConnectedPayload | None:
        if not isinstance(record, EncryptedConnectedPayload):
            raise TypeError("record must be EncryptedConnectedPayload")
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_payload_put_v1",
                _payload_parameters(record),
            )
        except ConnectedDurableStoreError:
            status, value = await self._state(record.reference)
            if status == "erased":
                return None
            if status != "present":
                raise ConnectedDurableStoreError("CONNECTED_STORE_AMBIGUOUS") from None
            stored = _payload_record(value)
            if stored.reference.identity_sha256 != record.reference.identity_sha256:
                raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
            return stored
        envelope = _object(result, frozenset({"status", "record"}))
        if envelope["status"] == "erased" and envelope["record"] is None:
            return None
        if envelope["status"] != "present" or envelope["record"] is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        stored = _payload_record(envelope["record"])
        if stored.reference.identity_sha256 != record.reference.identity_sha256:
            raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
        return stored

    async def resolve_reference(
        self,
        *,
        owner_id: str,
        payload_id: str,
        connection_id: str,
        action_id: str,
        provider: ConnectorProvider,
        action: ConnectorActionKind,
    ) -> ConnectedPayloadRef | None:
        expected_owner = _uuid(owner_id, "owner_id")
        expected_payload = _uuid(payload_id, "payload_id")
        expected_connection = _uuid(connection_id, "connection_id")
        expected_action_id = _uuid(action_id, "action_id")
        if not isinstance(provider, ConnectorProvider) or not isinstance(
            action, ConnectorActionKind
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        result = await _rpc(
            self._rpc,
            "connected_app_payload_reference_get_v1",
            {
                "p_owner_id": expected_owner,
                "p_payload_id": expected_payload,
                "p_connection_id": expected_connection,
                "p_action_id": expected_action_id,
                "p_provider": provider.value,
                "p_action": action.value,
            },
        )
        envelope = _object(result, frozenset({"status", "reference"}))
        if envelope["status"] == "erased" and envelope["reference"] is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_TOMBSTONED")
        if envelope["status"] == "absent" and envelope["reference"] is None:
            return None
        if envelope["status"] != "present" or envelope["reference"] is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        reference = _payload_reference(envelope["reference"])
        if (
            reference.owner_id != expected_owner
            or reference.payload_id != expected_payload
            or reference.connection_id != expected_connection
            or reference.action_id != expected_action_id
            or reference.provider is not provider
            or reference.action is not action
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
        return reference

    async def read(self, reference: ConnectedPayloadRef) -> EncryptedConnectedPayload | None:
        if not isinstance(reference, ConnectedPayloadRef):
            raise TypeError("reference must be ConnectedPayloadRef")
        status, value = await self._state(reference)
        if status != "present":
            return None
        stored = _payload_record(value)
        if stored.reference.identity_sha256 != reference.identity_sha256:
            raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
        return stored

    async def delete_once(self, reference: ConnectedPayloadRef) -> bool:
        if not isinstance(reference, ConnectedPayloadRef):
            raise TypeError("reference must be ConnectedPayloadRef")
        payload = {
            "p_payload_id": reference.payload_id,
            "p_identity_sha256": reference.identity_sha256,
            "p_erased_at": _iso(datetime.now(UTC)),
        }
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_payload_delete_v1",
                payload,
            )
        except ConnectedDurableStoreError:
            # The RPC is permanently idempotent: its tombstone retains the
            # original record_existed result.  Repeating this database-only
            # effect recovers the exact boolean after a lost HTTP response.
            # A state-only readback could prove erasure but could not recover
            # whether this call erased a live record.
            try:
                result = await _rpc(
                    self._rpc,
                    "connected_app_payload_delete_v1",
                    payload,
                )
            except ConnectedDurableStoreError:
                raise ConnectedDurableStoreError("CONNECTED_STORE_AMBIGUOUS") from None
        envelope = _object(result, frozenset({"status", "record_existed"}))
        if envelope["status"] != "erased" or type(envelope["record_existed"]) is not bool:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        return envelope["record_existed"]


_CREDENTIAL_RECORD_KEYS = frozenset(
    {
        "owner_id",
        "connection_id",
        "provider",
        "credential_handle_sha256",
        "connection_incarnation_id",
        "oauth_client_id_sha256",
        "account_kind",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "external_account_id_hash",
        "authorization_expires_at",
        "secret_revision",
        "created_at",
        "updated_at",
        "authority_binding_sha256",
        "metadata_binding_sha256",
        "key_id",
        "wrapped_key_nonce",
        "wrapped_key_ciphertext",
        "secret_nonce",
        "secret_ciphertext",
        "record_binding_sha256",
    }
)


def _credential_record(
    value: object,
    expected: CredentialHandleRef,
) -> EncryptedConnectedCredential:
    row = _object(value, _CREDENTIAL_RECORD_KEYS)
    if not hmac.compare_digest(_sha(row["credential_handle_sha256"]), _handle_sha256(expected)):
        raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
    credential = CredentialHandleRef(
        owner_id=_uuid(row["owner_id"], "owner_id"),
        connection_id=_uuid(row["connection_id"], "connection_id"),
        provider=_enum(ConnectorProvider, row["provider"]),
        handle_id=expected.handle_id,
    )
    if credential != expected:
        raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
    metadata = ConnectedCredentialMetadata(
        credential=credential,
        connection_incarnation_id=_uuid(
            row["connection_incarnation_id"], "connection_incarnation_id"
        ),
        oauth_client_id_sha256=_sha(row["oauth_client_id_sha256"]),
        account_kind=_enum(ConnectorAccountKind, row["account_kind"]),
        authorization_revision=_positive_int(row["authorization_revision"]),
        authorization_snapshot_sha256=_sha(row["authorization_snapshot_sha256"]),
        granted_actions_sha256=_sha(row["granted_actions_sha256"]),
        granted_scopes_sha256=_sha(row["granted_scopes_sha256"]),
        external_account_id_hash=_sha(row["external_account_id_hash"]),
        authorization_expires_at=_time(row["authorization_expires_at"]),
        secret_revision=_positive_int(row["secret_revision"]),
        created_at=_time(row["created_at"]),
        updated_at=_time(row["updated_at"]),
    )
    if not hmac.compare_digest(
        metadata.authority_binding_sha256, _sha(row["authority_binding_sha256"])
    ) or not hmac.compare_digest(metadata.binding_sha256, _sha(row["metadata_binding_sha256"])):
        raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
    try:
        return EncryptedConnectedCredential(
            metadata=metadata,
            key_id=_text(row["key_id"], maximum=64, pattern=_KEY_ID),
            wrapped_key_nonce=_text(row["wrapped_key_nonce"], maximum=64, pattern=_B64URL),
            wrapped_key_ciphertext=_text(
                row["wrapped_key_ciphertext"], maximum=128, pattern=_B64URL
            ),
            secret_nonce=_text(row["secret_nonce"], maximum=64, pattern=_B64URL),
            secret_ciphertext=_text(row["secret_ciphertext"], maximum=65536, pattern=_B64URL),
            record_binding_sha256=_sha(row["record_binding_sha256"]),
        )
    except (TypeError, ValueError):
        raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID") from None


def _credential_parameters(record: EncryptedConnectedCredential) -> dict[str, object]:
    metadata = record.metadata
    credential = metadata.credential
    return {
        "p_owner_id": credential.owner_id,
        "p_connection_id": credential.connection_id,
        "p_provider": credential.provider.value,
        "p_credential_handle_sha256": _handle_sha256(credential),
        "p_connection_incarnation_id": metadata.connection_incarnation_id,
        "p_oauth_client_id_sha256": metadata.oauth_client_id_sha256,
        "p_account_kind": metadata.account_kind.value,
        "p_authorization_revision": metadata.authorization_revision,
        "p_authorization_snapshot_sha256": metadata.authorization_snapshot_sha256,
        "p_granted_actions_sha256": metadata.granted_actions_sha256,
        "p_granted_scopes_sha256": metadata.granted_scopes_sha256,
        "p_external_account_id_hash": metadata.external_account_id_hash,
        "p_authorization_expires_at": _iso(metadata.authorization_expires_at),
        "p_secret_revision": metadata.secret_revision,
        "p_created_at": _iso(metadata.created_at),
        "p_updated_at": _iso(metadata.updated_at),
        "p_authority_binding_sha256": metadata.authority_binding_sha256,
        "p_metadata_binding_sha256": metadata.binding_sha256,
        "p_key_id": record.key_id,
        "p_wrapped_key_nonce": record.wrapped_key_nonce,
        "p_wrapped_key_ciphertext": record.wrapped_key_ciphertext,
        "p_secret_nonce": record.secret_nonce,
        "p_secret_ciphertext": record.secret_ciphertext,
        "p_record_binding_sha256": record.record_binding_sha256,
    }


class SupabaseConnectedCredentialSecretStore(ConnectedCredentialSecretStore):
    """Permanent-tombstone CAS store for encrypted refresh credentials."""

    def __init__(self, rpc: ConnectedStoreRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("connected credential RPC boundary is invalid")
        self._rpc = rpc

    async def _state(self, credential: CredentialHandleRef) -> tuple[str, object | None]:
        result = await _rpc(
            self._rpc,
            "connected_app_credential_read_v1",
            {"p_credential_handle_sha256": _handle_sha256(credential)},
        )
        envelope = _object(result, frozenset({"status", "record"}))
        status = envelope["status"]
        if status not in {"absent", "erased", "present"}:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        if (status == "present") is (envelope["record"] is None):
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        return status, envelope["record"]

    async def create_once(
        self, record: EncryptedConnectedCredential
    ) -> EncryptedConnectedCredential:
        if not isinstance(record, EncryptedConnectedCredential):
            raise TypeError("record must be EncryptedConnectedCredential")
        credential = record.metadata.credential
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_credential_create_v1",
                _credential_parameters(record),
            )
        except ConnectedDurableStoreError:
            status, value = await self._state(credential)
            if status == "erased":
                raise ConnectedDurableStoreError("CONNECTED_STORE_TOMBSTONED") from None
            if status != "present":
                raise ConnectedDurableStoreError("CONNECTED_STORE_AMBIGUOUS") from None
            stored = _credential_record(value, credential)
            if stored.record_binding_sha256 != record.record_binding_sha256:
                raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
            return stored
        envelope = _object(result, frozenset({"status", "record"}))
        if envelope["status"] != "present" or envelope["record"] is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        return _credential_record(envelope["record"], credential)

    async def read(self, credential: CredentialHandleRef) -> EncryptedConnectedCredential | None:
        if not isinstance(credential, CredentialHandleRef):
            raise TypeError("credential must be CredentialHandleRef")
        status, value = await self._state(credential)
        if status != "present":
            return None
        return _credential_record(value, credential)

    async def replace_once(
        self,
        *,
        expected_record_binding_sha256: str,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential:
        expected = _sha(expected_record_binding_sha256)
        if not isinstance(record, EncryptedConnectedCredential):
            raise TypeError("record must be EncryptedConnectedCredential")
        credential = record.metadata.credential
        payload = _credential_parameters(record)
        payload["p_expected_record_binding_sha256"] = expected
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_credential_replace_v1",
                payload,
            )
        except ConnectedDurableStoreError:
            status, value = await self._state(credential)
            if status != "present":
                raise ConnectedDurableStoreError("CONNECTED_STORE_AMBIGUOUS") from None
            stored = _credential_record(value, credential)
            if stored.record_binding_sha256 != record.record_binding_sha256:
                raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
            return stored
        envelope = _object(result, frozenset({"status", "record"}))
        if envelope["status"] != "present" or envelope["record"] is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        return _credential_record(envelope["record"], credential)

    async def delete_once(
        self,
        *,
        credential: CredentialHandleRef,
        expected_record_binding_sha256: str,
    ) -> bool:
        expected = _sha(expected_record_binding_sha256)
        if not isinstance(credential, CredentialHandleRef):
            raise TypeError("credential must be CredentialHandleRef")
        payload = {
            "p_credential_handle_sha256": _handle_sha256(credential),
            "p_expected_record_binding_sha256": expected,
            "p_erased_at": _iso(datetime.now(UTC)),
        }
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_credential_delete_v1",
                payload,
            )
        except ConnectedDurableStoreError:
            # The tombstone preserves record_existed, so an exact retry is a
            # readback of the committed outcome rather than a second delete.
            try:
                result = await _rpc(
                    self._rpc,
                    "connected_app_credential_delete_v1",
                    payload,
                )
            except ConnectedDurableStoreError:
                raise ConnectedDurableStoreError("CONNECTED_STORE_AMBIGUOUS") from None
        envelope = _object(result, frozenset({"status", "record_existed"}))
        if envelope["status"] != "erased" or type(envelope["record_existed"]) is not bool:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        return envelope["record_existed"]


@dataclass(frozen=True, slots=True)
class ConnectedCredentialRefreshLease:
    credential_handle_sha256: str
    lease_id: str
    expected_record_binding_sha256: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "credential_handle_sha256", _sha(self.credential_handle_sha256))
        object.__setattr__(self, "lease_id", _uuid(self.lease_id, "lease_id"))
        object.__setattr__(
            self,
            "expected_record_binding_sha256",
            _sha(self.expected_record_binding_sha256),
        )
        issued = self.issued_at
        expires = self.expires_at
        if (
            not isinstance(issued, datetime)
            or issued.tzinfo is None
            or not isinstance(expires, datetime)
            or expires.tzinfo is None
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        issued = issued.astimezone(UTC)
        expires = expires.astimezone(UTC)
        if expires <= issued or expires - issued > _MAX_LEASE:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires.astimezone(UTC))


class SupabaseConnectedCredentialRefreshCoordinator:
    """Cross-host lease for refresh-token rotation serialization.

    Callers must re-open the credential after claiming because an earlier host
    may have rotated the refresh token before releasing or losing its lease.
    """

    def __init__(self, rpc: ConnectedStoreRPC, *, now: Any | None = None) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("connected refresh RPC boundary is invalid")
        self._rpc = rpc
        self._now = now or (lambda: datetime.now(UTC))

    async def claim(
        self,
        *,
        credential: CredentialHandleRef,
        expected_record_binding_sha256: str,
        lease_for: timedelta = timedelta(seconds=15),
    ) -> ConnectedCredentialRefreshLease:
        if (
            not isinstance(credential, CredentialHandleRef)
            or not isinstance(lease_for, timedelta)
            or lease_for <= timedelta(0)
            or lease_for > _MAX_LEASE
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        issued_at = self._now()
        if not isinstance(issued_at, datetime) or issued_at.tzinfo is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        issued_at = issued_at.astimezone(UTC)
        lease_id = str(uuid4())
        expected = _sha(expected_record_binding_sha256)
        payload = {
            "p_credential_handle_sha256": _handle_sha256(credential),
            "p_expected_record_binding_sha256": expected,
            "p_lease_id": lease_id,
            "p_lease_seconds": int(lease_for.total_seconds()),
        }
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_credential_claim_refresh_v2",
                payload,
            )
        except ConnectedDurableStoreError:
            # Same lease ID is an idempotency key.  The database returns the
            # existing exact lease if the first response was lost.
            try:
                result = await _rpc(
                    self._rpc,
                    "connected_app_credential_claim_refresh_v2",
                    payload,
                )
            except ConnectedDurableStoreError:
                raise ConnectedDurableStoreError("CONNECTED_STORE_AMBIGUOUS") from None
        envelope = _object(
            result,
            frozenset(
                {
                    "status",
                    "credential_handle_sha256",
                    "lease_id",
                    "expected_record_binding_sha256",
                    "issued_at",
                    "expires_at",
                }
            ),
        )
        if envelope["status"] == "busy":
            raise ConnectedDurableStoreError("CONNECTED_STORE_BUSY")
        if envelope["status"] == "stale":
            raise ConnectedDurableStoreError("CONNECTED_STORE_TOMBSTONED")
        if envelope["status"] != "claimed":
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        lease = ConnectedCredentialRefreshLease(
            credential_handle_sha256=_sha(envelope["credential_handle_sha256"]),
            lease_id=_uuid(envelope["lease_id"], "lease_id"),
            expected_record_binding_sha256=_sha(envelope["expected_record_binding_sha256"]),
            issued_at=_time(envelope["issued_at"]),
            expires_at=_time(envelope["expires_at"]),
        )
        if (
            lease.credential_handle_sha256 != _handle_sha256(credential)
            or lease.lease_id != lease_id
            or lease.expected_record_binding_sha256 != expected
            or lease.expires_at - lease.issued_at != lease_for
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
        return lease

    async def finish(self, lease: ConnectedCredentialRefreshLease) -> None:
        if not isinstance(lease, ConnectedCredentialRefreshLease):
            raise TypeError("lease must be ConnectedCredentialRefreshLease")
        payload = {
            "p_credential_handle_sha256": lease.credential_handle_sha256,
            "p_lease_id": lease.lease_id,
            "p_expected_record_binding_sha256": lease.expected_record_binding_sha256,
        }
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_credential_finish_refresh_v2",
                payload,
            )
        except ConnectedDurableStoreError:
            # Exact finish is idempotent; retry once after an ambiguous response.
            result = await _rpc(
                self._rpc,
                "connected_app_credential_finish_refresh_v2",
                payload,
            )
        envelope = _object(result, frozenset({"status", "lease_id"}))
        if envelope["status"] == "stale":
            raise ConnectedDurableStoreError("CONNECTED_STORE_TOMBSTONED")
        if envelope["status"] != "finished" or envelope["lease_id"] != lease.lease_id:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")

    async def commit_rotation(
        self,
        *,
        lease: ConnectedCredentialRefreshLease,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential:
        """Atomically commit a rotated secret only while the exact lease is live.

        The database validates current connection authority, the prior record
        binding, lease ID, and lease deadline in the same transaction that
        replaces ciphertext and permanently retires the lease ID.
        """

        if not isinstance(lease, ConnectedCredentialRefreshLease):
            raise TypeError("lease must be ConnectedCredentialRefreshLease")
        if not isinstance(record, EncryptedConnectedCredential):
            raise TypeError("record must be EncryptedConnectedCredential")
        if (
            _handle_sha256(record.metadata.credential) != lease.credential_handle_sha256
            or record.metadata.secret_revision < 2
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
        payload = _credential_parameters(record)
        payload.update(
            {
                "p_expected_record_binding_sha256": (
                    lease.expected_record_binding_sha256
                ),
                "p_lease_id": lease.lease_id,
            }
        )
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_credential_commit_refresh_v2",
                payload,
            )
        except ConnectedDurableStoreError:
            # The target record binding plus permanent lease history make this
            # an exact readback after response loss, never a second rotation.
            try:
                result = await _rpc(
                    self._rpc,
                    "connected_app_credential_commit_refresh_v2",
                    payload,
                )
            except ConnectedDurableStoreError:
                raise ConnectedDurableStoreError("CONNECTED_STORE_AMBIGUOUS") from None
        envelope = _object(result, frozenset({"status", "record"}))
        if envelope["status"] == "stale" and envelope["record"] is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_TOMBSTONED")
        if envelope["status"] != "present" or envelope["record"] is None:
            raise ConnectedDurableStoreError("CONNECTED_STORE_INVALID")
        stored = _credential_record(envelope["record"], record.metadata.credential)
        if not hmac.compare_digest(
            stored.record_binding_sha256,
            record.record_binding_sha256,
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
        return stored

    async def quarantine(self, lease: ConnectedCredentialRefreshLease) -> None:
        """Permanently fence an ambiguous rotating refresh-token outcome."""

        if not isinstance(lease, ConnectedCredentialRefreshLease):
            raise TypeError("lease must be ConnectedCredentialRefreshLease")
        payload = {
            "p_credential_handle_sha256": lease.credential_handle_sha256,
            "p_lease_id": lease.lease_id,
            "p_expected_record_binding_sha256": (lease.expected_record_binding_sha256),
        }
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_credential_quarantine_refresh_v2",
                payload,
            )
        except ConnectedDurableStoreError:
            # Exact replay is a readback of the permanent quarantine row. It
            # must never fall through to finish/release this lease.
            result = await _rpc(
                self._rpc,
                "connected_app_credential_quarantine_refresh_v2",
                payload,
            )
        envelope = _object(
            result,
            frozenset(
                {
                    "status",
                    "credential_handle_sha256",
                    "lease_id",
                    "expected_record_binding_sha256",
                    "quarantined_at",
                }
            ),
        )
        if (
            envelope["status"] != "quarantined"
            or envelope["credential_handle_sha256"] != lease.credential_handle_sha256
            or envelope["lease_id"] != lease.lease_id
            or envelope["expected_record_binding_sha256"] != lease.expected_record_binding_sha256
        ):
            raise ConnectedDurableStoreError("CONNECTED_STORE_BINDING_MISMATCH")
        _time(envelope["quarantined_at"])
