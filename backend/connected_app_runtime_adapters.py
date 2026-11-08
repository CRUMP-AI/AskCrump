"""Restart-safe PostgREST bindings for the connected action runtime.

The action adapter intentionally uses only the v2 claim/read/settle RPCs.  A
mutation is issued once; ambiguous transport outcomes are resolved by the
runtime through an exact v2 readback.  The credential gateway couples the
database-owned one-use phase nonce to a process-local, one-use token facade;
the durable credential handle itself is never handed to a provider adapter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
from typing import Any, Callable, Protocol
from uuid import UUID, uuid4

from .connected_app_contracts import (
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    CredentialHandleRef,
)
from .connected_app_credential_vault import ConnectedAccessTokenBroker
from .connected_app_dispatch import (
    ConnectedCredentialLeaseConsumer,
    ConnectedDispatchError,
    ConnectedLeaseConsumption,
)
from .connected_app_https import ConnectedAccessToken, ConnectedAccessTokenSource
from .connected_app_policy import ConnectorActionKind, ConnectorProvider, ConnectorResource
from .connected_app_runtime import (
    ConnectedActionAccessRecoveryRequest,
    ConnectedActionAccessRequest,
    ConnectedActionAuthorityRecord,
    ConnectedActionClaim,
    ConnectedActionClaimRequest,
    ConnectedActionClaimStatus,
    ConnectedActionEffectRequest,
    ConnectedActionLedger,
    ConnectedActionLookupRecord,
    ConnectedActionPostobserveRequest,
    ConnectedAmbiguousTerminalRecord,
    ConnectedCredentialBroker,
    ConnectedCredentialLease,
    ConnectedCredentialPhase,
    ConnectedReadTerminalRecord,
    ConnectedWriteTerminalRecord,
    LedgerTerminal,
    _record_hash,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACTION_ROW_KEYS = frozenset(
    {
        "operation_id",
        "action_id",
        "owner_id",
        "task_id",
        "turn_id",
        "connection_id",
        "grant_id",
        "provider",
        "resource",
        "action",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "parameters_sha256",
        "resource_version_sha256",
        "authority_sha256",
        "idempotency_key_sha256",
        "invocation_binding_sha256",
        "task_state_revision",
        "status",
        "mutates_external_state",
        "approval_class",
        "claim_request_id",
        "claim_id",
        "fencing_token",
        "lease_expires_at",
        "execution_deadline",
        "access_phase",
        "read_use_nonce",
        "read_credential_expires_at",
        "read_consumed_at",
        "preobserve_use_nonce",
        "preobserve_credential_expires_at",
        "preobserve_consumed_at",
        "access_started_at",
        "effect_use_nonce",
        "effect_credential_expires_at",
        "effect_consumed_at",
        "effect_started_at",
        "postobserve_use_nonce",
        "postobserve_started_at",
        "postobserve_expires_at",
        "postobserve_consumed_at",
        "postobserve_impossible",
        "terminal_outcome",
        "terminal_binding_sha256",
        "terminal_resource_version_sha256",
        "provider_request_id_sha256",
        "provider_resource_id_sha256",
        "observed_at",
        "terminal_at",
        "created_at",
        "updated_at",
    }
)
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
_CONSUMPTION_KEYS = frozenset(
    {"operation_id", "action_id", "phase", "consumed", "consumed_at"}
)
_OUTCOME_BY_ACTION = {
    ConnectorActionKind.MAIL_CREATE_DRAFT: "drafted",
    ConnectorActionKind.MAIL_SEND: "sent",
    ConnectorActionKind.MAIL_REPLY: "sent",
    ConnectorActionKind.CALENDAR_CREATE: "created",
    ConnectorActionKind.CALENDAR_UPDATE: "updated",
    ConnectorActionKind.CALENDAR_CANCEL: "cancelled",
}


class ConnectedRuntimeRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ValueError("connected RPC shape is invalid")
    return value  # type: ignore[return-value]


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if canonical != value:
        raise ValueError(f"{name} is invalid")
    return value


def _sha(value: object, name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _time(value: object, name: str, *, nullable: bool = False) -> datetime | None:
    if nullable and value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and 1 <= len(value) <= 64:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{name} is invalid") from None
    else:
        raise ValueError(f"{name} is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} is invalid")
    return parsed.astimezone(UTC)


def _integer(value: object, name: str, *, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} is invalid")
    return value


def _enum(value: object, enum_type: type[Any], name: str) -> Any:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} is invalid") from None


def _row(value: object) -> dict[str, object]:
    return _object(value, _ACTION_ROW_KEYS)


class SupabaseConnectedActionLedger(ConnectedActionLedger):
    """Exact v2 action ledger.  There is deliberately no v1 fallback."""

    def __init__(
        self,
        database: ConnectedRuntimeRPC,
        *,
        claim_lease: timedelta = timedelta(seconds=45),
        new_uuid: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected runtime RPC boundary is invalid")
        seconds = int(claim_lease.total_seconds())
        if claim_lease != timedelta(seconds=seconds) or not 30 <= seconds <= 300:
            raise ValueError("claim_lease is invalid")
        if not callable(new_uuid):
            raise TypeError("new_uuid is invalid")
        self._database = database
        self._claim_seconds = seconds
        self._new_uuid = new_uuid

    async def _rpc(self, name: str, payload: dict[str, object], *, read: bool = False) -> Any:
        return await self._database.rpc(name, payload, retry_transient=read)

    async def readback(
        self, record: ConnectedActionLookupRecord | ConnectedActionClaimRequest
    ) -> ConnectedActionClaim | None:
        lookup = record.lookup if type(record) is ConnectedActionClaimRequest else record
        if type(lookup) is not ConnectedActionLookupRecord:
            raise TypeError("lookup record is invalid")
        value = await self._rpc(
            "connected_app_read_action_v2",
            {
                "p_owner_id": lookup.owner_id,
                "p_operation_id": lookup.operation_id,
                "p_idempotency_key_sha256": lookup.idempotency_key_hash,
                "p_invocation_binding_sha256": lookup.binding_sha256,
            },
            read=True,
        )
        if value is None:
            return None
        row = _row(value)
        self._validate_lookup_row(row, lookup)
        disclose = (
            type(record) is ConnectedActionClaimRequest
            and row["claim_request_id"] == record.claim_request_id
        )
        return self._claim(row, disclose=disclose)

    async def claim(
        self,
        record: ConnectedActionClaimRequest,
        authority: ConnectedActionAuthorityRecord,
    ) -> ConnectedActionClaim:
        if type(record) is not ConnectedActionClaimRequest or type(
            authority
        ) is not ConnectedActionAuthorityRecord:
            raise TypeError("claim input is invalid")
        lookup = record.lookup
        claim_id = _uuid(self._new_uuid(), "claim_id")
        row = _row(
            await self._rpc(
                "connected_app_claim_action_v2",
                {
                    "p_operation_id": lookup.operation_id,
                    "p_action_id": lookup.operation_id,
                    "p_owner_id": lookup.owner_id,
                    "p_task_id": lookup.task_id,
                    "p_turn_id": lookup.turn_id,
                    "p_connection_id": lookup.connection_id,
                    "p_grant_id": authority.grant_id,
                    "p_provider": lookup.provider.value,
                    "p_resource": lookup.resource.value,
                    "p_action": lookup.action.value,
                    "p_authorization_revision": authority.authorization_revision,
                    "p_authorization_snapshot_sha256": (
                        authority.authorization_snapshot_sha256
                    ),
                    "p_granted_actions_sha256": authority.granted_actions_sha256,
                    "p_granted_scopes_sha256": authority.granted_scopes_sha256,
                    "p_parameters_sha256": lookup.parameters_sha256,
                    "p_resource_version_sha256": lookup.resource_version_sha256,
                    "p_authority_sha256": record.authority_sha256,
                    "p_idempotency_key_sha256": lookup.idempotency_key_hash,
                    "p_invocation_binding_sha256": lookup.binding_sha256,
                    "p_task_state_revision": authority.task_state_revision,
                    "p_claim_request_id": record.claim_request_id,
                    "p_claim_id": claim_id,
                    "p_lease_seconds": self._claim_seconds,
                    "p_execution_deadline": record.execution_deadline.isoformat(),
                },
            )
        )
        self._validate_lookup_row(row, lookup)
        self._validate_authority_row(row, authority)
        if (
            row["grant_id"] != authority.grant_id
            or row["mutates_external_state"] is not record.mutates_external_state
            or _time(row["execution_deadline"], "execution_deadline")
            != record.execution_deadline.astimezone(UTC)
        ):
            raise ValueError("claim response authority is invalid")
        return self._claim(
            row,
            disclose=row["claim_request_id"] == record.claim_request_id,
        )

    async def begin_access(
        self,
        record: ConnectedActionAccessRequest,
        claim: ConnectedActionClaim,
    ) -> ConnectedActionClaim:
        del claim
        row = _row(
            await self._rpc(
                "connected_app_begin_access_v1",
                {
                    "p_operation_id": record.lookup.operation_id,
                    "p_owner_id": record.lookup.owner_id,
                    "p_claim_id": record.claim_id,
                    "p_fencing_token": record.fencing_token,
                    "p_granted_actions_sha256": record.granted_actions_sha256,
                    "p_access_phase": record.phase.value,
                    "p_access_use_nonce": record.credential_use_nonce,
                    "p_credential_expires_at": record.credential_expires_at.isoformat(),
                },
            )
        )
        self._validate_lookup_row(row, record.lookup)
        self._validate_request_authority_row(row, record)
        return self._claim(row, disclose=self._owns(row, record.claim_id, record.fencing_token))

    async def recover_access(
        self,
        record: ConnectedActionAccessRecoveryRequest,
        authority: ConnectedActionAuthorityRecord,
    ) -> ConnectedActionClaim:
        claim_id = _uuid(self._new_uuid(), "claim_id")
        row = _row(
            await self._rpc(
                "connected_app_recover_access_v2",
                {
                    "p_operation_id": record.lookup.operation_id,
                    "p_owner_id": record.lookup.owner_id,
                    "p_expired_claim_id": record.expired_claim_id,
                    "p_recovery_request_id": record.claim_request_id,
                    "p_claim_id": claim_id,
                    "p_lease_seconds": self._claim_seconds,
                    "p_grant_id": authority.grant_id,
                    "p_authorization_revision": record.authorization_revision,
                    "p_authorization_snapshot_sha256": (
                        record.authorization_snapshot_sha256
                    ),
                    "p_granted_actions_sha256": record.granted_actions_sha256,
                    "p_granted_scopes_sha256": record.granted_scopes_sha256,
                    "p_authority_sha256": record.authority_sha256,
                    "p_task_state_revision": record.task_state_revision,
                    "p_invocation_binding_sha256": record.lookup.binding_sha256,
                    "p_access_phase": record.phase.value,
                    "p_access_use_nonce": record.credential_use_nonce,
                    "p_credential_expires_at": record.credential_expires_at.isoformat(),
                    "p_execution_deadline": record.execution_deadline.isoformat(),
                },
            )
        )
        self._validate_lookup_row(row, record.lookup)
        self._validate_request_authority_row(row, record)
        self._validate_authority_row(row, authority)
        return self._claim(
            row,
            disclose=(
                row["claim_request_id"] == record.claim_request_id
                and row["claim_id"] == claim_id
            ),
        )

    async def begin_effect(
        self,
        record: ConnectedActionEffectRequest,
        claim: ConnectedActionClaim,
    ) -> ConnectedActionClaim:
        del claim
        row = _row(
            await self._rpc(
                "connected_app_consume_approval_and_begin_effect_v1",
                {
                    "p_operation_id": record.lookup.operation_id,
                    "p_owner_id": record.lookup.owner_id,
                    "p_claim_id": record.claim_id,
                    "p_fencing_token": record.fencing_token,
                    "p_granted_actions_sha256": record.granted_actions_sha256,
                    "p_approval_id": record.approval_id,
                    "p_approval_binding_sha256": record.approval_binding_sha256,
                    "p_effect_use_nonce": record.credential_use_nonce,
                    "p_credential_expires_at": record.credential_expires_at.isoformat(),
                },
            )
        )
        self._validate_lookup_row(row, record.lookup)
        self._validate_request_authority_row(row, record)
        return self._claim(row, disclose=self._owns(row, record.claim_id, record.fencing_token))

    async def begin_postobserve(
        self,
        record: ConnectedActionPostobserveRequest,
        claim: ConnectedActionClaim,
    ) -> ConnectedActionClaim:
        del claim
        row = _row(
            await self._rpc(
                "connected_app_begin_postobserve_v1",
                {
                    "p_operation_id": record.lookup.operation_id,
                    "p_owner_id": record.lookup.owner_id,
                    "p_effect_use_nonce": record.effect_use_nonce,
                    "p_postobserve_use_nonce": record.credential_use_nonce,
                    "p_credential_expires_at": record.credential_expires_at.isoformat(),
                    "p_granted_actions_sha256": record.granted_actions_sha256,
                },
            )
        )
        self._validate_lookup_row(row, record.lookup)
        self._validate_request_authority_row(row, record)
        return self._claim(row, disclose=self._owns(row, record.claim_id, record.fencing_token))

    async def settle(
        self, claim: ConnectedActionClaim, terminal: LedgerTerminal
    ) -> ConnectedActionClaim:
        if type(claim) is not ConnectedActionClaim or type(terminal) not in {
            ConnectedReadTerminalRecord,
            ConnectedWriteTerminalRecord,
            ConnectedAmbiguousTerminalRecord,
        }:
            raise TypeError("settlement input is invalid")
        if claim.fencing_token is None:
            raise ValueError("settlement claim does not disclose its fence")
        if type(terminal) is ConnectedReadTerminalRecord:
            outcome = "read"
            provider_request = None
            provider_resource = None
            resource_version = terminal.resource_version_sha256
            post_nonce = None
            impossible = False
        elif type(terminal) is ConnectedWriteTerminalRecord:
            outcome = "succeeded"
            provider_request = terminal.provider_request_id_hash
            provider_resource = terminal.resource_id_hash
            resource_version = terminal.resource_version_sha256
            post_nonce = claim.postobserve_use_nonce
            impossible = False
        else:
            outcome = "ambiguous"
            provider_request = None
            provider_resource = None
            resource_version = None
            post_nonce = claim.postobserve_use_nonce
            impossible = claim.postobserve_use_nonce is None
        row = _row(
            await self._rpc(
                "connected_app_settle_action_v2",
                {
                    "p_operation_id": terminal.operation_id,
                    "p_claim_id": claim.claim_id,
                    "p_fencing_token": claim.fencing_token,
                    "p_invocation_binding_sha256": terminal.binding_sha256,
                    "p_access_use_nonce": claim.access_use_nonce,
                    "p_effect_use_nonce": claim.effect_use_nonce,
                    "p_postobserve_use_nonce": post_nonce,
                    "p_postobserve_impossible": impossible,
                    "p_terminal_outcome": outcome,
                    "p_terminal_binding_sha256": _record_hash(terminal),
                    "p_terminal_resource_version_sha256": resource_version,
                    "p_provider_request_id_sha256": provider_request,
                    "p_provider_resource_id_sha256": provider_resource,
                    "p_observed_at": terminal.observed_at.isoformat(),
                },
            )
        )
        if (
            row["operation_id"] != terminal.operation_id
            or row["provider"] != terminal.provider.value
            or row["resource"] != terminal.resource.value
            or row["action"] != terminal.action.value
            or row["invocation_binding_sha256"] != terminal.binding_sha256
            or row["authority_sha256"] != terminal.authority_sha256
            or row["idempotency_key_sha256"] != terminal.idempotency_key_hash
            or row["claim_id"] != claim.claim_id
            or row["fencing_token"] != claim.fencing_token
        ):
            raise ValueError("settlement response authority is invalid")
        return self._claim(row, disclose=False)

    @staticmethod
    def _owns(row: dict[str, object], claim_id: str, fence: int) -> bool:
        return row["claim_id"] == claim_id and row["fencing_token"] == fence

    @staticmethod
    def _validate_lookup_row(
        row: dict[str, object], lookup: ConnectedActionLookupRecord
    ) -> None:
        if (
            row["operation_id"] != lookup.operation_id
            or row["action_id"] != lookup.operation_id
            or row["owner_id"] != lookup.owner_id
            or row["task_id"] != lookup.task_id
            or row["turn_id"] != lookup.turn_id
            or row["connection_id"] != lookup.connection_id
            or row["provider"] != lookup.provider.value
            or row["resource"] != lookup.resource.value
            or row["action"] != lookup.action.value
            or row["parameters_sha256"] != lookup.parameters_sha256
            or row["resource_version_sha256"] != lookup.resource_version_sha256
            or row["invocation_binding_sha256"] != lookup.binding_sha256
            or row["idempotency_key_sha256"] != lookup.idempotency_key_hash
        ):
            raise ValueError("action response lookup binding is invalid")

    @staticmethod
    def _validate_authority_row(
        row: dict[str, object], authority: ConnectedActionAuthorityRecord
    ) -> None:
        if (
            row["authorization_revision"] != authority.authorization_revision
            or row["authorization_snapshot_sha256"]
            != authority.authorization_snapshot_sha256
            or row["granted_actions_sha256"] != authority.granted_actions_sha256
            or row["granted_scopes_sha256"] != authority.granted_scopes_sha256
            or row["authority_sha256"] != authority.authority_sha256
            or row["task_state_revision"] != authority.task_state_revision
        ):
            raise ValueError("action response authority binding is invalid")

    @staticmethod
    def _validate_request_authority_row(row: dict[str, object], record: object) -> None:
        if (
            row["authorization_revision"] != getattr(record, "authorization_revision")
            or row["authorization_snapshot_sha256"]
            != getattr(record, "authorization_snapshot_sha256")
            or row["granted_actions_sha256"]
            != getattr(record, "granted_actions_sha256")
            or row["granted_scopes_sha256"] != getattr(record, "granted_scopes_sha256")
            or row["authority_sha256"] != getattr(record, "authority_sha256")
            or row["task_state_revision"] != getattr(record, "task_state_revision")
            or _time(row["execution_deadline"], "execution_deadline")
            != getattr(record, "execution_deadline").astimezone(UTC)
        ):
            raise ValueError("action response request authority is invalid")

    @staticmethod
    def _claim(row: dict[str, object], *, disclose: bool) -> ConnectedActionClaim:
        provider = _enum(row["provider"], ConnectorProvider, "provider")
        resource = _enum(row["resource"], ConnectorResource, "resource")
        action = _enum(row["action"], ConnectorActionKind, "action")
        claim_id = _uuid(row["claim_id"], "claim_id")
        binding = _sha(row["invocation_binding_sha256"], "invocation_binding_sha256") or ""
        authority = _sha(row["authority_sha256"], "authority_sha256") or ""
        actions = _sha(row["granted_actions_sha256"], "granted_actions_sha256") or ""
        status = row["status"]
        if status == "terminal":
            outcome = row["terminal_outcome"]
            common = {
                "operation_id": _uuid(row["operation_id"], "operation_id"),
                "provider": provider,
                "resource": resource,
                "action": action,
                "binding_sha256": binding,
                "authority_sha256": authority,
                "idempotency_key_hash": _sha(
                    row["idempotency_key_sha256"], "idempotency_key_sha256"
                )
                or "",
                "observed_at": _time(row["observed_at"], "observed_at")
                or datetime.min.replace(tzinfo=UTC),
            }
            if outcome == "read":
                terminal: LedgerTerminal = ConnectedReadTerminalRecord(
                    **common,
                    resource_version_sha256=_sha(
                        row["terminal_resource_version_sha256"],
                        "terminal_resource_version_sha256",
                        nullable=True,
                    ),
                )
                claim_status = ConnectedActionClaimStatus.REPLAY_READ
            elif outcome == "succeeded":
                terminal = ConnectedWriteTerminalRecord(
                    **common,
                    receipt_outcome=_OUTCOME_BY_ACTION[action],
                    provider_request_id_hash=_sha(
                        row["provider_request_id_sha256"], "provider_request_id_sha256"
                    )
                    or "",
                    resource_id_hash=_sha(
                        row["provider_resource_id_sha256"], "provider_resource_id_sha256"
                    )
                    or "",
                    resource_version_sha256=_sha(
                        row["terminal_resource_version_sha256"],
                        "terminal_resource_version_sha256",
                    )
                    or "",
                )
                claim_status = ConnectedActionClaimStatus.REPLAY_SUCCEEDED
            elif outcome == "ambiguous":
                terminal = ConnectedAmbiguousTerminalRecord(**common)
                claim_status = ConnectedActionClaimStatus.REPLAY_AMBIGUOUS
            else:
                raise ValueError("terminal outcome is invalid")
            expected_terminal = _sha(
                row["terminal_binding_sha256"], "terminal_binding_sha256"
            )
            if not hmac.compare_digest(_record_hash(terminal), expected_terminal or ""):
                raise ValueError("terminal binding is invalid")
            return ConnectedActionClaim(
                claim_id=claim_id,
                status=claim_status,
                binding_sha256=binding,
                authority_sha256=authority,
                granted_actions_sha256=actions,
                terminal=terminal,
            )

        lease = _time(row["lease_expires_at"], "lease_expires_at")
        deadline = _time(row["execution_deadline"], "execution_deadline")
        fence = _integer(row["fencing_token"], "fencing_token") if disclose else None
        if status == "claimed":
            claim_status = (
                ConnectedActionClaimStatus.CLAIMED
                if disclose
                else ConnectedActionClaimStatus.BUSY
            )
            return ConnectedActionClaim(
                claim_id=claim_id,
                status=claim_status,
                binding_sha256=binding,
                authority_sha256=authority,
                granted_actions_sha256=actions,
                fencing_token=fence,
                lease_expires_at=lease,
                execution_deadline=deadline,
            )
        if status == "access_granted":
            phase = _enum(row["access_phase"], ConnectedCredentialPhase, "access_phase")
            nonce_key = "read_use_nonce" if phase is ConnectedCredentialPhase.READ else "preobserve_use_nonce"
            return ConnectedActionClaim(
                claim_id=claim_id,
                status=ConnectedActionClaimStatus.ACCESS_GRANTED,
                binding_sha256=binding,
                authority_sha256=authority,
                granted_actions_sha256=actions,
                fencing_token=fence,
                lease_expires_at=lease,
                execution_deadline=deadline,
                access_started_at=_time(row["access_started_at"], "access_started_at"),
                access_phase=phase,
                access_use_nonce=_uuid(row[nonce_key], nonce_key) if disclose else None,
            )
        if status == "effect_possible":
            return ConnectedActionClaim(
                claim_id=claim_id,
                status=ConnectedActionClaimStatus.EFFECT_POSSIBLE,
                binding_sha256=binding,
                authority_sha256=authority,
                granted_actions_sha256=actions,
                fencing_token=fence,
                lease_expires_at=lease,
                execution_deadline=deadline,
                effect_started_at=_time(row["effect_started_at"], "effect_started_at"),
                effect_use_nonce=(
                    _uuid(row["effect_use_nonce"], "effect_use_nonce") if disclose else None
                ),
                postobserve_started_at=(
                    _time(
                        row["postobserve_started_at"],
                        "postobserve_started_at",
                        nullable=True,
                    )
                    if disclose
                    else None
                ),
                postobserve_use_nonce=(
                    _uuid(row["postobserve_use_nonce"], "postobserve_use_nonce")
                    if disclose and row["postobserve_use_nonce"] is not None
                    else None
                ),
                postobserve_expires_at=(
                    _time(
                        row["postobserve_expires_at"],
                        "postobserve_expires_at",
                        nullable=True,
                    )
                    if disclose
                    else None
                ),
            )
        raise ValueError("action status is invalid")


@dataclass(frozen=True, slots=True)
class _CredentialBinding:
    credential: CredentialHandleRef
    connection_incarnation_id: str


@dataclass(slots=True)
class _LeaseTokenContext:
    account: ConnectedAccountRef
    authorization: ConnectedAuthorizationSnapshot
    real_credential: CredentialHandleRef
    presented_credential: CredentialHandleRef
    connection_incarnation_id: str
    phase: ConnectedCredentialPhase
    use_nonce: str
    claim_id: str
    fencing_token: int
    authority_sha256: str
    task_state_revision: int
    expires_at: datetime
    token_source: ConnectedAccessTokenSource
    consuming: bool = False
    consumed: bool = False


class SupabaseConnectedCredentialGateway(
    ConnectedCredentialBroker,
    ConnectedCredentialLeaseConsumer,
    ConnectedAccessTokenSource,
):
    """Durable phase-consumption plus ephemeral access-token facade."""

    def __init__(
        self,
        *,
        database: ConnectedRuntimeRPC,
        tokens: ConnectedAccessTokenBroker,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_uuid: Callable[[], str] = lambda: str(uuid4()),
        max_pending: int = 1024,
    ) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected runtime RPC boundary is invalid")
        if not callable(getattr(tokens, "bind", None)):
            raise TypeError("connected access-token broker is invalid")
        if not callable(now) or not callable(new_uuid) or not 1 <= max_pending <= 4096:
            raise ValueError("credential gateway configuration is invalid")
        self._database = database
        self._tokens = tokens
        self._now = now
        self._new_uuid = new_uuid
        self._max_pending = max_pending
        self._contexts: dict[str, _LeaseTokenContext] = {}
        self._lock = asyncio.Lock()

    async def issue_child_lease(
        self,
        *,
        account: ConnectedAccountRef,
        authorization: ConnectedAuthorizationSnapshot,
        intent: Any,
        claim: ConnectedActionClaim,
        authority: ConnectedActionAuthorityRecord,
        phase: ConnectedCredentialPhase,
        use_nonce: str,
        hard_expires_at: datetime,
    ) -> ConnectedCredentialLease:
        now = self._aware_now()
        expires = hard_expires_at.astimezone(UTC)
        if (
            not isinstance(account, ConnectedAccountRef)
            or not isinstance(authorization, ConnectedAuthorizationSnapshot)
            or type(claim) is not ConnectedActionClaim
            or type(authority) is not ConnectedActionAuthorityRecord
            or not isinstance(phase, ConnectedCredentialPhase)
            or claim.fencing_token is None
            or expires <= now
            or not authorization.binds(account)
            or intent.owner_id != account.owner_id
            or intent.connection_id != account.connection_id
            or intent.provider is not account.provider
            or intent.resource is not account.resource
            or claim.authority_sha256 != authority.authority_sha256
        ):
            raise ValueError("credential lease authority is invalid")
        binding = await self._binding(account=account, authorization=authorization)
        alias = CredentialHandleRef(
            owner_id=account.owner_id,
            connection_id=account.connection_id,
            provider=account.provider,
            handle_id=_uuid(self._new_uuid(), "credential_alias"),
        )
        source = self._tokens.bind(
            account=account,
            credential=binding.credential,
            presented_credential=alias,
            connection_incarnation_id=binding.connection_incarnation_id,
            authorization=authorization,
            hard_expires_at=expires,
        )
        context = _LeaseTokenContext(
            account=account,
            authorization=authorization,
            real_credential=binding.credential,
            presented_credential=alias,
            connection_incarnation_id=binding.connection_incarnation_id,
            phase=phase,
            use_nonce=_uuid(use_nonce, "use_nonce"),
            claim_id=claim.claim_id,
            fencing_token=claim.fencing_token,
            authority_sha256=authority.authority_sha256,
            task_state_revision=authority.task_state_revision,
            expires_at=expires,
            token_source=source,
        )
        key = self._alias_key(alias)
        async with self._lock:
            self._prune(now)
            if len(self._contexts) >= self._max_pending or key in self._contexts:
                raise ValueError("credential gateway capacity is exhausted")
            self._contexts[key] = context
        return ConnectedCredentialLease(
            credential=alias,
            owner_id=account.owner_id,
            connection_id=account.connection_id,
            provider=account.provider,
            resource=account.resource,
            authorization_revision=authorization.revision,
            authorization_snapshot_sha256=authorization.snapshot_sha256,
            granted_actions_sha256=authorization.granted_actions_sha256,
            granted_scopes_sha256=authorization.granted_scopes_sha256,
            authority_sha256=authority.authority_sha256,
            task_state_revision=authority.task_state_revision,
            claim_id=claim.claim_id,
            fencing_token=claim.fencing_token,
            phase=phase,
            use_nonce=use_nonce,
            issued_at=now,
            expires_at=expires,
        )

    async def consume_once(
        self,
        *,
        lease: ConnectedCredentialLease,
        operation_id: str,
        action: ConnectorActionKind,
    ) -> ConnectedLeaseConsumption:
        if type(lease) is not ConnectedCredentialLease or not isinstance(
            action, ConnectorActionKind
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_MISMATCH")
        key = self._alias_key(lease.credential)
        async with self._lock:
            context = self._contexts.get(key)
            if (
                context is None
                or context.consuming
                or context.consumed
                or not self._context_matches(context, lease)
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_MISMATCH")
            context.consuming = True
        try:
            value = await self._database.rpc(
                "connected_app_consume_credential_lease_v1",
                {
                    "p_operation_id": operation_id,
                    "p_owner_id": lease.owner_id,
                    "p_connection_id": lease.connection_id,
                    "p_action_id": operation_id,
                    "p_action": action.value,
                    "p_claim_id": lease.claim_id,
                    "p_fencing_token": lease.fencing_token,
                    "p_phase": lease.phase.value,
                    "p_use_nonce": lease.use_nonce,
                    "p_credential_expires_at": lease.expires_at.isoformat(),
                    "p_authorization_revision": lease.authorization_revision,
                    "p_authorization_snapshot_sha256": (
                        lease.authorization_snapshot_sha256
                    ),
                    "p_granted_actions_sha256": lease.granted_actions_sha256,
                    "p_granted_scopes_sha256": lease.granted_scopes_sha256,
                    "p_authority_sha256": lease.authority_sha256,
                    "p_task_state_revision": lease.task_state_revision,
                },
                retry_transient=False,
            )
            row = _object(value, _CONSUMPTION_KEYS)
            if (
                row["operation_id"] != operation_id
                or row["action_id"] != operation_id
                or row["phase"] != lease.phase.value
                or row["consumed"] is not True
            ):
                raise ValueError("credential consumption receipt is invalid")
            consumed_at = _time(row["consumed_at"], "consumed_at")
            assert consumed_at is not None
        except Exception:
            async with self._lock:
                self._contexts.pop(key, None)
            raise ConnectedDispatchError(
                "CONNECTED_DISPATCH_LEASE_UNCERTAIN", retryable=False
            ) from None
        async with self._lock:
            current = self._contexts.get(key)
            if current is not context or not current.consuming or current.consumed:
                self._contexts.pop(key, None)
                raise ConnectedDispatchError(
                    "CONNECTED_DISPATCH_LEASE_UNCERTAIN", retryable=False
                )
            current.consuming = False
            current.consumed = True
        return ConnectedLeaseConsumption(
            operation_id=operation_id,
            owner_id=lease.owner_id,
            connection_id=lease.connection_id,
            claim_id=lease.claim_id,
            fencing_token=lease.fencing_token,
            provider=lease.provider,
            resource=lease.resource,
            action=action,
            phase=lease.phase,
            use_nonce=lease.use_nonce,
            consumed_at=consumed_at,
        )

    async def issue_access_token(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
    ) -> ConnectedAccessToken:
        key = self._alias_key(credential)
        async with self._lock:
            context = self._contexts.pop(key, None)
            if (
                context is None
                or not context.consumed
                or context.account != account
                or context.presented_credential != credential
                or context.expires_at <= self._aware_now()
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_MISMATCH")
        try:
            return await context.token_source.issue_access_token(
                account=account,
                credential=credential,
            )
        except ConnectedDispatchError:
            raise
        except Exception:
            raise ConnectedDispatchError(
                "CONNECTED_DISPATCH_LEASE_UNCERTAIN", retryable=False
            ) from None

    async def _binding(
        self,
        *,
        account: ConnectedAccountRef,
        authorization: ConnectedAuthorizationSnapshot,
    ) -> _CredentialBinding:
        value = await self._database.rpc(
            "connected_app_get_binding_v2",
            {"p_owner_id": account.owner_id, "p_connection_id": account.connection_id},
            retry_transient=True,
        )
        row = _object(value, _BINDING_KEYS)
        broker_ref = (
            _uuid(row["broker_credential_ref"], "broker_credential_ref")
            if isinstance(row["broker_credential_ref"], str)
            else ""
        )
        granted_actions = row["granted_actions"]
        try:
            parsed_actions = (
                tuple(ConnectorActionKind(value) for value in granted_actions)
                if type(granted_actions) is list
                else ()
            )
        except (TypeError, ValueError):
            parsed_actions = ()
        if (
            row["owner_id"] != account.owner_id
            or row["connection_id"] != account.connection_id
            or row["provider"] != account.provider.value
            or row["resource"] != account.resource.value
            or row["account_kind"] != account.account_kind.value
            or row["authorization_state"] != "active"
            or row["authorization_revision"] != authorization.revision
            or row["authorization_snapshot_sha256"] != authorization.snapshot_sha256
            or row["granted_actions_sha256"] != authorization.granted_actions_sha256
            or row["granted_scopes_sha256"] != authorization.granted_scopes_sha256
            or row["external_account_id_sha256"] != account.external_account_id_hash
            or not parsed_actions
            or len(parsed_actions) != len(frozenset(parsed_actions))
            or frozenset(parsed_actions) != authorization.granted_actions
            or _time(row["authorization_issued_at"], "authorization_issued_at")
            != authorization.issued_at.astimezone(UTC)
            or _sha(row["credential_ref_sha256"], "credential_ref_sha256")
            != hashlib.sha256(broker_ref.encode("utf-8")).hexdigest()
            or row["revoked_at"] is not None
        ):
            raise ValueError("credential binding authority changed")
        binding_expiry = _time(row["authorization_expires_at"], "authorization_expires_at")
        if binding_expiry != authorization.expires_at.astimezone(UTC):
            raise ValueError("credential binding expiry changed")
        return _CredentialBinding(
            credential=CredentialHandleRef(
                owner_id=account.owner_id,
                connection_id=account.connection_id,
                provider=account.provider,
                handle_id=broker_ref,
            ),
            connection_incarnation_id=_uuid(
                row["connection_incarnation_id"], "connection_incarnation_id"
            ),
        )

    def _aware_now(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("credential gateway clock is invalid")
        return value.astimezone(UTC)

    @staticmethod
    def _alias_key(credential: CredentialHandleRef) -> str:
        return hashlib.sha256(
            (
                credential.owner_id
                + "\x00"
                + credential.connection_id
                + "\x00"
                + credential.provider.value
                + "\x00"
                + credential.handle_id
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _context_matches(
        context: _LeaseTokenContext, lease: ConnectedCredentialLease
    ) -> bool:
        return (
            context.presented_credential == lease.credential
            and context.account.owner_id == lease.owner_id
            and context.account.connection_id == lease.connection_id
            and context.account.provider is lease.provider
            and context.account.resource is lease.resource
            and context.authorization.revision == lease.authorization_revision
            and context.authorization.snapshot_sha256
            == lease.authorization_snapshot_sha256
            and context.authorization.granted_actions_sha256
            == lease.granted_actions_sha256
            and context.authorization.granted_scopes_sha256
            == lease.granted_scopes_sha256
            and context.claim_id == lease.claim_id
            and context.fencing_token == lease.fencing_token
            and context.authority_sha256 == lease.authority_sha256
            and context.task_state_revision == lease.task_state_revision
            and context.phase is lease.phase
            and context.use_nonce == lease.use_nonce
            and context.expires_at == lease.expires_at
        )

    def _prune(self, now: datetime) -> None:
        expired = [
            key
            for key, context in self._contexts.items()
            if context.expires_at <= now
        ]
        for key in expired:
            self._contexts.pop(key, None)


__all__ = [
    "ConnectedRuntimeRPC",
    "SupabaseConnectedActionLedger",
    "SupabaseConnectedCredentialGateway",
]
