"""Durable ordinary-language chat orchestration for connected applications.

This module joins the already-reviewed chat claim, exactly-once planner, action
preparation/runtime boundary, optional durable scheduler, and atomic reply
completion.  It deliberately does not construct production dependencies or
enable the feature.  The HTTP route may call it only after the checked-in
source lock and the operator switch are both enabled.

The model is a proposal boundary only.  Connection authority, approval policy,
payload custody, provider execution, scheduling, and final persistence remain
durable server-side decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import json
from typing import Callable, Protocol
from uuid import UUID, uuid5

from .connected_app_agent import (
    ConnectedOperatorDisposition,
    ConnectedOperatorPlan,
    ConnectedOperatorPlanningResult,
    connected_operator_candidate,
    connected_operator_schedule_candidate,
)
from .connected_app_chat_completion import (
    ConnectedChatCompletionCommand,
    ConnectedChatCompletionKey,
    ConnectedChatCompletionKind,
    SupabaseConnectedChatCompletionStore,
)
from .connected_app_chat_turn import (
    ConnectedChatBindingKey,
    ConnectedChatRequestMaterial,
    ConnectedChatTurnClaim,
    ConnectedChatTurnState,
    SupabaseConnectedChatTurnStore,
)
from .connected_app_contracts import ConnectionAuthorizationState
from .connected_app_plan_once import (
    ConnectedPlanBindingKey,
    ConnectedPlanOnceCommand,
)
from .connected_app_multi_step import (
    ConnectedMultiStepLoopRecord,
    ConnectedMultiStepSettlement,
    ConnectedMultiStepStatus,
)
from .connected_app_policy import ConnectedActionPolicy
from .connected_app_service import ConnectedConnectionView


_ASSISTANT_NAMESPACE = UUID("08d813d4-8b2c-5a87-81c8-6e6324196df7")
_MAX_PUBLIC_BYTES = 1_048_576
_MAX_TEXT_BYTES = 100_000
_PLAN_LIFETIME = timedelta(minutes=10)


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


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} is invalid")
    return value.astimezone(UTC)


def _sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} is invalid")
    return value


def _text(value: object, name: str, *, maximum: int = _MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is invalid")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{name} is invalid")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f"{name} is invalid")
    return value


def _public_object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"{name} is invalid")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ValueError(f"{name} is invalid") from None
    if len(encoded) > _MAX_PUBLIC_BYTES:
        raise ValueError(f"{name} is invalid")
    return value  # type: ignore[return-value]


class ConnectedOperatorChatError(RuntimeError):
    """Fixed, content-free chat integration failure."""

    _ALLOWED = frozenset(
        {
            "CONNECTED_OPERATOR_CHAT_BUSY",
            "CONNECTED_OPERATOR_CHAT_FAILED",
            "CONNECTED_OPERATOR_CHAT_INVALID",
            "CONNECTED_OPERATOR_CHAT_NOT_READY",
            "CONNECTED_OPERATOR_CHAT_EFFECT_UNKNOWN",
            "CONNECTED_OPERATOR_ATTACHMENT_UNSUPPORTED",
        }
    )

    def __init__(
        self,
        code: str = "CONNECTED_OPERATOR_CHAT_FAILED",
        *,
        status_code: int = 503,
        retryable: bool = False,
        retry_after: int | None = None,
    ) -> None:
        self.code = code if code in self._ALLOWED else "CONNECTED_OPERATOR_CHAT_FAILED"
        self.status_code = status_code if status_code in {400, 409, 503} else 503
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(self.code)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedOperatorChatRequest:
    owner_id: str
    session_id: str = field(repr=False)
    chat_id: str
    message_id: str
    message: str = field(repr=False)
    attachment_ids: tuple[str, ...] = field(default=(), repr=False)
    time_zone: str = "UTC"

    def __post_init__(self) -> None:
        for name in ("owner_id", "session_id", "chat_id", "message_id"):
            _uuid(getattr(self, name), name)
        _text(self.message, "message", maximum=12_000)
        # ConnectedChatRequestMaterial performs the canonical attachment and
        # IANA-zone validation.  Constructing it here keeps bad client input
        # outside every database/model/provider boundary.
        self.material()

    def material(self) -> ConnectedChatRequestMaterial:
        return ConnectedChatRequestMaterial(
            owner_id=self.owner_id,
            session_id=self.session_id,
            chat_id=self.chat_id,
            message_id=self.message_id,
            message=self.message,
            attachment_ids=self.attachment_ids,
            time_zone=self.time_zone,
        )

    def __repr__(self) -> str:
        return (
            "ConnectedOperatorChatRequest("
            f"owner_id={self.owner_id!r}, chat_id={self.chat_id!r}, "
            f"message_id={self.message_id!r}, content='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedOperatorChatResponse:
    status_code: int
    content: dict[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.status_code) is not int or not 200 <= self.status_code <= 599:
            raise ValueError("status_code is invalid")
        _public_object(self.content, "content")

    def __repr__(self) -> str:
        return (
            f"ConnectedOperatorChatResponse(status_code={self.status_code}, content='<redacted>')"
        )


class ConnectedPreparedActionStatus(StrEnum):
    READY = "ready"
    PENDING_APPROVAL = "pending_approval"


@dataclass(frozen=True, slots=True)
class ConnectedOperatorPreparedAction:
    request_id: str
    action_id: str
    status: ConnectedPreparedActionStatus
    approval_id: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.request_id, "request_id")
        _uuid(self.action_id, "action_id")
        if not isinstance(self.status, ConnectedPreparedActionStatus):
            raise ValueError("prepared action status is invalid")
        if self.status is ConnectedPreparedActionStatus.PENDING_APPROVAL:
            _uuid(self.approval_id, "approval_id")
        elif self.approval_id is not None:
            raise ValueError("read preparation cannot contain approval")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedOperatorReadResult:
    action_id: str
    result_reference_id: str
    summary: str = field(repr=False)
    item_count: int

    def __post_init__(self) -> None:
        _uuid(self.action_id, "action_id")
        _uuid(self.result_reference_id, "result_reference_id")
        _text(self.summary, "summary", maximum=_MAX_TEXT_BYTES)
        if type(self.item_count) is not int or not 0 <= self.item_count <= 10_000:
            raise ValueError("item_count is invalid")

    def __repr__(self) -> str:
        return (
            "ConnectedOperatorReadResult("
            f"action_id={self.action_id!r}, item_count={self.item_count!r}, "
            "summary='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class ConnectedOperatorScheduleResult:
    schedule_id: str
    next_run_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.schedule_id, "schedule_id")
        object.__setattr__(self, "next_run_at", _aware(self.next_run_at, "next_run_at"))


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedOperatorActionContext:
    request: ConnectedOperatorChatRequest = field(repr=False)
    turn_id: str
    claim_token: str = field(repr=False)
    origin_session_binding_sha256: str = field(repr=False)
    request_binding_sha256: str = field(repr=False)
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if type(self.request) is not ConnectedOperatorChatRequest:
            raise ValueError("request is invalid")
        _uuid(self.turn_id, "turn_id")
        _uuid(self.claim_token, "claim_token")
        for name in ("origin_session_binding_sha256", "request_binding_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"{name} is invalid")
            try:
                int(value, 16)
            except ValueError:
                raise ValueError(f"{name} is invalid") from None
        requested = _aware(self.requested_at, "requested_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= requested or expires - requested > _PLAN_LIFETIME:
            raise ValueError("action context lifetime is invalid")
        object.__setattr__(self, "requested_at", requested)
        object.__setattr__(self, "expires_at", expires)


class ConnectedOperatorConnectionSource(Protocol):
    async def list_connections(self, *, owner_id: str) -> tuple[ConnectedConnectionView, ...]: ...


class ConnectedOperatorPlanOnce(Protocol):
    async def plan_once(
        self,
        command: ConnectedPlanOnceCommand,
        *,
        message: str,
        connections: tuple[ConnectedConnectionView, ...],
        user_time_zone: str,
    ) -> ConnectedOperatorPlanningResult: ...


class ConnectedOperatorActionBoundary(Protocol):
    """Trusted encrypted-payload preparation and read-only runtime boundary."""

    async def prepare(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> ConnectedOperatorPreparedAction: ...

    async def execute_read(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
        preparation: ConnectedOperatorPreparedAction,
    ) -> ConnectedOperatorReadResult: ...


class ConnectedOperatorScheduleBoundary(Protocol):
    """Durable encrypted-template scheduler; never accepts client payload refs."""

    async def create(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> ConnectedOperatorScheduleResult: ...


class ConnectedOperatorMultiStepBoundary(Protocol):
    """Optional explicitly locked durable multi-operation chat boundary."""

    async def start_from_chat(
        self,
        *,
        context: ConnectedOperatorActionContext,
        connections: tuple[ConnectedConnectionView, ...],
        wake_id: str,
    ) -> ConnectedMultiStepSettlement | ConnectedMultiStepLoopRecord: ...


class ConnectedOperatorDelegatedResponder(Protocol):
    async def respond(
        self,
        *,
        request: ConnectedOperatorChatRequest,
    ) -> str: ...


class ConnectedOperatorChatService:
    """Exactly-once connected-operator orchestration for one chat message."""

    def __init__(
        self,
        *,
        binding_key: ConnectedChatBindingKey,
        planning_key: ConnectedPlanBindingKey,
        completion_key: ConnectedChatCompletionKey,
        turns: SupabaseConnectedChatTurnStore,
        plans: ConnectedOperatorPlanOnce,
        completions: SupabaseConnectedChatCompletionStore,
        connections: ConnectedOperatorConnectionSource,
        actions: ConnectedOperatorActionBoundary,
        delegated: ConnectedOperatorDelegatedResponder,
        schedules: ConnectedOperatorScheduleBoundary | None = None,
        multi_step: ConnectedOperatorMultiStepBoundary | None = None,
        multi_step_enabled: bool = False,
        composition_manifest_sha256: str,
        require_ready: Callable[[], None] = lambda: None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(binding_key) is not ConnectedChatBindingKey:
            raise TypeError("chat binding key is invalid")
        if type(planning_key) is not ConnectedPlanBindingKey:
            raise TypeError("planning binding key is invalid")
        if type(completion_key) is not ConnectedChatCompletionKey:
            raise TypeError("completion key is invalid")
        for value, methods, name in (
            (turns, ("claim",), "turn store"),
            (plans, ("plan_once",), "plan coordinator"),
            (completions, ("complete",), "completion store"),
            (connections, ("list_connections",), "connection source"),
            (actions, ("prepare", "execute_read"), "action boundary"),
            (delegated, ("respond",), "delegated responder"),
        ):
            if any(not callable(getattr(value, method, None)) for method in methods):
                raise TypeError(f"{name} is invalid")
        if schedules is not None and not callable(getattr(schedules, "create", None)):
            raise TypeError("schedule boundary is invalid")
        if multi_step is not None and not callable(
            getattr(multi_step, "start_from_chat", None)
        ):
            raise TypeError("multi-step boundary is invalid")
        if type(multi_step_enabled) is not bool or (multi_step_enabled and multi_step is None):
            raise ValueError("multi-step source lock is invalid")
        if not callable(require_ready) or not callable(now):
            raise TypeError("connected operator dependency is invalid")
        self._binding_key = binding_key
        self._planning_key = planning_key
        self._completion_key = completion_key
        self._turns = turns
        self._plans = plans
        self._completions = completions
        self._connections = connections
        self._actions = actions
        self._delegated = delegated
        self._schedules = schedules
        self._multi_step = multi_step
        self._multi_step_enabled = multi_step_enabled
        self._composition_manifest_sha256 = _sha256(
            composition_manifest_sha256,
            "composition_manifest_sha256",
        )
        self._require_ready = require_ready
        self._now = now

    @staticmethod
    def candidate(message: object) -> bool:
        return connected_operator_candidate(message)

    def require_ready(self) -> None:
        try:
            self._require_ready()
        except Exception:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_NOT_READY") from None

    @property
    def composition_manifest_sha256(self) -> str:
        return self._composition_manifest_sha256

    @staticmethod
    def _context(
        request: ConnectedOperatorChatRequest,
        claim: ConnectedChatTurnClaim,
        material: ConnectedChatRequestMaterial,
        key: ConnectedChatBindingKey,
        now: datetime,
    ) -> ConnectedOperatorActionContext:
        if claim.claim_token is None:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_INVALID", status_code=400)
        return ConnectedOperatorActionContext(
            request=request,
            turn_id=claim.turn_id,
            claim_token=claim.claim_token,
            origin_session_binding_sha256=material.session_binding_sha256(key),
            request_binding_sha256=material.request_binding_sha256(key),
            requested_at=now,
            expires_at=now + _PLAN_LIFETIME,
        )

    async def _complete(
        self,
        *,
        context: ConnectedOperatorActionContext,
        kind: ConnectedChatCompletionKind,
        text: str,
        card: dict[str, object],
    ) -> ConnectedOperatorChatResponse:
        text = _text(text, "assistant response")
        card = _public_object(card, "connected operator card")
        now = _aware(self._now(), "now")
        assistant_id = str(uuid5(_ASSISTANT_NAMESPACE, f"{context.turn_id}:assistant"))
        user_message: dict[str, object] = {
            "id": context.request.message_id,
            "role": "user",
            "content": context.request.message,
            "timestamp": now.isoformat(),
            "deliveryStatus": "seen",
            "replyStatus": "replied",
            "deliveryUpdatedAt": now.isoformat(),
            "seenAt": now.isoformat(),
        }
        assistant_message: dict[str, object] = {
            "id": assistant_id,
            "role": "assistant",
            "content": text,
            "timestamp": now.isoformat(),
            "origin": "connected_operator",
            "inReplyTo": context.request.message_id,
            "connectedOperator": card,
        }
        response_data: dict[str, object] = {
            "response": text,
            "assistantMessage": assistant_message,
            "connectedOperator": card,
            "model": "connected-operator",
        }
        command = ConnectedChatCompletionCommand.build(
            key=self._completion_key,
            owner_id=context.request.owner_id,
            session_id=context.request.session_id,
            turn_id=context.turn_id,
            chat_id=context.request.chat_id,
            message_id=context.request.message_id,
            assistant_message_id=assistant_id,
            claim_token=context.claim_token,
            origin_session_binding_sha256=context.origin_session_binding_sha256,
            request_binding_sha256=context.request_binding_sha256,
            kind=kind,
            title="Connected mail and calendar",
            user_message=user_message,
            assistant_message=assistant_message,
            response_data=response_data,
        )
        try:
            completion = await self._completions.complete(command)
        except Exception:
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_CHAT_EFFECT_UNKNOWN",
                retryable=False,
            ) from None
        return ConnectedOperatorChatResponse(
            status_code=200,
            content={"success": True, **completion.response_data},
        )

    async def _handle_multi_step(
        self,
        *,
        context: ConnectedOperatorActionContext,
        connections: tuple[ConnectedConnectionView, ...],
    ) -> ConnectedOperatorChatResponse:
        if not self._multi_step_enabled or self._multi_step is None:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_NOT_READY")
        wake_id = str(uuid5(_ASSISTANT_NAMESPACE, f"{context.turn_id}:multi-step-wake"))
        try:
            result = await self._multi_step.start_from_chat(
                context=context,
                connections=connections,
                wake_id=wake_id,
            )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            if "EFFECT_UNKNOWN" in code:
                raise ConnectedOperatorChatError(
                    "CONNECTED_OPERATOR_CHAT_EFFECT_UNKNOWN", retryable=False
                ) from None
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
            ) from None
        if type(result) not in {ConnectedMultiStepSettlement, ConnectedMultiStepLoopRecord}:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
        loop = result.loop if isinstance(result, ConnectedMultiStepSettlement) else result
        card: dict[str, object] = {
            "version": 1,
            "state": loop.status.value,
            "loopId": loop.loop_id,
            "currentStep": loop.current_step,
            "maxSteps": loop.max_steps,
        }
        if loop.last_result_reference_id is not None:
            card["resultReferenceId"] = loop.last_result_reference_id
        if loop.status is ConnectedMultiStepStatus.WAITING_APPROVAL:
            if (
                type(result) is not ConnectedMultiStepSettlement
                or result.action_id is None
                or result.approval_id is None
            ):
                raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
            card.update(
                {
                    "state": "pending_approval",
                    "actionId": result.action_id,
                    "approvalId": result.approval_id,
                }
            )
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.PENDING_APPROVAL,
                text=(
                    "I prepared the next connected action, but I have not carried it out. "
                    "Review the exact details and approve or deny it."
                ),
                card=card,
            )
        if loop.status is ConnectedMultiStepStatus.CLARIFICATION:
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.CLARIFICATION,
                text="I need a little more information before I can safely continue.",
                card=card,
            )
        if loop.status is ConnectedMultiStepStatus.COMPLETED:
            if loop.current_step == 0:
                # The connected planner determined that the initial candidate
                # was ordinary chat. Preserve the normal assistant response;
                # never claim that a connected action ran when no step did.
                try:
                    text = await self._delegated.respond(request=context.request)
                except Exception:
                    raise ConnectedOperatorChatError(
                        "CONNECTED_OPERATOR_CHAT_FAILED",
                        retryable=True,
                        retry_after=3,
                    ) from None
                return await self._complete(
                    context=context,
                    kind=ConnectedChatCompletionKind.DELEGATED,
                    text=text,
                    card={"version": 1, "state": "delegated"},
                )
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.ACTION_TERMINAL,
                text="I completed the connected mail and calendar steps in your request.",
                card=card,
            )
        if loop.status is ConnectedMultiStepStatus.LIMIT_REACHED:
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.ACTION_TERMINAL,
                text="I stopped safely after the eight-step limit.",
                card=card,
            )
        if loop.status in {
            ConnectedMultiStepStatus.CANCELLED,
            ConnectedMultiStepStatus.EXPIRED,
        }:
            return await self._complete(
                context=context,
                kind=(
                    ConnectedChatCompletionKind.ACTION_TERMINAL
                    if loop.current_step > 0
                    else ConnectedChatCompletionKind.DELEGATED
                ),
                text=(
                    "I stopped the connected request."
                    if loop.status is ConnectedMultiStepStatus.CANCELLED
                    else "The connected request expired before it could finish."
                ),
                card=card,
            )
        raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_EFFECT_UNKNOWN")

    async def handle(self, request: ConnectedOperatorChatRequest) -> ConnectedOperatorChatResponse:
        if type(request) is not ConnectedOperatorChatRequest:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_INVALID", status_code=400)
        self.require_ready()
        if not self.candidate(request.message):
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_INVALID", status_code=400)
        if request.attachment_ids:
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_ATTACHMENT_UNSUPPORTED",
                status_code=400,
            )
        material = request.material()
        try:
            claim = await self._turns.claim(material.command(self._binding_key))
        except Exception:
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
            ) from None
        if claim.state is ConnectedChatTurnState.COMPLETED:
            return ConnectedOperatorChatResponse(
                status_code=200,
                content={"success": True, **(claim.response_data or {}), "cached": True},
            )
        if claim.state is ConnectedChatTurnState.BUSY:
            return ConnectedOperatorChatResponse(
                status_code=409,
                content={
                    "success": False,
                    "code": "CONNECTED_OPERATOR_CHAT_BUSY",
                    "message": "Crump is already handling this connected request.",
                    "shouldRetry": True,
                    "retryAfter": 3,
                },
            )
        now = _aware(self._now(), "now")
        context = self._context(request, claim, material, self._binding_key, now)
        try:
            connections = await self._connections.list_connections(owner_id=request.owner_id)
        except Exception:
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
            ) from None
        if not isinstance(connections, tuple) or any(
            not isinstance(item, ConnectedConnectionView) for item in connections
        ):
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
        active_connections = tuple(
            item
            for item in connections
            if item.authorization_state is ConnectionAuthorizationState.ACTIVE
            and item.authorization_snapshot_sha256 is not None
            and item.expires_at is not None
            and item.expires_at > now
            and bool(item.granted_actions)
        )

        # The planner deliberately short-circuits when there is no active
        # connection and therefore does not advance the durable turn to
        # `planning`.  Complete this truthful answer as a delegated response,
        # the only completion kind permitted directly from `claimed`.
        if not active_connections:
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.DELEGATED,
                text="Connect the mail or calendar account you want Ask Crump to use first.",
                card={"version": 1, "state": "needs_connection"},
            )

        # Explicit recurrence is initial user authority, not something a
        # continuation may infer from untrusted tool output. Keep it on the
        # existing exactly-once plan/schedule path even when the bounded
        # multi-step source lock is enabled.
        if self._multi_step_enabled and not connected_operator_schedule_candidate(
            request.message
        ):
            return await self._handle_multi_step(
                context=context,
                connections=active_connections,
            )

        plan_command = ConnectedPlanOnceCommand.build(
            binding_key=self._planning_key,
            owner_id=request.owner_id,
            session_id=request.session_id,
            chat_id=request.chat_id,
            message_id=request.message_id,
            turn_id=claim.turn_id,
            claim_token=context.claim_token,
            origin_session_binding_sha256=context.origin_session_binding_sha256,
            request_binding_sha256=context.request_binding_sha256,
            requested_at=context.requested_at,
            expires_at=context.expires_at,
        )
        try:
            planning = await self._plans.plan_once(
                plan_command,
                message=request.message.strip(),
                connections=active_connections,
                user_time_zone=request.time_zone,
            )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            if code == "CONNECTED_PLAN_ONCE_BUSY":
                raise ConnectedOperatorChatError(
                    "CONNECTED_OPERATOR_CHAT_BUSY",
                    status_code=409,
                    retryable=True,
                    retry_after=3,
                ) from None
            if code == "CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN":
                raise ConnectedOperatorChatError(
                    "CONNECTED_OPERATOR_CHAT_EFFECT_UNKNOWN", retryable=False
                ) from None
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
            ) from None
        if type(planning) is not ConnectedOperatorPlanningResult:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")

        if planning.disposition is ConnectedOperatorDisposition.NONE:
            try:
                text = await self._delegated.respond(request=request)
            except Exception:
                raise ConnectedOperatorChatError(
                    "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
                ) from None
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.DELEGATED,
                text=text,
                card={"version": 1, "state": "delegated"},
            )

        if planning.disposition is ConnectedOperatorDisposition.CLARIFY:
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.CLARIFICATION,
                text=planning.question or "What would you like Ask Crump to do?",
                card={"version": 1, "state": "clarification"},
            )

        plan = planning.plan
        if plan is None:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
        if planning.disposition is ConnectedOperatorDisposition.SCHEDULE:
            if self._schedules is None:
                return await self._complete(
                    context=context,
                    kind=ConnectedChatCompletionKind.CLARIFICATION,
                    text=(
                        "Recurring connected actions are not enabled on this build yet. "
                        "I can help with the same mail or calendar task one time instead."
                    ),
                    card={"version": 1, "state": "schedule_unavailable"},
                )
            try:
                scheduled = await self._schedules.create(context=context, plan=plan)
            except Exception:
                raise ConnectedOperatorChatError(
                    "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
                ) from None
            if type(scheduled) is not ConnectedOperatorScheduleResult:
                raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.SCHEDULE_CREATED,
                text="I created the recurring connected task. You can pause or cancel it anytime.",
                card={
                    "version": 1,
                    "state": "schedule_created",
                    "scheduleId": scheduled.schedule_id,
                    "nextRunAt": scheduled.next_run_at.isoformat(),
                    "provider": plan.provider.value,
                    "action": plan.action.value,
                },
            )

        requirement = ConnectedActionPolicy.requirement(plan.action)
        try:
            prepared = await self._actions.prepare(context=context, plan=plan)
        except Exception:
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
            ) from None
        if type(prepared) is not ConnectedOperatorPreparedAction:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
        if requirement.mutates_external_state:
            if prepared.status is not ConnectedPreparedActionStatus.PENDING_APPROVAL:
                raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
            return await self._complete(
                context=context,
                kind=ConnectedChatCompletionKind.PENDING_APPROVAL,
                text=(
                    "I prepared this connected action, but I have not carried it out. "
                    "Review the exact details and approve or deny it."
                ),
                card={
                    "version": 1,
                    "state": "pending_approval",
                    "requestId": prepared.request_id,
                    "actionId": prepared.action_id,
                    "approvalId": prepared.approval_id,
                    "provider": plan.provider.value,
                    "resource": plan.resource.value,
                    "action": plan.action.value,
                },
            )

        if prepared.status is not ConnectedPreparedActionStatus.READY:
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
        try:
            result = await self._actions.execute_read(
                context=context,
                plan=plan,
                preparation=prepared,
            )
        except Exception as exc:
            if str(getattr(exc, "code", "")) in {
                "CONNECTED_ACTION_EFFECT_UNKNOWN",
                "CONNECTED_READ_RESULT_EFFECT_UNKNOWN",
            }:
                raise ConnectedOperatorChatError(
                    "CONNECTED_OPERATOR_CHAT_EFFECT_UNKNOWN", retryable=False
                ) from None
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_CHAT_FAILED", retryable=True, retry_after=3
            ) from None
        if (
            type(result) is not ConnectedOperatorReadResult
            or result.action_id != prepared.action_id
        ):
            raise ConnectedOperatorChatError("CONNECTED_OPERATOR_CHAT_FAILED")
        return await self._complete(
            context=context,
            kind=ConnectedChatCompletionKind.ACTION_TERMINAL,
            text=result.summary,
            card={
                "version": 1,
                "state": "completed",
                "actionId": result.action_id,
                "resultReferenceId": result.result_reference_id,
                "itemCount": result.item_count,
                "provider": plan.provider.value,
                "resource": plan.resource.value,
                "action": plan.action.value,
            },
        )

    def __repr__(self) -> str:
        return "ConnectedOperatorChatService(dependencies='<redacted>')"
