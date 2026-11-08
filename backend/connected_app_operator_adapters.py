"""Concrete adapters joining chat plans to encrypted actions and runtime reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
from typing import Callable, Protocol
from uuid import UUID, uuid5

from .connected_app_action_preparation import (
    ConnectedActionPreparationCommand,
    ConnectedActionPreparationStatus,
    ConnectedActionPreparationView,
)
from .connected_app_agent import ConnectedOperatorPlan
from .connected_app_chat_operator import (
    ConnectedOperatorActionContext,
    ConnectedOperatorPreparedAction,
    ConnectedOperatorReadResult,
    ConnectedPreparedActionStatus,
)
from .connected_app_contracts import (
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarUpdateRequest,
    EventSnapshot,
    MailDraftRequest,
    MailReplyRequest,
    MailSendRequest,
)
from .connected_app_payload_envelope import (
    ConnectedActionPayloadEnvelope,
    expected_resource_version,
)
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
from .connected_app_read_results import ConnectedReadResultCoordinator
from .connected_app_review_resolution import ConnectedApprovalReviewEnvelope
from .connected_app_runtime import (
    ConnectedActionOutcome,
    ConnectedAppRuntime,
    ConnectedReadObservation,
)
from .connected_app_service import (
    ConnectedCalendarReviewPayload,
    ConnectedConnectionAuthorityView,
    ConnectedMailReviewPayload,
)


_IDENTITY_NAMESPACE = UUID("215897d0-dbb2-5e7e-8b96-cdc73b7fc30f")


class ConnectedOperatorAdapterError(RuntimeError):
    _CODES = frozenset(
        {
            "CONNECTED_OPERATOR_ACTION_FAILED",
            "CONNECTED_OPERATOR_ACTION_INVALID",
            "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED",
            "CONNECTED_OPERATOR_ACTION_EFFECT_UNKNOWN",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code if code in self._CODES else "CONNECTED_OPERATOR_ACTION_FAILED"
        self.retryable = bool(retryable)
        super().__init__(self.code)


class ConnectedOperatorAuthoritySource(Protocol):
    async def get_connection_authority(
        self,
        *,
        owner_id: str,
        connection_id: str,
    ) -> ConnectedConnectionAuthorityView | None: ...


class ConnectedOperatorActionStage(Protocol):
    async def prepare(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan_payload_id: str,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView: ...

    async def begin_read(
        self,
        *,
        context: ConnectedOperatorActionContext,
        execution_request_id: str,
        preparation: ConnectedActionPreparationView,
    ) -> None: ...

    async def read_preparation(
        self,
        *,
        owner_id: str,
        request_id: str,
    ) -> ConnectedActionPreparationView | None: ...


class ConnectedOperatorMultiStepActionStage(Protocol):
    """Durable loop-aware action stage; model output is never authority."""

    async def prepare_step(
        self,
        *,
        context: ConnectedOperatorActionContext,
        binding: ConnectedOperatorMultiStepBinding,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView: ...

    async def begin_read_step(
        self,
        *,
        context: ConnectedOperatorActionContext,
        binding: ConnectedOperatorMultiStepBinding,
        execution_request_id: str,
        preparation: ConnectedActionPreparationView,
    ) -> None: ...

    async def read_preparation(
        self,
        *,
        owner_id: str,
        request_id: str,
    ) -> ConnectedActionPreparationView | None: ...


class ConnectedCalendarCancellationSnapshotSource(Protocol):
    async def read_authoritative_event(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> EventSnapshot: ...


def _identity(turn_id: str, label: str) -> str:
    return str(uuid5(_IDENTITY_NAMESPACE, f"{turn_id}:{label}"))


def _canonical_uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if canonical != value:
        raise ValueError(f"{name} is invalid")
    return value


def _sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} is invalid")
    return value


def _resource_version_sha256(plan: ConnectedOperatorPlan) -> str | None:
    version = expected_resource_version(plan.request)
    return None if version is None else hashlib.sha256(version.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedOperatorMultiStepBinding:
    """Exact, content-free bridge from one durable loop step to one action."""

    loop_id: str
    step_id: str
    step_index: int
    task_state_revision: int
    owner_id: str
    session_id: str
    session_binding_sha256: str
    chat_id: str
    message_id: str
    turn_id: str
    turn_claim_token: str
    request_binding_sha256: str
    time_zone: str
    planning_binding_sha256: str
    proposal_id: str
    proposal_sha256: str
    proposal_binding_sha256: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    loop_expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "loop_id",
            "step_id",
            "owner_id",
            "session_id",
            "chat_id",
            "message_id",
            "turn_id",
            "turn_claim_token",
            "proposal_id",
            "connection_id",
        ):
            _canonical_uuid(getattr(self, name), name)
        if type(self.step_index) is not int or not 0 <= self.step_index < 8:
            raise ValueError("step_index is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task_state_revision is invalid")
        for name in (
            "session_binding_sha256",
            "request_binding_sha256",
            "planning_binding_sha256",
            "proposal_sha256",
            "proposal_binding_sha256",
            "authorization_snapshot_sha256",
        ):
            _sha256(getattr(self, name), name)
        if not isinstance(self.time_zone, str) or not self.time_zone.strip():
            raise ValueError("time_zone is invalid")
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if not isinstance(self.action, ConnectorActionKind):
            raise ValueError("action is invalid")
        if ConnectedActionPolicy.requirement(self.action).resource is not self.resource:
            raise ValueError("action resource is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision is invalid")
        if (
            not isinstance(self.loop_expires_at, datetime)
            or self.loop_expires_at.tzinfo is None
            or self.loop_expires_at.utcoffset() is None
        ):
            raise ValueError("loop_expires_at is invalid")
        object.__setattr__(self, "loop_expires_at", self.loop_expires_at.astimezone(UTC))

    @classmethod
    def from_claim(
        cls,
        *,
        context: object,
        claim: object,
    ) -> ConnectedOperatorMultiStepBinding:
        from .connected_app_multi_step import (
            ConnectedMultiStepClaim,
            ConnectedMultiStepPlanningContext,
            ConnectedMultiStepProposalKind,
            ConnectedMultiStepState,
            step_id,
        )

        if (
            type(context) is not ConnectedMultiStepPlanningContext
            or type(claim) is not ConnectedMultiStepClaim
            or claim.state is not ConnectedMultiStepState.INVOKED
            or claim.proposal_kind is not ConnectedMultiStepProposalKind.ACTION
            or claim.step_id != context.step_id
            or claim.step_index != context.step_index
            or claim.step_id != step_id(claim.loop.loop_id, claim.step_index)
            or claim.planning_binding_sha256 != context.planning_binding_sha256
            or claim.proposal_id is None
            or claim.proposal_sha256 is None
            or claim.proposal_binding_sha256 is None
            or claim.connection_id is None
            or claim.provider is None
            or claim.resource is None
            or claim.action is None
            or claim.authorization_revision is None
            or claim.authorization_snapshot_sha256 is None
        ):
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")
        command, loop = context.command, claim.loop
        if (
            loop.loop_id != command.loop_id
            or loop.owner_id != command.owner_id
            or loop.session_id != command.session_id
            or not hmac.compare_digest(
                loop.session_binding_sha256, command.session_binding_sha256
            )
            or loop.chat_id != command.chat_id
            or loop.message_id != command.message_id
            or loop.turn_id != command.turn_id
            or loop.turn_claim_token != command.turn_claim_token
            or loop.time_zone != command.time_zone
            or not hmac.compare_digest(
                loop.request_binding_sha256, command.request_binding_sha256
            )
            or loop.expires_at != command.expires_at
        ):
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")
        return cls(
            loop_id=loop.loop_id,
            step_id=claim.step_id,
            step_index=claim.step_index,
            task_state_revision=loop.task_state_revision,
            owner_id=loop.owner_id,
            session_id=loop.session_id,
            session_binding_sha256=loop.session_binding_sha256,
            chat_id=loop.chat_id,
            message_id=loop.message_id,
            turn_id=loop.turn_id,
            turn_claim_token=loop.turn_claim_token,
            request_binding_sha256=loop.request_binding_sha256,
            time_zone=loop.time_zone,
            planning_binding_sha256=claim.planning_binding_sha256,
            proposal_id=claim.proposal_id,
            proposal_sha256=claim.proposal_sha256,
            proposal_binding_sha256=claim.proposal_binding_sha256,
            connection_id=claim.connection_id,
            provider=claim.provider,
            resource=claim.resource,
            action=claim.action,
            authorization_revision=claim.authorization_revision,
            authorization_snapshot_sha256=claim.authorization_snapshot_sha256,
            loop_expires_at=loop.expires_at,
        )

    def validate(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> None:
        if (
            context.request.owner_id != self.owner_id
            or context.request.session_id != self.session_id
            or context.request.chat_id != self.chat_id
            or context.request.message_id != self.message_id
            or context.request.time_zone != self.time_zone
            or context.turn_id != self.turn_id
            or context.claim_token != self.turn_claim_token
            or not hmac.compare_digest(
                context.origin_session_binding_sha256,
                self.session_binding_sha256,
            )
            or not hmac.compare_digest(
                context.request_binding_sha256,
                self.request_binding_sha256,
            )
            or context.expires_at > self.loop_expires_at
            or plan.connection_id != self.connection_id
            or plan.provider is not self.provider
            or plan.resource is not self.resource
            or plan.action is not self.action
        ):
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")

    def __repr__(self) -> str:
        return (
            "ConnectedOperatorMultiStepBinding("
            f"loop_id={self.loop_id!r}, step_id={self.step_id!r}, "
            f"step_index={self.step_index!r}, content='<redacted>')"
        )


class ConnectedOperatorActionCoordinator:
    """Seal, stage, and execute one exact connected action from a chat plan.

    Writes stop at a pending approval.  Reads cross the durable chat execution
    fence before the runtime can issue a one-use credential.  The coordinator
    never accepts a payload reference from the browser or model.
    """

    def __init__(
        self,
        *,
        planning_key: ConnectedPlanBindingKey,
        authorities: ConnectedOperatorAuthoritySource,
        payload_vault: ConnectedPayloadVault,
        payloads: ConnectedActionPayloadResolver,
        stage: ConnectedOperatorActionStage,
        runtime: ConnectedAppRuntime,
        durable_read_results_attested: bool,
        multi_step_stage: ConnectedOperatorMultiStepActionStage | None = None,
        cancellation_snapshots: ConnectedCalendarCancellationSnapshotSource | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(planning_key) is not ConnectedPlanBindingKey:
            raise TypeError("connected planning key is invalid")
        for value, methods, name in (
            (authorities, ("get_connection_authority",), "authority source"),
            (payload_vault, ("seal_json",), "payload vault"),
            (payloads, ("resolve",), "payload resolver"),
            (stage, ("prepare", "begin_read", "read_preparation"), "action stage"),
            (runtime, ("run",), "action runtime"),
        ):
            if any(not callable(getattr(value, method, None)) for method in methods):
                raise TypeError(f"connected {name} is invalid")
        if durable_read_results_attested is not True:
            raise ValueError("durable connected read results are required")
        if multi_step_stage is not None and any(
            not callable(getattr(multi_step_stage, method, None))
            for method in ("prepare_step", "begin_read_step", "read_preparation")
        ):
            raise TypeError("connected multi-step action stage is invalid")
        if cancellation_snapshots is not None and not callable(
            getattr(cancellation_snapshots, "read_authoritative_event", None)
        ):
            raise TypeError("calendar cancellation snapshot source is invalid")
        if not callable(now):
            raise TypeError("connected action clock is invalid")
        self._planning_key = planning_key
        self._authorities = authorities
        self._vault = payload_vault
        self._payloads = payloads
        self._stage = stage
        self._multi_step_stage = multi_step_stage
        self._runtime = runtime
        self._cancellation_snapshots = cancellation_snapshots
        self._now = now

    @staticmethod
    def _validate_plan_context(
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> None:
        if type(context) is not ConnectedOperatorActionContext or type(
            plan
        ) is not ConnectedOperatorPlan:
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")
        if context.expires_at <= context.requested_at:
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")

    def _plan_command(self, context: ConnectedOperatorActionContext) -> ConnectedPlanOnceCommand:
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

    async def _review_payload(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> tuple[ConnectedMailReviewPayload | ConnectedCalendarReviewPayload, EventSnapshot | None]:
        request = plan.request
        if type(request) in {MailDraftRequest, MailSendRequest, MailReplyRequest}:
            spec = request.spec
            return (
                ConnectedMailReviewPayload(
                    account=plan.connection_id,
                    to=spec.to,
                    cc=spec.cc,
                    bcc=spec.bcc,
                    subject=spec.subject,
                    body_text=spec.body_text,
                    reply_context=spec.reply_to_message_id,
                ),
                None,
            )
        if type(request) in {CalendarCreateRequest, CalendarUpdateRequest}:
            spec = request.spec
            return (
                ConnectedCalendarReviewPayload(
                    calendar=spec.calendar_id,
                    event_context=spec.source_event_id,
                    title=spec.title,
                    start=spec.starts_at.isoformat(),
                    end=spec.ends_at.isoformat(),
                    time_zone=spec.time_zone,
                    attendees=spec.attendees,
                    location=spec.location,
                    description=spec.description,
                ),
                None,
            )
        if type(request) is CalendarCancelRequest:
            if self._cancellation_snapshots is None:
                raise ConnectedOperatorAdapterError(
                    "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED"
                )
            try:
                event = await self._cancellation_snapshots.read_authoritative_event(
                    context=context,
                    plan=plan,
                )
            except Exception:
                raise ConnectedOperatorAdapterError(
                    "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED"
                ) from None
            if (
                type(event) is not EventSnapshot
                or event.calendar_id != request.calendar_id
                or event.event_id != request.event_id
                or event.resource_version != request.expected_resource_version
            ):
                raise ConnectedOperatorAdapterError(
                    "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED"
                )
            return (
                ConnectedCalendarReviewPayload(
                    calendar=event.calendar_id,
                    event_context=event.event_id,
                    title=event.title,
                    start=event.starts_at.isoformat(),
                    end=event.ends_at.isoformat(),
                    time_zone=event.time_zone,
                    attendees=event.attendees,
                    location=event.location,
                    description=event.description,
                ),
                event,
            )
        raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")

    async def prepare(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
    ) -> ConnectedOperatorPreparedAction:
        return await self._prepare(
            context=context,
            plan=plan,
            identity_seed=context.turn_id,
            multi_step_binding=None,
        )

    async def prepare_step(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
        binding: ConnectedOperatorMultiStepBinding,
    ) -> ConnectedOperatorPreparedAction:
        if (
            self._multi_step_stage is None
            or type(binding) is not ConnectedOperatorMultiStepBinding
        ):
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")
        binding.validate(context=context, plan=plan)
        return await self._prepare(
            context=context,
            plan=plan,
            identity_seed=binding.step_id,
            multi_step_binding=binding,
        )

    async def _prepare(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
        identity_seed: str,
        multi_step_binding: ConnectedOperatorMultiStepBinding | None,
    ) -> ConnectedOperatorPreparedAction:
        self._validate_plan_context(context, plan)
        _canonical_uuid(identity_seed, "identity_seed")
        try:
            authority = await self._authorities.get_connection_authority(
                owner_id=context.request.owner_id,
                connection_id=plan.connection_id,
            )
        except Exception:
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_FAILED", retryable=True
            ) from None
        now = self._now()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_FAILED")
        now = now.astimezone(UTC)
        if (
            type(authority) is not ConnectedConnectionAuthorityView
            or authority.connection_id != plan.connection_id
            or authority.provider is not plan.provider
            or authority.resource is not plan.resource
            or plan.action not in authority.granted_actions
            or authority.expires_at <= now
            or (
                multi_step_binding is not None
                and (
                    authority.authorization_revision
                    != multi_step_binding.authorization_revision
                    or not hmac.compare_digest(
                        authority.authorization_snapshot_sha256,
                        multi_step_binding.authorization_snapshot_sha256,
                    )
                )
            )
        ):
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED"
            )
        expires_at = min(context.expires_at.astimezone(UTC), authority.expires_at.astimezone(UTC))
        if expires_at <= now:
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED"
            )

        turn_id = context.turn_id
        request_id = _identity(identity_seed, "preparation-request")
        action_id = _identity(identity_seed, "action")
        task_id = _identity(identity_seed, "task")
        grant_id = _identity(identity_seed, "grant")
        payload_id = _identity(identity_seed, "action-payload")
        approval_id = _identity(identity_seed, "approval")
        preview_id = _identity(identity_seed, "approval-preview")
        action_envelope = ConnectedActionPayloadEnvelope.build(
            action=plan.action,
            request=plan.request,
        )
        try:
            payload_ref = await self._vault.seal_json(
                payload_id=payload_id,
                owner_id=context.request.owner_id,
                connection_id=plan.connection_id,
                action_id=action_id,
                provider=plan.provider,
                action=plan.action,
                value=action_envelope.to_value(),
                created_at=context.requested_at,
                expires_at=expires_at,
            )
        except Exception:
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_FAILED", retryable=True
            ) from None

        requirement = ConnectedActionPolicy.requirement(plan.action)
        review_ref = None
        if requirement.mutates_external_state:
            review_payload, authoritative_event = await self._review_payload(
                context=context,
                plan=plan,
            )
            review_envelope = ConnectedApprovalReviewEnvelope(
                approval_id=approval_id,
                action_id=action_id,
                connection_id=plan.connection_id,
                parameters_sha256=payload_ref.payload_sha256,
                resource_version_sha256=_resource_version_sha256(plan),
                action_payload=action_envelope,
                review_payload=review_payload,
                authoritative_event=authoritative_event,
            )
            try:
                review_ref = await self._vault.seal_json(
                    payload_id=preview_id,
                    owner_id=context.request.owner_id,
                    connection_id=plan.connection_id,
                    action_id=action_id,
                    provider=plan.provider,
                    action=plan.action,
                    value=review_envelope.to_value(),
                    created_at=context.requested_at,
                    expires_at=expires_at,
                )
            except Exception:
                raise ConnectedOperatorAdapterError(
                    "CONNECTED_OPERATOR_ACTION_FAILED", retryable=True
                ) from None

        command = ConnectedActionPreparationCommand.build(
            request_id=request_id,
            owner_id=context.request.owner_id,
            session_id=context.request.session_id,
            session_binding_sha256=context.origin_session_binding_sha256,
            grant_id=grant_id,
            action_id=action_id,
            task_id=task_id,
            turn_id=turn_id,
            connection_id=plan.connection_id,
            provider=plan.provider,
            resource=plan.resource,
            action=plan.action,
            authorization_revision=authority.authorization_revision,
            authorization_snapshot_sha256=authority.authorization_snapshot_sha256,
            granted_actions_sha256=action_set_sha256(authority.granted_actions),
            granted_scopes_sha256=authority.granted_scopes_sha256,
            task_state_revision=(
                1
                if multi_step_binding is None
                else multi_step_binding.task_state_revision
            ),
            payload=payload_ref,
            resource_version_sha256=_resource_version_sha256(plan),
            requested_at=context.requested_at,
            expires_at=expires_at,
            approval_id=approval_id if requirement.mutates_external_state else None,
            review_payload=review_ref,
        )
        try:
            if multi_step_binding is None:
                plan_command = self._plan_command(context)
                prepared = await self._stage.prepare(
                    context=context,
                    plan_payload_id=plan_command.payload_id,
                    command=command,
                )
            else:
                assert self._multi_step_stage is not None
                prepared = await self._multi_step_stage.prepare_step(
                    context=context,
                    binding=multi_step_binding,
                    command=command,
                )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            raise ConnectedOperatorAdapterError(
                (
                    "CONNECTED_OPERATOR_ACTION_EFFECT_UNKNOWN"
                    if code.endswith("RESULT_INVALID")
                    else "CONNECTED_OPERATOR_ACTION_FAILED"
                ),
                retryable=not code.endswith("RESULT_INVALID"),
            ) from None
        return ConnectedOperatorPreparedAction(
            request_id=prepared.request_id,
            action_id=prepared.action_id,
            status=(
                ConnectedPreparedActionStatus.PENDING_APPROVAL
                if prepared.status is ConnectedActionPreparationStatus.PENDING_APPROVAL
                else ConnectedPreparedActionStatus.READY
            ),
            approval_id=prepared.approval_id,
        )

    async def execute_read(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
        preparation: ConnectedOperatorPreparedAction,
    ) -> ConnectedOperatorReadResult:
        return await self._execute_read(
            context=context,
            plan=plan,
            preparation=preparation,
            identity_seed=context.turn_id,
            multi_step_binding=None,
        )

    async def execute_read_step(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
        preparation: ConnectedOperatorPreparedAction,
        binding: ConnectedOperatorMultiStepBinding,
    ) -> ConnectedOperatorReadResult:
        if (
            self._multi_step_stage is None
            or type(binding) is not ConnectedOperatorMultiStepBinding
        ):
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")
        binding.validate(context=context, plan=plan)
        return await self._execute_read(
            context=context,
            plan=plan,
            preparation=preparation,
            identity_seed=binding.step_id,
            multi_step_binding=binding,
        )

    async def _execute_read(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan: ConnectedOperatorPlan,
        preparation: ConnectedOperatorPreparedAction,
        identity_seed: str,
        multi_step_binding: ConnectedOperatorMultiStepBinding | None,
    ) -> ConnectedOperatorReadResult:
        self._validate_plan_context(context, plan)
        _canonical_uuid(identity_seed, "identity_seed")
        if (
            type(preparation) is not ConnectedOperatorPreparedAction
            or preparation.status is not ConnectedPreparedActionStatus.READY
        ):
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")
        stage = self._stage if multi_step_binding is None else self._multi_step_stage
        assert stage is not None
        try:
            record = await stage.read_preparation(
                owner_id=context.request.owner_id,
                request_id=preparation.request_id,
            )
        except Exception:
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_FAILED", retryable=True
            ) from None
        if (
            type(record) is not ConnectedActionPreparationView
            or record.request_id != preparation.request_id
            or record.owner_id != context.request.owner_id
            or record.turn_id != context.turn_id
            or record.connection_id != plan.connection_id
            or record.provider is not plan.provider
            or record.resource is not plan.resource
            or record.action is not plan.action
            or record.status is not ConnectedActionPreparationStatus.READY
        ):
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED"
            )
        execution_id = _identity(identity_seed, "read-execution")
        try:
            if multi_step_binding is None:
                await self._stage.begin_read(
                    context=context,
                    execution_request_id=execution_id,
                    preparation=record,
                )
            else:
                assert self._multi_step_stage is not None
                await self._multi_step_stage.begin_read_step(
                    context=context,
                    binding=multi_step_binding,
                    execution_request_id=execution_id,
                    preparation=record,
                )
            resolved = await self._payloads.resolve(
                payload_id=record.payload_id,
                intent=record.intent(),
            )
            result = await self._runtime.run(
                resolved.invocation,
                grant=record.grant(),
                approval=None,
                task_state_revision=record.task_state_revision,
            )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            if "EFFECT_UNKNOWN" in code or "EFFECT_POSSIBLE" in code:
                raise ConnectedOperatorAdapterError(
                    "CONNECTED_OPERATOR_ACTION_EFFECT_UNKNOWN"
                ) from None
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_FAILED", retryable=True
            ) from None
        if (
            result.outcome is not ConnectedActionOutcome.READ
            or result.operation_id != record.action_id
            or type(result.provider_result) is not ConnectedReadObservation
            or result.provider_result.operation_id != record.action_id
        ):
            raise ConnectedOperatorAdapterError(
                "CONNECTED_OPERATOR_ACTION_EFFECT_UNKNOWN"
            )
        value = result.provider_result.value
        item_count = len(value) if isinstance(value, (tuple, list)) else 1
        summaries = {
            ConnectorActionKind.MAIL_SEARCH: f"I found {item_count} matching message{'s' if item_count != 1 else ''}.",
            ConnectorActionKind.MAIL_GET: "I retrieved the requested message.",
            ConnectorActionKind.CALENDAR_LIST: f"I found {item_count} calendar event{'s' if item_count != 1 else ''}.",
            ConnectorActionKind.CALENDAR_GET: "I retrieved the requested calendar event.",
            ConnectorActionKind.CALENDAR_FREE_BUSY: f"I found {item_count} busy window{'s' if item_count != 1 else ''}.",
        }
        summary = summaries.get(plan.action)
        if summary is None:
            raise ConnectedOperatorAdapterError("CONNECTED_OPERATOR_ACTION_INVALID")
        return ConnectedOperatorReadResult(
            action_id=record.action_id,
            result_reference_id=ConnectedReadResultCoordinator.payload_id(record.action_id),
            summary=summary,
            item_count=item_count,
        )

    def __repr__(self) -> str:
        return "ConnectedOperatorActionCoordinator(secrets='<redacted>')"


__all__ = [
    "ConnectedCalendarCancellationSnapshotSource",
    "ConnectedOperatorActionCoordinator",
    "ConnectedOperatorActionStage",
    "ConnectedOperatorAdapterError",
    "ConnectedOperatorAuthoritySource",
    "ConnectedOperatorMultiStepActionStage",
    "ConnectedOperatorMultiStepBinding",
]
