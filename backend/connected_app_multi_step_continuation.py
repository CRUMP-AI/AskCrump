"""Crash-safe background continuation for durable connected-operator loops.

The database decides which loop may be resumed and issues one bounded lease.
This module never derives authority from the model, mail, calendar, or chat
content.  The original user instruction is read only under that live lease and
must reproduce the server-held chat request binding before it is used.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hmac
from typing import Callable, Protocol
from uuid import UUID, uuid4, uuid5

from .connected_app_chat_turn import ConnectedChatBindingKey, ConnectedChatRequestMaterial
from .connected_app_multi_step import (
    ConnectedMultiStepLoopRecord,
    ConnectedMultiStepSettlement,
    ConnectedMultiStepStartCommand,
    ConnectedMultiStepStatus,
)
from .connected_app_multi_step_adapters import ConnectedOperatorMultiStepWorker
from .connected_app_service import ConnectedConnectionView
from .connected_app_contracts import ConnectionAuthorizationState


_CONTINUATION_NAMESPACE = UUID("81d76b5a-dbd4-4e36-b50c-d8ea629c305d")
_HEX = frozenset("0123456789abcdef")
_MAX_INSTRUCTION_BYTES = 12_000


def _uuid(value: object, name: str = "identifier") -> str:
    if type(value) is not str:
        raise ValueError(f"{name} is invalid")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if str(parsed) != value:
        raise ValueError(f"{name} is invalid")
    return value


def _sha(value: object, name: str = "binding") -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        raise ValueError(f"{name} is invalid")
    return value


def _time(value: object, name: str = "timestamp") -> datetime:
    if type(value) is str:
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{name} is invalid") from None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} is invalid")
    return value.astimezone(UTC)


def _positive(value: object, name: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is invalid")
    return value


class ConnectedMultiStepContinuationError(RuntimeError):
    """Fixed, content-free continuation failure."""

    _CODES = frozenset(
        {
            "CONNECTED_MULTI_STEP_CONTINUATION_BUSY",
            "CONNECTED_MULTI_STEP_CONTINUATION_FAILED",
            "CONNECTED_MULTI_STEP_CONTINUATION_INSTRUCTION_INVALID",
            "CONNECTED_MULTI_STEP_CONTINUATION_INVALID",
            "CONNECTED_MULTI_STEP_CONTINUATION_NOT_READY",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code if code in self._CODES else "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
        self.retryable = retryable
        super().__init__(self.code)


class ConnectedMultiStepContinuationKind(StrEnum):
    ACTIVE = "active"
    APPROVED_WRITE = "approved_write"


class ConnectedMultiStepContinuationClaimState(StrEnum):
    CLAIMED = "claimed"
    SETTLED = "settled"
    SUPERSEDED = "superseded"


class ConnectedMultiStepContinuationOutcome(StrEnum):
    WAITING_APPROVAL = "waiting_approval"
    TERMINAL = "terminal"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepContinuationCandidate:
    owner_id: str
    loop_id: str
    task_state_revision: int
    kind: ConnectedMultiStepContinuationKind
    expires_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.owner_id, "owner_id")
        _uuid(self.loop_id, "loop_id")
        _positive(self.task_state_revision, "task_state_revision")
        if not isinstance(self.kind, ConnectedMultiStepContinuationKind):
            raise ValueError("continuation kind is invalid")
        object.__setattr__(self, "expires_at", _time(self.expires_at, "expires_at"))


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepContinuationClaim:
    claim_request_id: str
    claim_token: str
    claim_generation: int
    loop_revision: int
    claim_expires_at: datetime
    claim_state: ConnectedMultiStepContinuationClaimState
    kind: ConnectedMultiStepContinuationKind
    command: ConnectedMultiStepStartCommand
    approval_step_id: str | None = None
    action_id: str | None = None
    approval_id: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.claim_request_id, "claim_request_id")
        _uuid(self.claim_token, "claim_token")
        _positive(self.claim_generation, "claim_generation")
        _positive(self.loop_revision, "loop_revision")
        if not isinstance(self.claim_state, ConnectedMultiStepContinuationClaimState):
            raise ValueError("continuation claim state is invalid")
        if not isinstance(self.kind, ConnectedMultiStepContinuationKind):
            raise ValueError("continuation kind is invalid")
        if type(self.command) is not ConnectedMultiStepStartCommand:
            raise ValueError("continuation command is invalid")
        expires = _time(self.claim_expires_at, "claim_expires_at")
        if expires > self.command.expires_at:
            raise ValueError("continuation claim lifetime is invalid")
        proof = (self.approval_step_id, self.action_id, self.approval_id)
        if self.kind is ConnectedMultiStepContinuationKind.APPROVED_WRITE:
            if any(value is None for value in proof):
                raise ValueError("continuation approval proof is invalid")
            for name, value in zip(
                ("approval_step_id", "action_id", "approval_id"), proof, strict=True
            ):
                _uuid(value, name)
        elif any(value is not None for value in proof):
            raise ValueError("continuation approval proof is invalid")
        object.__setattr__(self, "claim_expires_at", expires)

    def __repr__(self) -> str:
        return (
            "ConnectedMultiStepContinuationClaim("
            f"claim_request_id={self.claim_request_id!r}, "
            f"loop_id={self.command.loop_id!r}, content='<none>')"
        )


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepContinuationSettlement:
    settlement_id: str
    claim_request_id: str
    claim_token: str
    owner_id: str
    loop_id: str
    claim_generation: int
    outcome: ConnectedMultiStepContinuationOutcome
    result_revision: int
    settled_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "settlement_id",
            "claim_request_id",
            "claim_token",
            "owner_id",
            "loop_id",
        ):
            _uuid(getattr(self, name), name)
        _positive(self.claim_generation, "claim_generation")
        _positive(self.result_revision, "result_revision")
        if not isinstance(self.outcome, ConnectedMultiStepContinuationOutcome):
            raise ValueError("continuation outcome is invalid")
        object.__setattr__(self, "settled_at", _time(self.settled_at, "settled_at"))


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepContinuationBatchResult:
    candidates_considered: int
    claims_acquired: int
    terminal_count: int
    failed_count: int

    def __post_init__(self) -> None:
        for name in (
            "candidates_considered",
            "claims_acquired",
            "terminal_count",
            "failed_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError("continuation batch result is invalid")


class ConnectedMultiStepContinuationRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


class ConnectedMultiStepContinuationConnectionSource(Protocol):
    async def list_connections(
        self, *, owner_id: str
    ) -> tuple[ConnectedConnectionView, ...]: ...


_CANDIDATE_KEYS = frozenset(
    {"owner_id", "loop_id", "task_state_revision", "kind", "expires_at"}
)
_CLAIM_KEYS = frozenset(
    {
        "claim_request_id",
        "claim_token",
        "claim_generation",
        "loop_revision",
        "claim_expires_at",
        "claim_state",
        "kind",
        "loop_id",
        "owner_id",
        "session_id",
        "session_binding_sha256",
        "chat_id",
        "message_id",
        "turn_id",
        "turn_claim_token",
        "time_zone",
        "request_binding_sha256",
        "requested_at",
        "expires_at",
        "max_steps",
        "approval_step_id",
        "action_id",
        "approval_id",
    }
)
_SETTLEMENT_KEYS = frozenset(
    {
        "settlement_id",
        "claim_request_id",
        "claim_token",
        "owner_id",
        "loop_id",
        "claim_generation",
        "outcome",
        "result_revision",
        "settled_at",
    }
)
_LOOP_KEYS = frozenset(
    {
        "loop_id",
        "owner_id",
        "session_id",
        "session_binding_sha256",
        "chat_id",
        "message_id",
        "turn_id",
        "turn_claim_token",
        "time_zone",
        "request_binding_sha256",
        "status",
        "current_step",
        "max_steps",
        "task_state_revision",
        "pending_approval_id",
        "last_result_reference_id",
        "last_result_binding_sha256",
        "expires_at",
        "updated_at",
    }
)


def _one(value: object) -> object:
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError("database result is invalid")
        return value[0]
    return value


def _candidate(value: object) -> ConnectedMultiStepContinuationCandidate:
    if type(value) is not dict or set(value) != _CANDIDATE_KEYS:
        raise ValueError("continuation candidate is invalid")
    return ConnectedMultiStepContinuationCandidate(
        owner_id=value["owner_id"],
        loop_id=value["loop_id"],
        task_state_revision=value["task_state_revision"],
        kind=ConnectedMultiStepContinuationKind(value["kind"]),
        expires_at=_time(value["expires_at"]),
    )


def _claim(value: object) -> ConnectedMultiStepContinuationClaim:
    value = _one(value)
    if type(value) is not dict or set(value) != _CLAIM_KEYS:
        raise ValueError("continuation claim is invalid")
    command = ConnectedMultiStepStartCommand(
        loop_id=value["loop_id"],
        owner_id=value["owner_id"],
        session_id=value["session_id"],
        session_binding_sha256=value["session_binding_sha256"],
        chat_id=value["chat_id"],
        message_id=value["message_id"],
        turn_id=value["turn_id"],
        turn_claim_token=value["turn_claim_token"],
        time_zone=value["time_zone"],
        request_binding_sha256=value["request_binding_sha256"],
        requested_at=_time(value["requested_at"]),
        expires_at=_time(value["expires_at"]),
        max_steps=value["max_steps"],
    )
    return ConnectedMultiStepContinuationClaim(
        claim_request_id=value["claim_request_id"],
        claim_token=value["claim_token"],
        claim_generation=value["claim_generation"],
        loop_revision=value["loop_revision"],
        claim_expires_at=_time(value["claim_expires_at"]),
        claim_state=ConnectedMultiStepContinuationClaimState(value["claim_state"]),
        kind=ConnectedMultiStepContinuationKind(value["kind"]),
        command=command,
        approval_step_id=value["approval_step_id"],
        action_id=value["action_id"],
        approval_id=value["approval_id"],
    )


def _settlement(value: object) -> ConnectedMultiStepContinuationSettlement:
    value = _one(value)
    if type(value) is not dict or set(value) != _SETTLEMENT_KEYS:
        raise ValueError("continuation settlement is invalid")
    return ConnectedMultiStepContinuationSettlement(
        settlement_id=value["settlement_id"],
        claim_request_id=value["claim_request_id"],
        claim_token=value["claim_token"],
        owner_id=value["owner_id"],
        loop_id=value["loop_id"],
        claim_generation=value["claim_generation"],
        outcome=ConnectedMultiStepContinuationOutcome(value["outcome"]),
        result_revision=value["result_revision"],
        settled_at=_time(value["settled_at"]),
    )


def _loop(value: object) -> ConnectedMultiStepLoopRecord:
    value = _one(value)
    if type(value) is not dict or set(value) != _LOOP_KEYS:
        raise ValueError("continuation loop result is invalid")
    return ConnectedMultiStepLoopRecord(
        loop_id=value["loop_id"],
        owner_id=value["owner_id"],
        session_id=value["session_id"],
        session_binding_sha256=value["session_binding_sha256"],
        chat_id=value["chat_id"],
        message_id=value["message_id"],
        turn_id=value["turn_id"],
        turn_claim_token=value["turn_claim_token"],
        time_zone=value["time_zone"],
        request_binding_sha256=value["request_binding_sha256"],
        status=ConnectedMultiStepStatus(value["status"]),
        current_step=value["current_step"],
        max_steps=value["max_steps"],
        task_state_revision=value["task_state_revision"],
        pending_approval_id=value["pending_approval_id"],
        last_result_reference_id=value["last_result_reference_id"],
        last_result_binding_sha256=value["last_result_binding_sha256"],
        expires_at=_time(value["expires_at"]),
        updated_at=_time(value["updated_at"]),
    )


class SupabaseConnectedMultiStepContinuationStore:
    """Strict service-role adapter for 68500 continuation metadata and custody."""

    def __init__(self, database: ConnectedMultiStepContinuationRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("continuation database is invalid")
        self._database = database

    async def _call(self, name: str, payload: dict[str, object]) -> object:
        try:
            return await self._database.rpc(name, payload, retry_transient=False)
        except Exception:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED", retryable=True
            ) from None

    async def list_runnable(
        self, *, maximum: int, now: datetime
    ) -> tuple[ConnectedMultiStepContinuationCandidate, ...]:
        _positive(maximum, "maximum", maximum=32)
        value = await self._call(
            "connected_multi_step_continuation_list_v1",
            {"p_maximum": maximum, "p_now": _time(now).isoformat()},
        )
        if not isinstance(value, list) or len(value) > maximum:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        try:
            result = tuple(_candidate(item) for item in value)
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None
        if len({item.loop_id for item in result}) != len(result):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        return result

    async def claim(
        self,
        *,
        candidate: ConnectedMultiStepContinuationCandidate,
        claim_request_id: str,
        claim_token: str,
        lease_seconds: int,
        now: datetime,
    ) -> ConnectedMultiStepContinuationClaim:
        if type(candidate) is not ConnectedMultiStepContinuationCandidate:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INVALID"
            )
        payload = {
            "p_owner_id": candidate.owner_id,
            "p_loop_id": candidate.loop_id,
            "p_expected_revision": candidate.task_state_revision,
            "p_claim_request_id": _uuid(claim_request_id, "claim_request_id"),
            "p_claim_token": _uuid(claim_token, "claim_token"),
            "p_now": _time(now).isoformat(),
            "p_lease_seconds": _positive(
                lease_seconds, "lease_seconds", maximum=120
            ),
        }
        try:
            result = _claim(
                await self._call("connected_multi_step_continuation_claim_v1", payload)
            )
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None
        if (
            result.command.owner_id != candidate.owner_id
            or result.command.loop_id != candidate.loop_id
            or result.loop_revision != candidate.task_state_revision
            or result.kind is not candidate.kind
            or result.claim_request_id != claim_request_id
            or result.claim_token != claim_token
            or result.claim_state is not ConnectedMultiStepContinuationClaimState.CLAIMED
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        return result

    async def read_claim(
        self, *, claim_request_id: str, claim_token: str
    ) -> ConnectedMultiStepContinuationClaim | None:
        value = await self._call(
            "connected_multi_step_continuation_read_claim_v1",
            {
                "p_claim_request_id": _uuid(claim_request_id, "claim_request_id"),
                "p_claim_token": _uuid(claim_token, "claim_token"),
            },
        )
        if value is None or value == []:
            return None
        try:
            result = _claim(value)
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None
        if result.claim_request_id != claim_request_id or result.claim_token != claim_token:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        if result.claim_state is not ConnectedMultiStepContinuationClaimState.CLAIMED:
            return None
        return result

    async def renew(
        self,
        *,
        claim: ConnectedMultiStepContinuationClaim,
        expected_revision: int,
        lease_seconds: int,
        now: datetime,
    ) -> ConnectedMultiStepContinuationClaim:
        if type(claim) is not ConnectedMultiStepContinuationClaim:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INVALID"
            )
        try:
            result = _claim(
                await self._call(
                    "connected_multi_step_continuation_renew_v1",
                    {
                        "p_owner_id": claim.command.owner_id,
                        "p_loop_id": claim.command.loop_id,
                        "p_claim_request_id": claim.claim_request_id,
                        "p_claim_token": claim.claim_token,
                        "p_claim_generation": claim.claim_generation,
                        "p_expected_revision": _positive(
                            expected_revision, "expected_revision"
                        ),
                        "p_now": _time(now).isoformat(),
                        "p_lease_seconds": _positive(
                            lease_seconds, "lease_seconds", maximum=120
                        ),
                    },
                )
            )
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None
        if (
            result.claim_request_id != claim.claim_request_id
            or result.claim_token != claim.claim_token
            or result.claim_generation != claim.claim_generation
            or result.command.loop_id != claim.command.loop_id
            or result.loop_revision != expected_revision
            or result.claim_state is not ConnectedMultiStepContinuationClaimState.CLAIMED
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        return result

    async def settle(
        self,
        *,
        claim: ConnectedMultiStepContinuationClaim,
        settlement_id: str,
        outcome: ConnectedMultiStepContinuationOutcome,
        result_revision: int,
        now: datetime,
    ) -> ConnectedMultiStepContinuationSettlement:
        if (
            type(claim) is not ConnectedMultiStepContinuationClaim
            or not isinstance(outcome, ConnectedMultiStepContinuationOutcome)
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INVALID"
            )
        try:
            result = _settlement(
                await self._call(
                    "connected_multi_step_continuation_settle_v1",
                    {
                        "p_owner_id": claim.command.owner_id,
                        "p_loop_id": claim.command.loop_id,
                        "p_claim_request_id": claim.claim_request_id,
                        "p_claim_token": claim.claim_token,
                        "p_claim_generation": claim.claim_generation,
                        "p_settlement_id": _uuid(settlement_id, "settlement_id"),
                        "p_outcome": outcome.value,
                        "p_result_revision": _positive(
                            result_revision, "result_revision"
                        ),
                        "p_now": _time(now).isoformat(),
                    },
                )
            )
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None
        if (
            result.settlement_id != settlement_id
            or result.claim_request_id != claim.claim_request_id
            or result.claim_token != claim.claim_token
            or result.claim_generation != claim.claim_generation
            or result.owner_id != claim.command.owner_id
            or result.loop_id != claim.command.loop_id
            or result.outcome is not outcome
            or result.result_revision != result_revision
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        return result

    async def read_settlement(
        self,
        *,
        settlement_id: str,
        claim_request_id: str,
        claim_token: str,
    ) -> ConnectedMultiStepContinuationSettlement | None:
        value = await self._call(
            "connected_multi_step_continuation_read_settlement_v1",
            {
                "p_settlement_id": _uuid(settlement_id, "settlement_id"),
                "p_claim_request_id": _uuid(
                    claim_request_id, "claim_request_id"
                ),
                "p_claim_token": _uuid(claim_token, "claim_token"),
            },
        )
        if value is None or value == []:
            return None
        try:
            result = _settlement(value)
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None
        if (
            result.settlement_id != settlement_id
            or result.claim_request_id != claim_request_id
            or result.claim_token != claim_token
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        return result

    async def read_instruction(
        self, *, claim: ConnectedMultiStepContinuationClaim, now: datetime
    ) -> str:
        if type(claim) is not ConnectedMultiStepContinuationClaim:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INVALID"
            )
        value = _one(
            await self._call(
                "connected_multi_step_continuation_instruction_v1",
                {
                    "p_owner_id": claim.command.owner_id,
                    "p_loop_id": claim.command.loop_id,
                    "p_claim_request_id": claim.claim_request_id,
                    "p_claim_token": claim.claim_token,
                    "p_claim_generation": claim.claim_generation,
                    "p_now": _time(now).isoformat(),
                },
            )
        )
        if type(value) is not dict or set(value) != {
            "version",
            "owner_id",
            "loop_id",
            "chat_id",
            "message_id",
            "instruction",
        }:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INSTRUCTION_INVALID"
            )
        instruction = value["instruction"]
        if (
            value["version"] != 1
            or value["owner_id"] != claim.command.owner_id
            or value["loop_id"] != claim.command.loop_id
            or value["chat_id"] != claim.command.chat_id
            or value["message_id"] != claim.command.message_id
            or type(instruction) is not str
            or not instruction.strip()
            or len(instruction.encode("utf-8")) > _MAX_INSTRUCTION_BYTES
            or any(0xD800 <= ord(character) <= 0xDFFF for character in instruction)
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INSTRUCTION_INVALID"
            )
        return instruction

    async def fail(
        self,
        *,
        claim: ConnectedMultiStepContinuationClaim,
        expected_revision: int,
        reason: str,
        now: datetime,
    ) -> ConnectedMultiStepLoopRecord:
        if type(claim) is not ConnectedMultiStepContinuationClaim or reason not in {
            "instruction_missing",
            "instruction_invalid",
            "connections_missing",
            "connections_invalid",
        }:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INVALID"
            )
        try:
            result = _loop(
                await self._call(
                    "connected_multi_step_continuation_fail_v1",
                    {
                        "p_owner_id": claim.command.owner_id,
                        "p_loop_id": claim.command.loop_id,
                        "p_claim_request_id": claim.claim_request_id,
                        "p_claim_token": claim.claim_token,
                        "p_claim_generation": claim.claim_generation,
                        "p_expected_revision": _positive(
                            expected_revision, "expected_revision"
                        ),
                        "p_reason": reason,
                        "p_now": _time(now).isoformat(),
                    },
                )
            )
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None
        if (
            result.owner_id != claim.command.owner_id
            or result.loop_id != claim.command.loop_id
            or result.status
            not in {ConnectedMultiStepStatus.FAILED, ConnectedMultiStepStatus.CANCELLED}
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        return result


class ConnectedMultiStepInstructionSource:
    """Reconstruct and authenticate the original user instruction."""

    def __init__(
        self,
        *,
        store: SupabaseConnectedMultiStepContinuationStore,
        binding_key: ConnectedChatBindingKey,
    ) -> None:
        if not isinstance(store, SupabaseConnectedMultiStepContinuationStore) or type(
            binding_key
        ) is not ConnectedChatBindingKey:
            raise TypeError("continuation instruction dependency is invalid")
        self._store, self._binding_key = store, binding_key

    async def resolve(
        self, *, claim: ConnectedMultiStepContinuationClaim, now: datetime
    ) -> str:
        instruction = await self._store.read_instruction(claim=claim, now=now)
        command = claim.command
        try:
            material = ConnectedChatRequestMaterial(
                owner_id=command.owner_id,
                session_id=command.session_id,
                chat_id=command.chat_id,
                message_id=command.message_id,
                message=instruction,
                attachment_ids=(),
                time_zone=command.time_zone,
            )
        except ValueError:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INSTRUCTION_INVALID"
            ) from None
        if not hmac.compare_digest(
            material.session_binding_sha256(self._binding_key),
            command.session_binding_sha256,
        ) or not hmac.compare_digest(
            material.request_binding_sha256(self._binding_key),
            command.request_binding_sha256,
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_INSTRUCTION_INVALID"
            )
        return instruction

    def __repr__(self) -> str:
        return "ConnectedMultiStepInstructionSource(content='<durable-chat-only>')"


class ConnectedMultiStepContinuationWorker:
    """Claim, rehydrate, resume, and continue a bounded set of durable loops."""

    def __init__(
        self,
        *,
        store: SupabaseConnectedMultiStepContinuationStore,
        instructions: ConnectedMultiStepInstructionSource,
        connections: ConnectedMultiStepContinuationConnectionSource,
        worker: ConnectedOperatorMultiStepWorker,
        require_ready: Callable[[], None],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_id: Callable[[], str] = lambda: str(uuid4()),
        lease_seconds: int = 90,
    ) -> None:
        if (
            not isinstance(store, SupabaseConnectedMultiStepContinuationStore)
            or not isinstance(instructions, ConnectedMultiStepInstructionSource)
            or not callable(getattr(connections, "list_connections", None))
            or not isinstance(worker, ConnectedOperatorMultiStepWorker)
            or not callable(require_ready)
            or not callable(now)
            or not callable(new_id)
        ):
            raise TypeError("continuation worker dependency is invalid")
        _positive(lease_seconds, "lease_seconds", maximum=120)
        self._store, self._instructions = store, instructions
        self._connections, self._worker = connections, worker
        self._require_ready, self._now, self._new_id = require_ready, now, new_id
        self._lease_seconds = lease_seconds

    @staticmethod
    def _loop_result(
        value: ConnectedMultiStepSettlement | ConnectedMultiStepLoopRecord,
    ) -> ConnectedMultiStepLoopRecord:
        if type(value) is ConnectedMultiStepSettlement:
            return value.loop
        if type(value) is ConnectedMultiStepLoopRecord:
            return value
        raise ConnectedMultiStepContinuationError(
            "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
        )

    @staticmethod
    def _outcome(loop: ConnectedMultiStepLoopRecord) -> ConnectedMultiStepContinuationOutcome:
        if loop.status is ConnectedMultiStepStatus.WAITING_APPROVAL:
            return ConnectedMultiStepContinuationOutcome.WAITING_APPROVAL
        if loop.status is ConnectedMultiStepStatus.CANCELLED:
            return ConnectedMultiStepContinuationOutcome.CANCELLED
        if loop.status is ConnectedMultiStepStatus.FAILED:
            return ConnectedMultiStepContinuationOutcome.FAILED
        if loop.terminal:
            return ConnectedMultiStepContinuationOutcome.TERMINAL
        return ConnectedMultiStepContinuationOutcome.RETRYABLE

    def _ids(self) -> tuple[str, str]:
        try:
            return _uuid(self._new_id(), "claim_request_id"), _uuid(
                self._new_id(), "claim_token"
            )
        except (TypeError, ValueError):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            ) from None

    async def _claim_one(
        self, candidate: ConnectedMultiStepContinuationCandidate
    ) -> ConnectedMultiStepContinuationClaim | None:
        request_id, token = self._ids()
        now = _time(self._now())
        try:
            return await self._store.claim(
                candidate=candidate,
                claim_request_id=request_id,
                claim_token=token,
                lease_seconds=self._lease_seconds,
                now=now,
            )
        except ConnectedMultiStepContinuationError:
            try:
                result = await self._store.read_claim(
                    claim_request_id=request_id,
                    claim_token=token,
                )
                if result is not None and result.claim_expires_at <= _time(self._now()):
                    return None
                return result
            except ConnectedMultiStepContinuationError:
                return None

    async def _settle(
        self,
        *,
        claim: ConnectedMultiStepContinuationClaim,
        loop: ConnectedMultiStepLoopRecord,
        outcome: ConnectedMultiStepContinuationOutcome,
    ) -> ConnectedMultiStepContinuationSettlement | None:
        settlement_id = str(
            uuid5(_CONTINUATION_NAMESPACE, f"{claim.claim_request_id}:settlement")
        )
        try:
            return await self._store.settle(
                claim=claim,
                settlement_id=settlement_id,
                outcome=outcome,
                result_revision=loop.task_state_revision,
                now=_time(self._now()),
            )
        except ConnectedMultiStepContinuationError:
            try:
                return await self._store.read_settlement(
                    settlement_id=settlement_id,
                    claim_request_id=claim.claim_request_id,
                    claim_token=claim.claim_token,
                )
            except ConnectedMultiStepContinuationError:
                return None

    async def _deterministic_failure(
        self,
        *,
        claim: ConnectedMultiStepContinuationClaim,
        expected_revision: int,
        reason: str,
    ) -> ConnectedMultiStepLoopRecord:
        result = await self._store.fail(
            claim=claim,
            expected_revision=expected_revision,
            reason=reason,
            now=_time(self._now()),
        )
        return result

    async def _current_loop(
        self, claim: ConnectedMultiStepContinuationClaim
    ) -> ConnectedMultiStepLoopRecord:
        return await self._worker.status(command=claim.command)

    @staticmethod
    def _active_connections(
        values: object, *, now: datetime
    ) -> tuple[ConnectedConnectionView, ...]:
        if not isinstance(values, tuple) or any(
            type(item) is not ConnectedConnectionView for item in values
        ):
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
            )
        return tuple(
            item
            for item in values
            if item.authorization_state is ConnectionAuthorizationState.ACTIVE
            and item.authorization_snapshot_sha256 is not None
            and item.expires_at is not None
            and item.expires_at > now
            and bool(item.granted_actions)
        )

    async def _run_claim(
        self, claim: ConnectedMultiStepContinuationClaim
    ) -> ConnectedMultiStepLoopRecord:
        self._require_ready()
        try:
            instruction = await self._instructions.resolve(
                claim=claim, now=_time(self._now())
            )
        except ConnectedMultiStepContinuationError as exc:
            if exc.code != "CONNECTED_MULTI_STEP_CONTINUATION_INSTRUCTION_INVALID":
                raise
            return await self._deterministic_failure(
                claim=claim,
                expected_revision=(await self._current_loop(claim)).task_state_revision,
                reason="instruction_invalid",
            )

        try:
            current_connections = await self._connections.list_connections(
                owner_id=claim.command.owner_id
            )
            active = self._active_connections(
                current_connections, now=_time(self._now())
            )
        except ConnectedMultiStepContinuationError:
            raise
        except Exception:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_FAILED", retryable=True
            ) from None
        if not active:
            return await self._deterministic_failure(
                claim=claim,
                expected_revision=(await self._current_loop(claim)).task_state_revision,
                reason="connections_missing",
            )

        loop = await self._current_loop(claim)
        if loop.terminal:
            return loop
        if claim.kind is ConnectedMultiStepContinuationKind.APPROVED_WRITE:
            if (
                claim.approval_step_id is None
                or claim.action_id is None
                or claim.approval_id is None
            ):
                raise ConnectedMultiStepContinuationError(
                    "CONNECTED_MULTI_STEP_CONTINUATION_FAILED"
                )
            loop = await self._worker.resume_after_approval(
                command=claim.command,
                step_id=claim.approval_step_id,
                action_id=claim.action_id,
                approval_id=claim.approval_id,
            )
            if loop.terminal:
                return loop

        claim = await self._store.renew(
            claim=claim,
            expected_revision=loop.task_state_revision,
            lease_seconds=self._lease_seconds,
            now=_time(self._now()),
        )
        self._require_ready()
        return self._loop_result(
            await self._worker.wake(
                command=claim.command,
                instruction=instruction,
                connections=active,
                wake_id=str(
                    uuid5(_CONTINUATION_NAMESPACE, f"{claim.claim_request_id}:wake")
                ),
            )
        )

    async def run_bounded(
        self, *, maximum: int = 8
    ) -> ConnectedMultiStepContinuationBatchResult:
        _positive(maximum, "maximum", maximum=32)
        try:
            self._require_ready()
        except Exception:
            raise ConnectedMultiStepContinuationError(
                "CONNECTED_MULTI_STEP_CONTINUATION_NOT_READY", retryable=True
            ) from None
        candidates = await self._store.list_runnable(
            maximum=maximum,
            now=_time(self._now()),
        )
        claims_acquired = terminal_count = failed_count = 0
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.loop_id in seen:
                continue
            seen.add(candidate.loop_id)
            claim = await self._claim_one(candidate)
            if claim is None:
                continue
            claims_acquired += 1
            try:
                loop = await self._run_claim(claim)
                outcome = self._outcome(loop)
            except asyncio.CancelledError:
                raise
            except Exception:
                failed_count += 1
                try:
                    loop = await self._current_loop(claim)
                    outcome = self._outcome(loop)
                    if not loop.terminal and loop.status is not ConnectedMultiStepStatus.WAITING_APPROVAL:
                        outcome = ConnectedMultiStepContinuationOutcome.RETRYABLE
                except Exception:
                    # The lease expires and another host can reconcile the exact
                    # same durable step.  Never invent a settlement without the
                    # database-authored current loop revision.
                    continue
            settlement = await self._settle(claim=claim, loop=loop, outcome=outcome)
            if settlement is None:
                failed_count += 1
            elif outcome in {
                ConnectedMultiStepContinuationOutcome.TERMINAL,
                ConnectedMultiStepContinuationOutcome.FAILED,
                ConnectedMultiStepContinuationOutcome.CANCELLED,
            }:
                terminal_count += 1
        return ConnectedMultiStepContinuationBatchResult(
            candidates_considered=len(candidates),
            claims_acquired=claims_acquired,
            terminal_count=terminal_count,
            failed_count=failed_count,
        )

    def __repr__(self) -> str:
        return "ConnectedMultiStepContinuationWorker(content='<none>', authority='database')"


__all__ = [
    "ConnectedMultiStepContinuationBatchResult",
    "ConnectedMultiStepContinuationCandidate",
    "ConnectedMultiStepContinuationClaim",
    "ConnectedMultiStepContinuationClaimState",
    "ConnectedMultiStepContinuationError",
    "ConnectedMultiStepContinuationKind",
    "ConnectedMultiStepContinuationOutcome",
    "ConnectedMultiStepContinuationSettlement",
    "ConnectedMultiStepContinuationWorker",
    "ConnectedMultiStepInstructionSource",
    "SupabaseConnectedMultiStepContinuationStore",
]
