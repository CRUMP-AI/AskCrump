"""Durable provider-authoritative preview reads for calendar cancellation.

Cancellation review is unusual: a human must see the current provider event
*before* approving the write, but credentials may only cross a durable,
owner-bound action fence.  This module creates a distinct ``calendar.get``
child action, then runs it through the ordinary action ledger and one-use
credential runtime.  The browser and planning model never supply authority or
an opaque payload reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from typing import Callable, Protocol, overload
from uuid import UUID, uuid5

from .connected_app_action_preparation import (
    ConnectedActionPreparationCommand,
    ConnectedActionPreparationView,
    action_preparation_result_matches,
)
from .connected_app_agent import ConnectedOperatorPlan
from .connected_app_chat_operator import ConnectedOperatorActionContext
from .connected_app_contracts import CalendarCancelRequest, CalendarGetRequest, EventSnapshot
from .connected_app_operator_adapters import ConnectedOperatorAuthoritySource
from .connected_app_payload_envelope import ConnectedActionPayloadEnvelope
from .connected_app_payload_resolution import ConnectedActionPayloadResolver
from .connected_app_payload_vault import ConnectedPayloadVault
from .connected_app_plan_once import ConnectedPlanBindingKey, ConnectedPlanOnceCommand
from .connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from .connected_app_runtime import (
    ConnectedActionOutcome,
    ConnectedAppRuntime,
    ConnectedReadObservation,
)
from .connected_app_scheduler import ConnectedScheduleClaim
from .connected_app_service import ConnectedConnectionAuthorityView


_IDENTITY_NAMESPACE = UUID("cf34ed6d-d637-57be-87cc-f95bb390891a")
_MAX_SNAPSHOT_AGE = timedelta(minutes=5)
_CLOCK_SKEW = timedelta(seconds=5)
_SHA256 = frozenset("0123456789abcdef")


class ConnectedCalendarCancelSnapshotError(RuntimeError):
    """Content-free failure at the pre-approval provider-read boundary."""

    _CODES = frozenset(
        {
            "CONNECTED_CANCEL_SNAPSHOT_AUTHORITY_CHANGED",
            "CONNECTED_CANCEL_SNAPSHOT_EFFECT_UNKNOWN",
            "CONNECTED_CANCEL_SNAPSHOT_FAILED",
            "CONNECTED_CANCEL_SNAPSHOT_INVALID",
            "CONNECTED_CANCEL_SNAPSHOT_STALE",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code if code in self._CODES else "CONNECTED_CANCEL_SNAPSHOT_FAILED"
        self.retryable = retryable is True
        super().__init__(self.code)


class ConnectedCalendarCancelSnapshotRPC(Protocol):
    async def rpc(
        self,
        function: str,
        params: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


class ConnectedCalendarCancelPreparationReadback(Protocol):
    async def readback_action_preparation(
        self,
        *,
        owner_id: str,
        request_id: str,
    ) -> ConnectedActionPreparationView | None: ...


class ConnectedCalendarCancelSnapshotStage(Protocol):
    async def prepare_chat(
        self,
        *,
        context: ConnectedOperatorActionContext,
        parent_plan_payload_id: str,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView: ...

    async def prepare_schedule(
        self,
        *,
        claim: ConnectedScheduleClaim,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView: ...

    async def authorize_chat(
        self,
        *,
        context: ConnectedOperatorActionContext,
        parent_plan_payload_id: str,
        command: ConnectedActionPreparationCommand,
    ) -> None: ...

    async def authorize_schedule(
        self,
        *,
        claim: ConnectedScheduleClaim,
        command: ConnectedActionPreparationCommand,
    ) -> None: ...


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID") from None
    if value != canonical:
        raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
    return value


def _aware(value: object, name: str) -> datetime:
    del name
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
    return value.astimezone(UTC)


def _sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256 for character in value)
    ):
        raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
    return value


def _identity(seed: str, label: str) -> str:
    return str(uuid5(_IDENTITY_NAMESPACE, f"{_uuid(seed, 'seed')}:{label}"))


def _schedule_session_binding(claim: ConnectedScheduleClaim) -> str:
    values = {
        "version": "connected-calendar-cancel-snapshot-schedule-v1",
        "ownerId": claim.owner_id,
        "scheduleId": claim.schedule_id,
        "claimId": claim.claim_id,
        "turnId": claim.turn_id,
        "connectionId": claim.connection_id,
        "occurrenceId": claim.occurrence_id,
        "taskStateRevision": claim.task_state_revision,
        "authorizationRevision": claim.authorization_revision,
        "authorizationSnapshotSha256": claim.authorization_snapshot_sha256,
    }
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def _resource_version_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _command_payload(command: ConnectedActionPreparationCommand) -> dict[str, object]:
    return {
        "p_request_id": command.request_id,
        "p_session_id": command.session_id,
        "p_session_binding_sha256": command.session_binding_sha256,
        "p_command_binding_sha256": command.command_binding_sha256,
        "p_grant_id": command.grant_id,
        "p_action_id": command.action_id,
        "p_task_id": command.task_id,
        "p_connection_id": command.connection_id,
        "p_provider": command.provider.value,
        "p_resource": command.resource.value,
        "p_action": command.action.value,
        "p_authorization_revision": command.authorization_revision,
        "p_authorization_snapshot_sha256": command.authorization_snapshot_sha256,
        "p_granted_actions_sha256": command.granted_actions_sha256,
        "p_granted_scopes_sha256": command.granted_scopes_sha256,
        "p_task_state_revision": command.task_state_revision,
        "p_parameters_payload_id": command.payload.payload_id,
        "p_parameters_reference_binding_sha256": command.payload.binding_sha256,
        "p_parameters_sha256": command.payload.payload_sha256,
        "p_resource_version_sha256": command.resource_version_sha256,
        "p_policy_version": ConnectedActionPolicy.version,
        "p_requested_at": command.requested_at.isoformat(),
        "p_expires_at": command.expires_at.isoformat(),
    }


class SupabaseConnectedCalendarCancelSnapshotStage:
    """Exact service-role adapter for the two snapshot-preparation RPCs."""

    def __init__(
        self,
        *,
        database: ConnectedCalendarCancelSnapshotRPC,
        preparations: ConnectedCalendarCancelPreparationReadback,
    ) -> None:
        if not callable(getattr(database, "rpc", None)) or not callable(
            getattr(preparations, "readback_action_preparation", None)
        ):
            raise TypeError("calendar cancellation snapshot stage is invalid")
        self._database = database
        self._preparations = preparations

    async def _prepare(
        self,
        *,
        function: str,
        params: dict[str, object],
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView:
        if type(command) is not ConnectedActionPreparationCommand:
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
        for attempt in range(2):
            try:
                await self._database.rpc(function, params, retry_transient=False)
                break
            except Exception:
                if attempt:
                    raise ConnectedCalendarCancelSnapshotError(
                        "CONNECTED_CANCEL_SNAPSHOT_FAILED", retryable=True
                    ) from None
        try:
            result = await self._preparations.readback_action_preparation(
                owner_id=command.owner_id,
                request_id=command.request_id,
            )
        except Exception:
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_FAILED", retryable=True
            ) from None
        if not action_preparation_result_matches(command, result):
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_EFFECT_UNKNOWN"
            )
        assert result is not None
        return result

    async def _authorize(
        self,
        *,
        function: str,
        params: dict[str, object],
        command: ConnectedActionPreparationCommand,
    ) -> None:
        result: object = None
        for attempt in range(2):
            try:
                result = await self._database.rpc(
                    function,
                    params,
                    retry_transient=False,
                )
                break
            except Exception:
                if attempt:
                    raise ConnectedCalendarCancelSnapshotError(
                        "CONNECTED_CANCEL_SNAPSHOT_EFFECT_UNKNOWN"
                    ) from None
        if (
            type(result) is not dict
            or result.get("request_id") != command.request_id
            or result.get("action_id") != command.action_id
            or result.get("status") != "started"
            or not isinstance(result.get("updated_at"), str)
            or not result["updated_at"]
        ):
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_EFFECT_UNKNOWN"
            )

    async def prepare_chat(
        self,
        *,
        context: ConnectedOperatorActionContext,
        parent_plan_payload_id: str,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView:
        if (
            type(context) is not ConnectedOperatorActionContext
            or command.owner_id != context.request.owner_id
            or command.session_id != context.request.session_id
            or command.turn_id != context.turn_id
            or not hmac.compare_digest(
                command.session_binding_sha256,
                context.origin_session_binding_sha256,
            )
        ):
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
        params = _command_payload(command)
        params.update(
            {
                "p_owner_id": context.request.owner_id,
                "p_chat_id": context.request.chat_id,
                "p_message_id": context.request.message_id,
                "p_turn_id": context.turn_id,
                "p_claim_token": context.claim_token,
                "p_origin_session_binding_sha256": context.origin_session_binding_sha256,
                "p_request_binding_sha256": context.request_binding_sha256,
                "p_parent_plan_payload_id": _uuid(
                    parent_plan_payload_id, "parent_plan_payload_id"
                ),
            }
        )
        return await self._prepare(
            function="connected_app_prepare_cancel_snapshot_chat_v1",
            params=params,
            command=command,
        )

    async def prepare_schedule(
        self,
        *,
        claim: ConnectedScheduleClaim,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView:
        if (
            type(claim) is not ConnectedScheduleClaim
            or claim.occurrence_id is None
            or claim.turn_id is None
            or claim.authorization_revision is None
            or claim.authorization_snapshot_sha256 is None
            or claim.granted_actions_sha256 is None
            or claim.granted_scopes_sha256 is None
            or command.owner_id != claim.owner_id
            or command.turn_id != claim.turn_id
            or command.connection_id != claim.connection_id
        ):
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
        params = _command_payload(command)
        params.update(
            {
                "p_owner_id": claim.owner_id,
                "p_schedule_id": claim.schedule_id,
                "p_claim_id": claim.claim_id,
                "p_occurrence_id": claim.occurrence_id,
                "p_turn_id": claim.turn_id,
            }
        )
        return await self._prepare(
            function="connected_app_prepare_cancel_snapshot_schedule_v1",
            params=params,
            command=command,
        )

    async def authorize_chat(
        self,
        *,
        context: ConnectedOperatorActionContext,
        parent_plan_payload_id: str,
        command: ConnectedActionPreparationCommand,
    ) -> None:
        if (
            type(context) is not ConnectedOperatorActionContext
            or command.owner_id != context.request.owner_id
            or command.session_id != context.request.session_id
            or command.turn_id != context.turn_id
        ):
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
        await self._authorize(
            function="connected_app_begin_cancel_snapshot_chat_v1",
            params={
                "p_owner_id": context.request.owner_id,
                "p_session_id": context.request.session_id,
                "p_chat_id": context.request.chat_id,
                "p_message_id": context.request.message_id,
                "p_turn_id": context.turn_id,
                "p_claim_token": context.claim_token,
                "p_origin_session_binding_sha256": (
                    context.origin_session_binding_sha256
                ),
                "p_request_binding_sha256": context.request_binding_sha256,
                "p_parent_plan_payload_id": _uuid(
                    parent_plan_payload_id,
                    "parent_plan_payload_id",
                ),
                "p_request_id": command.request_id,
                "p_action_id": command.action_id,
                "p_command_binding_sha256": command.command_binding_sha256,
            },
            command=command,
        )

    async def authorize_schedule(
        self,
        *,
        claim: ConnectedScheduleClaim,
        command: ConnectedActionPreparationCommand,
    ) -> None:
        if (
            type(claim) is not ConnectedScheduleClaim
            or claim.occurrence_id is None
            or claim.turn_id is None
            or command.owner_id != claim.owner_id
            or command.turn_id != claim.turn_id
            or command.connection_id != claim.connection_id
        ):
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
        await self._authorize(
            function="connected_app_begin_cancel_snapshot_schedule_v1",
            params={
                "p_owner_id": claim.owner_id,
                "p_schedule_id": claim.schedule_id,
                "p_claim_id": claim.claim_id,
                "p_occurrence_id": claim.occurrence_id,
                "p_turn_id": claim.turn_id,
                "p_request_id": command.request_id,
                "p_action_id": command.action_id,
                "p_command_binding_sha256": command.command_binding_sha256,
            },
            command=command,
        )

    def __repr__(self) -> str:
        return "SupabaseConnectedCalendarCancelSnapshotStage(database='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class _SnapshotContext:
    owner_id: str
    session_id: str
    session_binding_sha256: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    task_state_revision: int
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    requested_at: datetime
    expires_at: datetime
    seed: str
    parent_plan_payload_id: str | None
    chat_context: ConnectedOperatorActionContext | None
    schedule_claim: ConnectedScheduleClaim | None


class ConnectedCalendarCancelSnapshotCoordinator:
    """Run one exact ``calendar.get`` before cancellation review."""

    def __init__(
        self,
        *,
        planning_key: ConnectedPlanBindingKey,
        authorities: ConnectedOperatorAuthoritySource,
        payload_vault: ConnectedPayloadVault,
        payloads: ConnectedActionPayloadResolver,
        stage: ConnectedCalendarCancelSnapshotStage,
        runtime: ConnectedAppRuntime,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(planning_key) is not ConnectedPlanBindingKey:
            raise TypeError("calendar cancellation planning key is invalid")
        for value, methods, name in (
            (authorities, ("get_connection_authority",), "authority source"),
            (payload_vault, ("seal_json",), "payload vault"),
            (payloads, ("resolve",), "payload resolver"),
            (
                stage,
                (
                    "prepare_chat",
                    "prepare_schedule",
                    "authorize_chat",
                    "authorize_schedule",
                ),
                "snapshot stage",
            ),
            (runtime, ("run",), "runtime"),
        ):
            if any(not callable(getattr(value, method, None)) for method in methods):
                raise TypeError(f"calendar cancellation {name} is invalid")
        if not callable(now):
            raise TypeError("calendar cancellation clock is invalid")
        self._planning_key = planning_key
        self._authorities = authorities
        self._vault = payload_vault
        self._payloads = payloads
        self._stage = stage
        self._runtime = runtime
        self._now = now

    @overload
    async def read_authoritative_event(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> EventSnapshot: ...

    @overload
    async def read_authoritative_event(
        self,
        *,
        claim: ConnectedScheduleClaim,
        request: CalendarCancelRequest,
    ) -> EventSnapshot: ...

    async def read_authoritative_event(
        self,
        *,
        context: ConnectedOperatorActionContext | None = None,
        plan: ConnectedOperatorPlan | None = None,
        claim: ConnectedScheduleClaim | None = None,
        request: CalendarCancelRequest | None = None,
    ) -> EventSnapshot:
        now = _aware(self._now(), "now")
        if context is not None or plan is not None:
            if claim is not None or request is not None:
                raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
            snapshot_context, cancel = await self._chat_context(context, plan, now)
        else:
            snapshot_context, cancel = self._schedule_context(claim, request, now)
        return await self._run(snapshot_context, cancel, now)

    async def _chat_context(
        self,
        context: ConnectedOperatorActionContext | None,
        plan: ConnectedOperatorPlan | None,
        now: datetime,
    ) -> tuple[_SnapshotContext, CalendarCancelRequest]:
        if (
            type(context) is not ConnectedOperatorActionContext
            or type(plan) is not ConnectedOperatorPlan
            or plan.action is not ConnectorActionKind.CALENDAR_CANCEL
            or plan.resource is not ConnectorResource.CALENDAR
            or type(plan.request) is not CalendarCancelRequest
        ):
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
        try:
            authority = await self._authorities.get_connection_authority(
                owner_id=context.request.owner_id,
                connection_id=plan.connection_id,
            )
        except Exception:
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_FAILED", retryable=True
            ) from None
        if (
            type(authority) is not ConnectedConnectionAuthorityView
            or authority.connection_id != plan.connection_id
            or authority.provider is not plan.provider
            or authority.resource is not ConnectorResource.CALENDAR
            or ConnectorActionKind.CALENDAR_CANCEL not in authority.granted_actions
            or ConnectorActionKind.CALENDAR_GET not in authority.granted_actions
            or authority.expires_at <= now
        ):
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_AUTHORITY_CHANGED"
            )
        plan_command = ConnectedPlanOnceCommand.build(
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
        expires_at = min(
            context.expires_at,
            authority.expires_at,
            context.requested_at + _MAX_SNAPSHOT_AGE,
        )
        if expires_at <= now:
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_STALE")
        return (
            _SnapshotContext(
                owner_id=context.request.owner_id,
                session_id=context.request.session_id,
                session_binding_sha256=context.origin_session_binding_sha256,
                turn_id=context.turn_id,
                connection_id=plan.connection_id,
                provider=plan.provider,
                task_state_revision=1,
                authorization_revision=authority.authorization_revision,
                authorization_snapshot_sha256=authority.authorization_snapshot_sha256,
                granted_actions_sha256=action_set_sha256(authority.granted_actions),
                granted_scopes_sha256=authority.granted_scopes_sha256,
                requested_at=context.requested_at,
                expires_at=expires_at,
                seed=context.turn_id,
                parent_plan_payload_id=plan_command.payload_id,
                chat_context=context,
                schedule_claim=None,
            ),
            plan.request,
        )

    @staticmethod
    def _schedule_context(
        claim: ConnectedScheduleClaim | None,
        request: CalendarCancelRequest | None,
        now: datetime,
    ) -> tuple[_SnapshotContext, CalendarCancelRequest]:
        if (
            type(claim) is not ConnectedScheduleClaim
            or type(request) is not CalendarCancelRequest
            or claim.action is not ConnectorActionKind.CALENDAR_CANCEL
            or claim.resource is not ConnectorResource.CALENDAR
            or claim.turn_id is None
            or claim.authorization_revision is None
            or claim.authorization_snapshot_sha256 is None
            or claim.granted_actions_sha256 is None
            or claim.granted_scopes_sha256 is None
            or claim.occurrence_id is None
            or claim.claim_expires_at <= now
        ):
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_INVALID")
        requested_at = claim.claimed_at
        expires_at = min(claim.claim_expires_at, requested_at + _MAX_SNAPSHOT_AGE)
        if expires_at <= now:
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_STALE")
        return (
            _SnapshotContext(
                owner_id=claim.owner_id,
                session_id=_identity(claim.claim_id, "schedule-session"),
                session_binding_sha256=_schedule_session_binding(claim),
                turn_id=claim.turn_id,
                connection_id=claim.connection_id,
                provider=claim.provider,
                task_state_revision=claim.task_state_revision,
                authorization_revision=claim.authorization_revision,
                authorization_snapshot_sha256=claim.authorization_snapshot_sha256,
                granted_actions_sha256=claim.granted_actions_sha256,
                granted_scopes_sha256=claim.granted_scopes_sha256,
                requested_at=requested_at,
                expires_at=expires_at,
                seed=claim.claim_id,
                parent_plan_payload_id=None,
                chat_context=None,
                schedule_claim=claim,
            ),
            request,
        )

    async def _run(
        self,
        context: _SnapshotContext,
        cancel: CalendarCancelRequest,
        now: datetime,
    ) -> EventSnapshot:
        request = CalendarGetRequest.build(
            calendar_id=cancel.calendar_id,
            event_id=cancel.event_id,
            expected_resource_version=cancel.expected_resource_version,
        )
        action_id = _identity(context.seed, "snapshot-action")
        payload_id = _identity(context.seed, "snapshot-payload")
        envelope = ConnectedActionPayloadEnvelope.build(
            action=ConnectorActionKind.CALENDAR_GET,
            request=request,
        )
        try:
            payload_ref = await self._vault.seal_json(
                payload_id=payload_id,
                owner_id=context.owner_id,
                connection_id=context.connection_id,
                action_id=action_id,
                provider=context.provider,
                action=ConnectorActionKind.CALENDAR_GET,
                value=envelope.to_value(),
                created_at=context.requested_at,
                expires_at=context.expires_at,
            )
            command = ConnectedActionPreparationCommand.build(
                request_id=_identity(context.seed, "snapshot-preparation"),
                owner_id=context.owner_id,
                session_id=context.session_id,
                session_binding_sha256=context.session_binding_sha256,
                grant_id=_identity(context.seed, "snapshot-grant"),
                action_id=action_id,
                task_id=_identity(context.seed, "snapshot-task"),
                turn_id=context.turn_id,
                connection_id=context.connection_id,
                provider=context.provider,
                resource=ConnectorResource.CALENDAR,
                action=ConnectorActionKind.CALENDAR_GET,
                authorization_revision=context.authorization_revision,
                authorization_snapshot_sha256=context.authorization_snapshot_sha256,
                granted_actions_sha256=context.granted_actions_sha256,
                granted_scopes_sha256=context.granted_scopes_sha256,
                task_state_revision=context.task_state_revision,
                payload=payload_ref,
                resource_version_sha256=_resource_version_sha256(
                    cancel.expected_resource_version
                ),
                requested_at=context.requested_at,
                expires_at=context.expires_at,
            )
            if context.chat_context is not None:
                assert context.parent_plan_payload_id is not None
                preparation = await self._stage.prepare_chat(
                    context=context.chat_context,
                    parent_plan_payload_id=context.parent_plan_payload_id,
                    command=command,
                )
                await self._stage.authorize_chat(
                    context=context.chat_context,
                    parent_plan_payload_id=context.parent_plan_payload_id,
                    command=command,
                )
            else:
                assert context.schedule_claim is not None
                preparation = await self._stage.prepare_schedule(
                    claim=context.schedule_claim,
                    command=command,
                )
                await self._stage.authorize_schedule(
                    claim=context.schedule_claim,
                    command=command,
                )
            resolved = await self._payloads.resolve(
                payload_id=preparation.payload_id,
                intent=preparation.intent(),
            )
            result = await self._runtime.run(
                resolved.invocation,
                grant=preparation.grant(),
                approval=None,
                task_state_revision=preparation.task_state_revision,
            )
        except ConnectedCalendarCancelSnapshotError:
            raise
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            if "EFFECT_UNKNOWN" in code or "RESULT_INVALID" in code:
                raise ConnectedCalendarCancelSnapshotError(
                    "CONNECTED_CANCEL_SNAPSHOT_EFFECT_UNKNOWN"
                ) from None
            if "AUTHORITY" in code or "STALE" in code or "VERSION" in code:
                raise ConnectedCalendarCancelSnapshotError(
                    "CONNECTED_CANCEL_SNAPSHOT_AUTHORITY_CHANGED"
                ) from None
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_FAILED", retryable=True
            ) from None
        observation = result.provider_result
        if (
            result.outcome is not ConnectedActionOutcome.READ
            or result.operation_id != action_id
            or type(observation) is not ConnectedReadObservation
            or observation.operation_id != action_id
            or observation.provider is not context.provider
            or observation.resource is not ConnectorResource.CALENDAR
            or type(observation.value) is not EventSnapshot
        ):
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_EFFECT_UNKNOWN"
            )
        event = observation.value
        observed_at = observation.observed_at
        if observed_at > now + _CLOCK_SKEW or now - observed_at > _MAX_SNAPSHOT_AGE:
            raise ConnectedCalendarCancelSnapshotError("CONNECTED_CANCEL_SNAPSHOT_STALE")
        if (
            event.calendar_id != cancel.calendar_id
            or event.event_id != cancel.event_id
            or event.resource_version != cancel.expected_resource_version
            or observation.resource_version != cancel.expected_resource_version
        ):
            raise ConnectedCalendarCancelSnapshotError(
                "CONNECTED_CANCEL_SNAPSHOT_AUTHORITY_CHANGED"
            )
        return event

    def __repr__(self) -> str:
        return "ConnectedCalendarCancelSnapshotCoordinator(secrets='<redacted>')"


__all__ = [
    "ConnectedCalendarCancelSnapshotCoordinator",
    "ConnectedCalendarCancelSnapshotError",
    "ConnectedCalendarCancelSnapshotRPC",
    "ConnectedCalendarCancelSnapshotStage",
    "SupabaseConnectedCalendarCancelSnapshotStage",
]
