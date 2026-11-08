"""Restart-safe Supabase repositories for the reviewed connected OAuth core.

Only service-role RPCs cross this module.  Provider authorization codes,
access tokens, refresh tokens, and raw exchange-permit capabilities never enter
ordinary application tables.  The short-lived exchange capability is envelope
encrypted and atomically stored beside the digest-only permit row; the fresh
dispatch winner erases that envelope in the same database transaction.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .connected_app_contracts import (
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from .connected_app_durable_oauth import (
    ConnectedOAuthMasterKey,
    SupabaseOAuthSecretStore,
)
from .connected_app_oauth import (
    OAuthCompletion,
    OAuthCompletionCommand,
    OAuthCompletionInactive,
    OAuthCompletionRepository,
    OAuthCompletionResponseLost,
    OAuthConsumeCommand,
    OAuthConsumeResponseLost,
    OAuthContractError,
    OAuthCredentialCleanupCommand,
    OAuthCredentialCleanupReceipt,
    OAuthCredentialCleanupResponseLost,
    OAuthExchangeCommand,
    OAuthExchangePermit,
    OAuthExchangePermitClaim,
    OAuthExchangePermitRecord,
    OAuthExchangePermitResponseLost,
    OAuthFlowConsumption,
    OAuthFlowCreateResponseLost,
    OAuthFlowRecord,
    OAuthFlowRepository,
    OAuthFlowState,
    _EXCHANGE_PERMIT_FACTORY_KEY,
    _exchange_permit_capability_sha256,
    _issue_exchange_permit,
)
from .connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from .connected_app_runtime import ConnectedAccountBinding, ConnectedAccountRegistry
from .connected_app_scopes import delegated_scope_plan


class ConnectedOAuthRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class ConnectedOAuthRepositoryError(RuntimeError):
    """Fixed, content-free repository failure."""

    _ALLOWED = frozenset(
        {
            "OAUTH_REPOSITORY_AMBIGUOUS",
            "OAUTH_REPOSITORY_BINDING_MISMATCH",
            "OAUTH_REPOSITORY_CORRUPT",
            "OAUTH_REPOSITORY_INVALID",
            "OAUTH_REPOSITORY_KEY_UNAVAILABLE",
            "OAUTH_REPOSITORY_UNAVAILABLE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid OAuth repository error code")
        self.code = code
        super().__init__(code)


_SHA256 = frozenset("0123456789abcdef")
_PERMIT_ENVELOPE_VERSION = "connected-oauth-exchange-permit-envelope-v1"


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    try:
        canonical = str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID") from None
    if canonical != value:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    return canonical


def _sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256 for character in value)
    ):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    return value


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Mapping[str, object]) -> str:
    return _digest(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    return parsed.astimezone(UTC)


def _optional_time(value: object) -> datetime | None:
    return None if value is None else _time(value)


def _iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    return value.astimezone(UTC).isoformat()


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    return value  # type: ignore[return-value]


def _enum(enum_type: type[Any], value: object) -> Any:
    if not isinstance(value, str):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    try:
        return enum_type(value)
    except ValueError:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID") from None


def _actions(value: object) -> frozenset[ConnectorActionKind]:
    if not isinstance(value, list) or not value:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    result = frozenset(_enum(ConnectorActionKind, item) for item in value)
    if len(result) != len(value):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
    return result


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: object, *, size: int | None = None, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > maximum * 2:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_CORRUPT")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_CORRUPT") from None
    if (size is not None and len(decoded) != size) or not 1 <= len(decoded) <= maximum:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_CORRUPT")
    if _b64(decoded) != value:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_CORRUPT")
    return decoded


async def _rpc(
    rpc: ConnectedOAuthRPC,
    name: str,
    payload: dict[str, object],
    *,
    read: bool,
) -> object:
    try:
        return await rpc.rpc(name, payload, retry_transient=read)
    except ConnectedOAuthRepositoryError:
        raise
    except Exception:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_UNAVAILABLE") from None


_FLOW_KEYS = frozenset(
    {
        "flow_id",
        "nonce_id",
        "owner_id",
        "connection_id",
        "connection_incarnation_id",
        "expected_base_revision",
        "current_flow_nonce_sha256",
        "session_binding_sha256",
        "provider",
        "resource",
        "account_kind",
        "actions",
        "actions_sha256",
        "requested_scopes_sha256",
        "state_sha256",
        "pkce_challenge",
        "redirect_uri_sha256",
        "flow_binding_sha256",
        "status",
        "consumption_id",
        "consume_binding_sha256",
        "consumed_at",
        "created_at",
        "expires_at",
    }
)
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
_CUSTODY_KEYS = frozenset(
    {
        "permit_id",
        "exchange_binding_sha256",
        "permit_binding_sha256",
        "capability_sha256",
        "key_id",
        "wrapped_key_nonce",
        "wrapped_key_ciphertext",
        "secret_nonce",
        "secret_ciphertext",
        "record_binding_sha256",
        "created_at",
        "expires_at",
    }
)
_PERMIT_WRITE_KEYS = frozenset({"permit", "custody"})
_PERMIT_CLAIM_KEYS = frozenset(
    {
        "claimed",
        "status",
        "permit_id",
        "exchange_binding_sha256",
        "permit_binding_sha256",
        "consumed_at",
    }
)
_ACTIVE_COMPLETION_KEYS = frozenset(
    {
        "completed",
        "active",
        "owner_id",
        "connection_id",
        "connection_incarnation_id",
        "consumption_id",
        "exchange_id",
        "completion_id",
        "completion_binding_sha256",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "authorization_issued_at",
        "granted_actions",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "external_account_id_sha256",
        "broker_credential_ref",
        "credential_ref_sha256",
        "authorization_expires_at",
    }
)
_INACTIVE_COMPLETION_KEYS = frozenset(
    {
        "completed",
        "active",
        "completion_id",
        "completion_binding_sha256",
        "connection_id",
        "observed_at",
        "reason",
    }
)
_CLEANUP_KEYS = frozenset({"cleanup_id", "cleanup_binding_sha256", "recorded_at"})
_BINDING_KEYS = frozenset(
    {
        "owner_id",
        "connection_id",
        "provider",
        "resource",
        "account_kind",
        "connection_incarnation_id",
        "authorization_revision",
        "authorization_state",
        "authorization_snapshot_sha256",
        "authorization_issued_at",
        "granted_actions",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "external_account_id_sha256",
        "broker_credential_ref",
        "credential_ref_sha256",
        "current_flow_nonce_sha256",
        "authorization_expires_at",
        "revoked_at",
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class _EncryptedPermitCapability:
    permit_id: str
    exchange_binding_sha256: str
    permit_binding_sha256: str
    capability_sha256: str
    key_id: str
    wrapped_key_nonce: str
    wrapped_key_ciphertext: str
    secret_nonce: str
    secret_ciphertext: str
    record_binding_sha256: str
    created_at: datetime
    expires_at: datetime

    @property
    def expected_record_binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _PERMIT_ENVELOPE_VERSION,
                "permit_id": self.permit_id,
                "exchange_binding_sha256": self.exchange_binding_sha256,
                "permit_binding_sha256": self.permit_binding_sha256,
                "capability_sha256": self.capability_sha256,
                "key_id": self.key_id,
                "wrapped_key_nonce": self.wrapped_key_nonce,
                "wrapped_key_ciphertext": self.wrapped_key_ciphertext,
                "secret_nonce": self.secret_nonce,
                "secret_ciphertext": self.secret_ciphertext,
                "created_at": _iso(self.created_at),
                "expires_at": _iso(self.expires_at),
            }
        )

    def __repr__(self) -> str:
        return (
            "_EncryptedPermitCapability("
            f"permit_id={self.permit_id!r}, key_id={self.key_id!r}, secret='<redacted>')"
        )


def _permit_aad(record: _EncryptedPermitCapability) -> bytes:
    return json.dumps(
        {
            "version": _PERMIT_ENVELOPE_VERSION,
            "permit_id": record.permit_id,
            "exchange_binding_sha256": record.exchange_binding_sha256,
            "permit_binding_sha256": record.permit_binding_sha256,
            "capability_sha256": record.capability_sha256,
            "created_at": _iso(record.created_at),
            "expires_at": _iso(record.expires_at),
        },
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _seal_permit(
    *,
    record: OAuthExchangePermitRecord,
    capability_secret: str,
    key: ConnectedOAuthMasterKey,
) -> _EncryptedPermitCapability:
    data_key = secrets.token_bytes(32)
    wrap_nonce = secrets.token_bytes(12)
    secret_nonce = secrets.token_bytes(12)
    shell = _EncryptedPermitCapability(
        permit_id=record.permit_id,
        exchange_binding_sha256=record.exchange_binding_sha256,
        permit_binding_sha256=record.binding_sha256,
        capability_sha256=record.capability_sha256,
        key_id=key.key_id,
        wrapped_key_nonce="pending",
        wrapped_key_ciphertext="pending",
        secret_nonce="pending",
        secret_ciphertext="pending",
        record_binding_sha256="0" * 64,
        created_at=record.issued_at,
        expires_at=record.expires_at,
    )
    aad = _permit_aad(shell)
    wrapped = AESGCM(key._key).encrypt(wrap_nonce, data_key, aad + b"|wrap")
    ciphertext = AESGCM(data_key).encrypt(
        secret_nonce, capability_secret.encode("ascii"), aad + b"|secret"
    )
    envelope = _EncryptedPermitCapability(
        permit_id=shell.permit_id,
        exchange_binding_sha256=shell.exchange_binding_sha256,
        permit_binding_sha256=shell.permit_binding_sha256,
        capability_sha256=shell.capability_sha256,
        key_id=shell.key_id,
        wrapped_key_nonce=_b64(wrap_nonce),
        wrapped_key_ciphertext=_b64(wrapped),
        secret_nonce=_b64(secret_nonce),
        secret_ciphertext=_b64(ciphertext),
        record_binding_sha256="0" * 64,
        created_at=shell.created_at,
        expires_at=shell.expires_at,
    )
    return replace(
        envelope,
        record_binding_sha256=envelope.expected_record_binding_sha256,
    )


def _custody(value: object) -> _EncryptedPermitCapability:
    row = _object(value, _CUSTODY_KEYS)
    record = _EncryptedPermitCapability(
        permit_id=_uuid(row["permit_id"], "permit_id"),
        exchange_binding_sha256=_sha(row["exchange_binding_sha256"]),
        permit_binding_sha256=_sha(row["permit_binding_sha256"]),
        capability_sha256=_sha(row["capability_sha256"]),
        key_id=str(row["key_id"]),
        wrapped_key_nonce=str(row["wrapped_key_nonce"]),
        wrapped_key_ciphertext=str(row["wrapped_key_ciphertext"]),
        secret_nonce=str(row["secret_nonce"]),
        secret_ciphertext=str(row["secret_ciphertext"]),
        record_binding_sha256=_sha(row["record_binding_sha256"]),
        created_at=_time(row["created_at"]),
        expires_at=_time(row["expires_at"]),
    )
    if not hmac.compare_digest(record.record_binding_sha256, record.expected_record_binding_sha256):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
    return record


def _open_permit(
    record: _EncryptedPermitCapability,
    *,
    keys: Mapping[str, ConnectedOAuthMasterKey],
) -> str:
    key = keys.get(record.key_id)
    if key is None:
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_KEY_UNAVAILABLE")
    aad = _permit_aad(record)
    try:
        data_key = AESGCM(key._key).decrypt(
            _unb64(record.wrapped_key_nonce, size=12, maximum=12),
            _unb64(record.wrapped_key_ciphertext, size=48, maximum=48),
            aad + b"|wrap",
        )
        plaintext = AESGCM(data_key).decrypt(
            _unb64(record.secret_nonce, size=12, maximum=12),
            _unb64(record.secret_ciphertext, maximum=256),
            aad + b"|secret",
        )
        capability = plaintext.decode("ascii")
    except (InvalidTag, UnicodeDecodeError, ValueError):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_CORRUPT") from None
    if not hmac.compare_digest(_digest(capability), record.capability_sha256):
        raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
    return capability


class SupabaseOAuthFlowRepository(OAuthFlowRepository):
    """Concrete live-authority flow/permit repository over attested RPCs."""

    def __init__(
        self,
        *,
        database: ConnectedOAuthRPC,
        redirect_uris: Mapping[ConnectorProvider, str],
        permit_keys: Mapping[str, ConnectedOAuthMasterKey],
        active_permit_key_id: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(getattr(database, "rpc", None)) or not callable(now):
            raise TypeError("OAuth flow repository dependency is invalid")
        if not redirect_uris or not permit_keys or active_permit_key_id not in permit_keys:
            raise ValueError("OAuth flow repository configuration is incomplete")
        if any(key.key_id != key_id for key_id, key in permit_keys.items()):
            raise ValueError("OAuth permit key mapping is invalid")
        self._database = database
        self._redirect_uris = dict(redirect_uris)
        self._permit_keys = dict(permit_keys)
        self._active_permit_key_id = active_permit_key_id
        self._now = now

    def _flow(self, value: object) -> OAuthFlowRecord:
        row = _object(value, _FLOW_KEYS)
        provider = _enum(ConnectorProvider, row["provider"])
        resource = _enum(ConnectorResource, row["resource"])
        account_kind = _enum(ConnectorAccountKind, row["account_kind"])
        actions = _actions(row["actions"])
        redirect_uri = self._redirect_uris.get(provider)
        if not isinstance(redirect_uri, str) or not hmac.compare_digest(
            _digest(redirect_uri), _sha(row["redirect_uri_sha256"])
        ):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        plan = delegated_scope_plan(provider, actions, account_kind=account_kind)
        scopes = frozenset(plan.delegated_scopes)
        status = row["status"]
        if status == "pending":
            state = OAuthFlowState.PENDING
            consumed_at = None
        elif status in {"consumed", "exchanged", "completed"}:
            state = OAuthFlowState.CONSUMED
            consumed_at = _time(row["consumed_at"])
        else:
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        try:
            flow = OAuthFlowRecord(
                flow_id=_uuid(row["flow_id"], "flow_id"),
                nonce_id=_uuid(row["nonce_id"], "nonce_id"),
                owner_id=_uuid(row["owner_id"], "owner_id"),
                connection_id=_uuid(row["connection_id"], "connection_id"),
                connection_incarnation_id=_uuid(
                    row["connection_incarnation_id"], "connection_incarnation_id"
                ),
                expected_base_revision=int(row["expected_base_revision"]),
                current_flow_nonce_sha256=_sha(row["current_flow_nonce_sha256"]),
                session_binding_sha256=_sha(row["session_binding_sha256"]),
                provider=provider,
                resource=resource,
                account_kind=account_kind,
                actions=actions,
                actions_sha256=_sha(row["actions_sha256"]),
                requested_scopes=scopes,
                requested_scopes_sha256=_sha(row["requested_scopes_sha256"]),
                state_sha256=_sha(row["state_sha256"]),
                pkce_challenge=str(row["pkce_challenge"]),
                broker_flow_binding_sha256=_sha(row["flow_binding_sha256"]),
                redirect_uri=redirect_uri,
                created_at=_time(row["created_at"]),
                expires_at=_time(row["expires_at"]),
                state=state,
                consumed_at=consumed_at,
            )
        except (TypeError, ValueError):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH") from None
        return flow

    def decode_flow(self, value: object) -> OAuthFlowRecord:
        """Decode one exact RPC flow row for a trusted composition adapter.

        Callback lookup belongs to the operator bridge, while flow validation
        belongs here.  Keeping one decoder prevents those two service-role
        adapters from interpreting the same durable authority differently.
        """

        return self._flow(value)

    async def _read_flow(self, flow_id: str, binding: str) -> object:
        return await _rpc(
            self._database,
            "connected_app_oauth_revalidate_flow_v2",
            {
                "p_flow_id": _uuid(flow_id, "flow_id"),
                "p_expected_flow_binding_sha256": _sha(binding),
            },
            read=True,
        )

    async def create_pending(self, flow: OAuthFlowRecord) -> None:
        if not isinstance(flow, OAuthFlowRecord) or flow.state is not OAuthFlowState.PENDING:
            raise TypeError("flow must be a pending OAuthFlowRecord")
        payload = {
            "p_flow_id": flow.flow_id,
            "p_nonce_id": flow.nonce_id,
            "p_owner_id": flow.owner_id,
            "p_connection_id": flow.connection_id,
            "p_connection_incarnation_id": flow.connection_incarnation_id,
            "p_expected_base_revision": flow.expected_base_revision,
            "p_current_flow_nonce_sha256": flow.current_flow_nonce_sha256,
            "p_session_binding_sha256": flow.session_binding_sha256,
            "p_provider": flow.provider.value,
            "p_resource": flow.resource.value,
            "p_account_kind": flow.account_kind.value,
            "p_actions": sorted(action.value for action in flow.actions),
            "p_actions_sha256": flow.actions_sha256,
            "p_requested_scopes_sha256": flow.requested_scopes_sha256,
            "p_state_sha256": flow.state_sha256,
            "p_pkce_challenge": flow.pkce_challenge,
            "p_redirect_uri_sha256": _digest(flow.redirect_uri),
            "p_flow_binding_sha256": flow.binding_sha256,
            "p_broker_start_receipt_sha256": _canonical_hash(
                {
                    "version": "connected-oauth-broker-start-attestation-v1",
                    "flow_binding_sha256": flow.binding_sha256,
                }
            ),
            "p_created_at": _iso(flow.created_at),
            "p_expires_at": _iso(flow.expires_at),
        }
        try:
            await _rpc(
                self._database,
                "connected_app_oauth_create_pending_v1",
                payload,
                read=False,
            )
        except ConnectedOAuthRepositoryError:
            try:
                existing = await self.read_pending(
                    flow_id=flow.flow_id,
                    expected_flow_binding_sha256=flow.binding_sha256,
                )
            except ConnectedOAuthRepositoryError:
                existing = None
            if existing == flow:
                return
            raise OAuthFlowCreateResponseLost() from None

    async def read_pending(
        self, *, flow_id: str, expected_flow_binding_sha256: str
    ) -> OAuthFlowRecord | None:
        value = await self._read_flow(flow_id, expected_flow_binding_sha256)
        if value is None:
            return None
        row = _object(value, _FLOW_KEYS)
        if row["status"] != "pending":
            return None
        return self._flow(row)

    async def revalidate_pending(self, flow: OAuthFlowRecord) -> OAuthFlowRecord:
        if not isinstance(flow, OAuthFlowRecord):
            raise TypeError("flow must be OAuthFlowRecord")
        value = await self._read_flow(flow.flow_id, flow.binding_sha256)
        if value is None:
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        current = self._flow(value)
        if current.state is not OAuthFlowState.PENDING or current != flow:
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        return current

    @staticmethod
    def _consumption(value: object) -> OAuthFlowConsumption:
        row = _object(value, _CONSUMPTION_KEYS)
        try:
            return OAuthFlowConsumption(
                consumption_id=_uuid(row["consumption_id"], "consumption_id"),
                flow_id=_uuid(row["flow_id"], "flow_id"),
                connection_id=_uuid(row["connection_id"], "connection_id"),
                connection_incarnation_id=_uuid(
                    row["connection_incarnation_id"], "connection_incarnation_id"
                ),
                expected_base_revision=int(row["expected_base_revision"]),
                current_flow_nonce_sha256=_sha(row["current_flow_nonce_sha256"]),
                consume_binding_sha256=_sha(row["consume_binding_sha256"]),
                flow_binding_sha256=_sha(row["flow_binding_sha256"]),
                consumed_at=_time(row["consumed_at"]),
            )
        except (TypeError, ValueError):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH") from None

    async def consume_pending(self, command: OAuthConsumeCommand) -> OAuthFlowConsumption:
        if not isinstance(command, OAuthConsumeCommand):
            raise TypeError("command must be OAuthConsumeCommand")
        try:
            await _rpc(
                self._database,
                "connected_app_oauth_consume_pending_v1",
                {
                    "p_flow_id": command.flow_id,
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
        except ConnectedOAuthRepositoryError:
            recovered = await self.read_consumption(command)
            if recovered is None:
                raise OAuthConsumeResponseLost() from None
            return recovered
        recovered = await self.read_consumption(command)
        if recovered is None:
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_AMBIGUOUS")
        return recovered

    async def read_consumption(self, command: OAuthConsumeCommand) -> OAuthFlowConsumption | None:
        if not isinstance(command, OAuthConsumeCommand):
            raise TypeError("command must be OAuthConsumeCommand")
        # Revalidate live connection authority before detached consumption readback.
        await self._read_flow(command.flow_id, command.flow_binding_sha256)
        value = await _rpc(
            self._database,
            "connected_app_oauth_read_consumption_v2",
            {
                "p_flow_id": command.flow_id,
                "p_consumption_id": command.consumption_id,
                "p_flow_binding_sha256": command.flow_binding_sha256,
                "p_consume_binding_sha256": command.binding_sha256,
            },
            read=True,
        )
        return None if value is None else self._consumption(value)

    def _envelope_for_record(
        self, record: OAuthExchangePermitRecord, permit: OAuthExchangePermit
    ) -> _EncryptedPermitCapability:
        key = self._permit_keys[self._active_permit_key_id]
        return _seal_permit(
            record=record,
            capability_secret=permit._capability_secret,
            key=key,
        )

    async def issue_exchange_permit_once(
        self, command: OAuthExchangeCommand
    ) -> OAuthExchangePermit:
        if not isinstance(command, OAuthExchangeCommand):
            raise TypeError("command must be OAuthExchangeCommand")
        record, permit = _issue_exchange_permit(command, issued_at=self._now())
        envelope = self._envelope_for_record(record, permit)
        payload = {
            "p_permit_id": record.permit_id,
            "p_flow_id": command.flow_id,
            "p_connection_id": command.connection_id,
            "p_exchange_id": command.exchange_id,
            "p_capability_sha256": record.capability_sha256,
            "p_permit_binding_sha256": record.binding_sha256,
            "p_exchange_binding_sha256": command.binding_sha256,
            "p_issued_at": _iso(record.issued_at),
            "p_deadline_at": _iso(record.expires_at),
            "p_key_id": envelope.key_id,
            "p_wrapped_key_nonce": envelope.wrapped_key_nonce,
            "p_wrapped_key_ciphertext": envelope.wrapped_key_ciphertext,
            "p_secret_nonce": envelope.secret_nonce,
            "p_secret_ciphertext": envelope.secret_ciphertext,
            "p_record_binding_sha256": envelope.record_binding_sha256,
        }
        try:
            value = await _rpc(
                self._database,
                "connected_app_oauth_put_permit_capability_v2",
                payload,
                read=False,
            )
        except ConnectedOAuthRepositoryError:
            recovered = await self.read_exchange_permit(command)
            if recovered is not None:
                return recovered
            raise OAuthExchangePermitResponseLost() from None
        row = _object(value, _PERMIT_WRITE_KEYS)
        stored = _custody(row["custody"])
        if (
            stored.record_binding_sha256 != envelope.record_binding_sha256
            or stored.permit_binding_sha256 != record.binding_sha256
            or stored.exchange_binding_sha256 != command.binding_sha256
        ):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        return permit

    async def read_exchange_permit(
        self, command: OAuthExchangeCommand
    ) -> OAuthExchangePermit | None:
        if not isinstance(command, OAuthExchangeCommand):
            raise TypeError("command must be OAuthExchangeCommand")
        value = await _rpc(
            self._database,
            "connected_app_oauth_read_permit_capability_v2",
            {
                "p_permit_id": command.exchange_id,
                "p_exchange_binding_sha256": command.binding_sha256,
            },
            read=True,
        )
        if value is None:
            return None
        envelope = _custody(value)
        capability = _open_permit(envelope, keys=self._permit_keys)
        record = OAuthExchangePermitRecord(
            permit_id=command.exchange_id,
            exchange_id=command.exchange_id,
            consumption_id=command.consumption_id,
            nonce_id=command.nonce_id,
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
            session_binding_sha256=command.session_binding_sha256,
            provider=command.provider,
            resource=command.resource,
            account_kind=command.account_kind,
            flow_binding_sha256=command.flow_binding_sha256,
            consume_binding_sha256=command.consume_binding_sha256,
            exchange_binding_sha256=command.binding_sha256,
            capability_sha256=envelope.capability_sha256,
            issued_at=envelope.created_at,
            expires_at=envelope.expires_at,
        )
        if not hmac.compare_digest(record.binding_sha256, envelope.permit_binding_sha256):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        return OAuthExchangePermit(
            permit_id=record.permit_id,
            exchange_binding_sha256=record.exchange_binding_sha256,
            permit_binding_sha256=record.binding_sha256,
            capability_secret=capability,
            _factory_key=_EXCHANGE_PERMIT_FACTORY_KEY,
        )

    async def consume_exchange_permit_for_dispatch(
        self, command: OAuthExchangeCommand, permit: OAuthExchangePermit
    ) -> OAuthExchangePermitClaim:
        if not isinstance(command, OAuthExchangeCommand) or not isinstance(
            permit, OAuthExchangePermit
        ):
            raise TypeError("exact exchange command and permit are required")
        value = await _rpc(
            self._database,
            "connected_app_oauth_consume_permit_v2",
            {
                "p_permit_id": permit.permit_id,
                "p_flow_id": command.flow_id,
                "p_connection_id": command.connection_id,
                "p_exchange_id": command.exchange_id,
                "p_capability_sha256": _exchange_permit_capability_sha256(permit),
                "p_permit_binding_sha256": permit.permit_binding_sha256,
                "p_exchange_binding_sha256": command.binding_sha256,
                "p_dispatch_fence_id": command.exchange_id,
            },
            read=False,
        )
        row = _object(value, _PERMIT_CLAIM_KEYS)
        if row["status"] == "expired":
            raise OAuthContractError("OAUTH_EXCHANGE_DEADLINE_EXPIRED")
        if row["claimed"] is not True or row["status"] != "attempt_fenced":
            raise OAuthContractError("OAUTH_EXCHANGE_RECOVERY_REQUIRED")
        try:
            return OAuthExchangePermitClaim(
                permit_id=_uuid(row["permit_id"], "permit_id"),
                exchange_binding_sha256=_sha(row["exchange_binding_sha256"]),
                permit_binding_sha256=_sha(row["permit_binding_sha256"]),
                consumed_at=_time(row["consumed_at"]),
            )
        except (TypeError, ValueError):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH") from None


class SupabaseOAuthCompletionRepository(OAuthCompletionRepository):
    """Atomic completion, replay, and cleanup repository."""

    def __init__(self, database: ConnectedOAuthRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("OAuth completion RPC boundary is invalid")
        self._database = database

    @staticmethod
    def _authorization(command: OAuthCompletionCommand) -> ConnectedAuthorizationSnapshot:
        return ConnectedAuthorizationSnapshot.build(
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            provider=command.provider,
            resource=command.resource,
            account_kind=command.account_kind,
            revision=command.expected_base_revision + 1,
            granted_actions=command.granted_actions,
            granted_scopes=command.granted_scopes,
            state=ConnectionAuthorizationState.ACTIVE,
            issued_at=command.issued_at,
            expires_at=command.expires_at,
        )

    @classmethod
    def _completion(
        cls, value: object, command: OAuthCompletionCommand
    ) -> OAuthCompletion | OAuthCompletionInactive:
        if type(value) is not dict:
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_INVALID")
        if value.get("active") is False:
            row = _object(value, _INACTIVE_COMPLETION_KEYS)
            if row["completed"] is not False or row["active"] is not False:
                raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
            try:
                return OAuthCompletionInactive(
                    completion_id=_uuid(row["completion_id"], "completion_id"),
                    completion_binding_sha256=_sha(row["completion_binding_sha256"]),
                    connection_id=_uuid(row["connection_id"], "connection_id"),
                    observed_at=_time(row["observed_at"]),
                    reason=str(row["reason"]),
                )
            except (TypeError, ValueError):
                raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH") from None
        row = _object(value, _ACTIVE_COMPLETION_KEYS)
        authorization = cls._authorization(command)
        actions = _actions(row["granted_actions"])
        credential = CredentialHandleRef(
            owner_id=_uuid(row["owner_id"], "owner_id"),
            connection_id=_uuid(row["connection_id"], "connection_id"),
            provider=command.provider,
            handle_id=_uuid(row["broker_credential_ref"], "broker_credential_ref"),
        )
        checks = (
            row["completed"] is True,
            row["active"] is True,
            _uuid(row["completion_id"], "completion_id") == command.completion_id,
            _uuid(row["consumption_id"], "consumption_id") == command.consumption_id,
            _uuid(row["exchange_id"], "exchange_id") == command.exchange_id,
            _uuid(row["connection_incarnation_id"], "connection_incarnation_id")
            == command.connection_incarnation_id,
            _sha(row["completion_binding_sha256"]) == command.binding_sha256,
            int(row["authorization_revision"]) == authorization.revision,
            _sha(row["authorization_snapshot_sha256"]) == authorization.snapshot_sha256,
            _time(row["authorization_issued_at"]) == authorization.issued_at,
            _time(row["authorization_expires_at"]) == authorization.expires_at,
            actions == authorization.granted_actions,
            _sha(row["granted_actions_sha256"]) == authorization.granted_actions_sha256,
            _sha(row["granted_scopes_sha256"]) == authorization.granted_scopes_sha256,
            _sha(row["external_account_id_sha256"]) == command.external_account_id_hash,
            _sha(row["credential_ref_sha256"]) == _digest(credential.handle_id),
            credential == command.credential,
        )
        if not all(checks):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        try:
            return OAuthCompletion(
                consumption_id=_uuid(row["consumption_id"], "consumption_id"),
                exchange_id=_uuid(row["exchange_id"], "exchange_id"),
                connection_incarnation_id=_uuid(
                    row["connection_incarnation_id"], "connection_incarnation_id"
                ),
                expected_base_revision=command.expected_base_revision,
                current_flow_nonce_sha256=command.current_flow_nonce_sha256,
                completion_binding_sha256=command.binding_sha256,
                credential=credential,
                external_account_id_hash=_sha(row["external_account_id_sha256"]),
                authorization=authorization,
            )
        except (TypeError, ValueError):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH") from None

    async def read_completion(
        self, command: OAuthCompletionCommand
    ) -> OAuthCompletion | OAuthCompletionInactive | None:
        if not isinstance(command, OAuthCompletionCommand):
            raise TypeError("command must be OAuthCompletionCommand")
        value = await _rpc(
            self._database,
            "connected_app_oauth_read_completion_v3",
            {
                "p_completion_id": command.completion_id,
                "p_completion_binding_sha256": command.binding_sha256,
                "p_owner_id": command.owner_id,
                "p_connection_id": command.connection_id,
            },
            read=True,
        )
        return None if value is None else self._completion(value, command)

    async def complete_once(
        self, command: OAuthCompletionCommand
    ) -> OAuthCompletion | OAuthCompletionInactive:
        if not isinstance(command, OAuthCompletionCommand):
            raise TypeError("command must be OAuthCompletionCommand")
        authorization = self._authorization(command)
        cleanup = OAuthCredentialCleanupCommand(
            cleanup_id=command.exchange_id,
            completion_id=command.completion_id,
            exchange_id=command.exchange_id,
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            provider=command.provider,
            credential=command.credential,
            exchange_binding_sha256=command.exchange_binding_sha256,
            completion_binding_sha256=command.binding_sha256,
        )
        payload = {
            "p_flow_id": command.completion_id,
            "p_consumption_id": command.consumption_id,
            "p_exchange_id": command.exchange_id,
            "p_exchange_binding_sha256": command.exchange_binding_sha256,
            "p_dispatch_fence_id": command.exchange_id,
            "p_owner_id": command.owner_id,
            "p_connection_id": command.connection_id,
            "p_connection_incarnation_id": command.connection_incarnation_id,
            "p_expected_base_revision": command.expected_base_revision,
            "p_current_flow_nonce_sha256": command.current_flow_nonce_sha256,
            "p_provider": command.provider.value,
            "p_resource": command.resource.value,
            "p_account_kind": command.account_kind.value,
            "p_external_account_id_sha256": command.external_account_id_hash,
            "p_granted_scopes_sha256": command.granted_scopes_sha256,
            "p_broker_credential_ref": _uuid(command.credential.handle_id, "credential_handle_id"),
            "p_credential_ref_sha256": _digest(command.credential.handle_id),
            "p_authorization_issued_at": _iso(command.issued_at),
            "p_authorization_expires_at": _iso(command.expires_at),
            "p_authorization_snapshot_sha256": authorization.snapshot_sha256,
            "p_completion_id": command.completion_id,
            "p_completion_binding_sha256": command.binding_sha256,
            "p_cleanup_id": cleanup.cleanup_id,
            "p_cleanup_binding_sha256": cleanup.binding_sha256,
        }
        try:
            value = await _rpc(
                self._database,
                "connected_app_oauth_finalize_v2",
                payload,
                read=False,
            )
        except ConnectedOAuthRepositoryError:
            recovered = await self.read_completion(command)
            if recovered is not None:
                return recovered
            raise OAuthCompletionResponseLost() from None
        return self._completion(value, command)

    async def read_cleanup(
        self, command: OAuthCredentialCleanupCommand
    ) -> OAuthCredentialCleanupReceipt | None:
        if not isinstance(command, OAuthCredentialCleanupCommand):
            raise TypeError("command must be OAuthCredentialCleanupCommand")
        value = await _rpc(
            self._database,
            "connected_app_read_credential_cleanup_v2",
            {
                "p_cleanup_id": command.cleanup_id,
                "p_cleanup_binding_sha256": command.binding_sha256,
            },
            read=True,
        )
        if value is None:
            return None
        row = _object(value, _CLEANUP_KEYS)
        return OAuthCredentialCleanupReceipt(
            cleanup_id=_uuid(row["cleanup_id"], "cleanup_id"),
            cleanup_binding_sha256=_sha(row["cleanup_binding_sha256"]),
            recorded_at=_time(row["recorded_at"]),
        )

    async def record_cleanup_once(
        self, command: OAuthCredentialCleanupCommand
    ) -> OAuthCredentialCleanupReceipt:
        if not isinstance(command, OAuthCredentialCleanupCommand):
            raise TypeError("command must be OAuthCredentialCleanupCommand")
        try:
            await _rpc(
                self._database,
                "connected_app_record_credential_cleanup_v1",
                {
                    "p_cleanup_id": command.cleanup_id,
                    "p_broker_credential_ref": _uuid(
                        command.credential.handle_id, "credential_handle_id"
                    ),
                    "p_credential_ref_sha256": _digest(command.credential.handle_id),
                    "p_provider": command.provider.value,
                    "p_reason": command.reason,
                    "p_cleanup_binding_sha256": command.binding_sha256,
                },
                read=False,
            )
        except ConnectedOAuthRepositoryError:
            recovered = await self.read_cleanup(command)
            if recovered is not None:
                return recovered
            raise OAuthCredentialCleanupResponseLost() from None
        recovered = await self.read_cleanup(command)
        if recovered is None:
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_AMBIGUOUS")
        return recovered


class SupabaseConnectedAccountRegistry(ConnectedAccountRegistry):
    """Reconstruct and hash-check exact runtime authority after any restart."""

    def __init__(self, database: ConnectedOAuthRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected-account RPC boundary is invalid")
        self._database = database

    async def get_binding(
        self, *, owner_id: str, connection_id: str
    ) -> ConnectedAccountBinding | None:
        value = await _rpc(
            self._database,
            "connected_app_get_binding_v2",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_connection_id": _uuid(connection_id, "connection_id"),
            },
            read=True,
        )
        if value is None:
            return None
        row = _object(value, _BINDING_KEYS)
        if row["authorization_state"] != ConnectionAuthorizationState.ACTIVE.value:
            return None
        provider = _enum(ConnectorProvider, row["provider"])
        resource = _enum(ConnectorResource, row["resource"])
        account_kind = _enum(ConnectorAccountKind, row["account_kind"])
        actions = _actions(row["granted_actions"])
        scopes = frozenset(
            delegated_scope_plan(provider, actions, account_kind=account_kind).delegated_scopes
        )
        authorization = ConnectedAuthorizationSnapshot.build(
            owner_id=_uuid(row["owner_id"], "owner_id"),
            connection_id=_uuid(row["connection_id"], "connection_id"),
            provider=provider,
            resource=resource,
            account_kind=account_kind,
            revision=int(row["authorization_revision"]),
            granted_actions=actions,
            granted_scopes=scopes,
            state=ConnectionAuthorizationState.ACTIVE,
            issued_at=_time(row["authorization_issued_at"]),
            expires_at=_time(row["authorization_expires_at"]),
        )
        broker_ref = _uuid(row["broker_credential_ref"], "broker_credential_ref")
        if not all(
            (
                hmac.compare_digest(
                    authorization.snapshot_sha256,
                    _sha(row["authorization_snapshot_sha256"]),
                ),
                hmac.compare_digest(
                    authorization.granted_actions_sha256,
                    _sha(row["granted_actions_sha256"]),
                ),
                hmac.compare_digest(
                    authorization.granted_scopes_sha256,
                    _sha(row["granted_scopes_sha256"]),
                ),
                hmac.compare_digest(_digest(broker_ref), _sha(row["credential_ref_sha256"])),
            )
        ):
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        account = ConnectedAccountRef(
            owner_id=authorization.owner_id,
            connection_id=authorization.connection_id,
            provider=provider,
            resource=resource,
            account_kind=account_kind,
            external_account_id_hash=_sha(row["external_account_id_sha256"]),
        )
        return ConnectedAccountBinding(account=account, authorization=authorization)


@dataclass(frozen=True, slots=True)
class SupabaseOAuthRepositoryCoordinator:
    """One composition root for flow, secret custody, completion, and restart authority."""

    flows: SupabaseOAuthFlowRepository
    secrets: SupabaseOAuthSecretStore
    completions: SupabaseOAuthCompletionRepository
    accounts: SupabaseConnectedAccountRegistry

    @classmethod
    def build(
        cls,
        *,
        database: ConnectedOAuthRPC,
        redirect_uris: Mapping[ConnectorProvider, str],
        permit_keys: Mapping[str, ConnectedOAuthMasterKey],
        active_permit_key_id: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> SupabaseOAuthRepositoryCoordinator:
        return cls(
            flows=SupabaseOAuthFlowRepository(
                database=database,
                redirect_uris=redirect_uris,
                permit_keys=permit_keys,
                active_permit_key_id=active_permit_key_id,
                now=now,
            ),
            secrets=SupabaseOAuthSecretStore(database),
            completions=SupabaseOAuthCompletionRepository(database),
            accounts=SupabaseConnectedAccountRegistry(database),
        )

    async def complete_and_reconstruct(
        self, command: OAuthCompletionCommand
    ) -> tuple[OAuthCompletion | OAuthCompletionInactive, ConnectedAccountBinding | None]:
        completion = await self.completions.complete_once(command)
        binding = await self.accounts.get_binding(
            owner_id=command.owner_id, connection_id=command.connection_id
        )
        if isinstance(completion, OAuthCompletion):
            if binding is None or (
                binding.authorization.snapshot_sha256 != completion.authorization.snapshot_sha256
            ):
                raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        elif binding is not None:
            raise ConnectedOAuthRepositoryError("OAUTH_REPOSITORY_BINDING_MISMATCH")
        return completion, binding


__all__ = [
    "ConnectedOAuthRepositoryError",
    "ConnectedOAuthRPC",
    "SupabaseConnectedAccountRegistry",
    "SupabaseOAuthCompletionRepository",
    "SupabaseOAuthFlowRepository",
    "SupabaseOAuthRepositoryCoordinator",
]
