from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import json

import pytest

from backend.connected_app_action_preparation import (
    ConnectedActionPreparationStatus,
    ConnectedActionPreparationView,
)
from backend.connected_app_agent import ConnectedOperatorDisposition, ConnectedOperatorPlan
from backend.connected_app_chat_operator import (
    ConnectedOperatorActionContext,
    ConnectedOperatorChatRequest,
)
from backend.connected_app_chat_action_stage import SupabaseConnectedChatActionStage
from backend.connected_app_contracts import (
    CalendarCancelRequest,
    ConnectionAuthorizationState,
    MailDraftSpec,
    MailQuery,
    MailSearchRequest,
    MailSendRequest,
    MessageSummary,
)
from backend.connected_app_operator_adapters import (
    ConnectedOperatorActionCoordinator,
    ConnectedOperatorAdapterError,
    ConnectedOperatorMultiStepBinding,
)
from backend.connected_app_payload_resolution import ConnectedActionPayloadResolver
from backend.connected_app_payload_vault import ConnectedPayloadRef
from backend.connected_app_plan_once import ConnectedPlanBindingKey
from backend.connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from backend.connected_app_runtime import (
    ConnectedActionOutcome,
    ConnectedActionRuntimeResult,
    ConnectedReadObservation,
    ConnectedReadTerminalRecord,
)
from backend.connected_app_service import (
    ConnectedConnectionAuthorityView,
)


NOW = datetime(2026, 11, 8, 5, 0, tzinfo=UTC)
OWNER = "10000000-0000-4000-8000-000000000001"
SESSION = "10000000-0000-4000-8000-000000000002"
CHAT = "10000000-0000-4000-8000-000000000003"
MESSAGE = "10000000-0000-4000-8000-000000000004"
TURN = "10000000-0000-4000-8000-000000000005"
CLAIM = "10000000-0000-4000-8000-000000000006"
CONNECTION = "10000000-0000-4000-8000-000000000007"
LOOP = "10000000-0000-4000-8000-000000000008"
STEP_ONE = "10000000-0000-4000-8000-000000000009"
STEP_TWO = "10000000-0000-4000-8000-00000000000a"
PROPOSAL_ONE = "10000000-0000-4000-8000-00000000000b"
PROPOSAL_TWO = "10000000-0000-4000-8000-00000000000c"
OTHER_OWNER = "10000000-0000-4000-8000-00000000000d"
OTHER_SESSION = "10000000-0000-4000-8000-00000000000e"
OTHER_TURN = "10000000-0000-4000-8000-00000000000f"


class MemoryPayloads:
    def __init__(self):
        self.references: dict[str, ConnectedPayloadRef] = {}
        self.values: dict[str, object] = {}

    async def seal_json(self, **kwargs):
        encoded = json.dumps(
            kwargs["value"], sort_keys=True, ensure_ascii=True, separators=(",", ":")
        ).encode("ascii")
        commitment = hashlib.sha256(kwargs["payload_id"].encode() + b"\0" + encoded).hexdigest()
        reference = ConnectedPayloadRef(
            payload_id=kwargs["payload_id"],
            owner_id=kwargs["owner_id"],
            connection_id=kwargs["connection_id"],
            action_id=kwargs["action_id"],
            provider=kwargs["provider"],
            action=kwargs["action"],
            commitment_key_id="test-commitment-1",
            payload_sha256=commitment,
            created_at=kwargs["created_at"],
            expires_at=kwargs["expires_at"],
        )
        existing = self.references.get(reference.payload_id)
        if existing is not None and existing != reference:
            raise RuntimeError("payload replay drift")
        self.references[reference.payload_id] = reference
        self.values[reference.payload_id] = kwargs["value"]
        return reference

    async def resolve_reference(self, **kwargs):
        reference = self.references.get(kwargs["payload_id"])
        if reference is None:
            return None
        assert reference.owner_id == kwargs["owner_id"]
        assert reference.connection_id == kwargs["connection_id"]
        assert reference.action_id == kwargs["action_id"]
        assert reference.provider is kwargs["provider"]
        assert reference.action is kwargs["action"]
        return reference

    async def open_json(self, reference):
        return self.values[reference.payload_id]


class Authorities:
    def __init__(self, actions):
        self.value = ConnectedConnectionAuthorityView(
            connection_id=CONNECTION,
            provider=ConnectorProvider.GOOGLE,
            resource=(
                ConnectorResource.MAIL
                if all(action.value.startswith("mail.") for action in actions)
                else ConnectorResource.CALENDAR
            ),
            authorization_state=ConnectionAuthorizationState.ACTIVE,
            authorization_revision=3,
            authorization_snapshot_sha256="a" * 64,
            granted_scopes_sha256="b" * 64,
            granted_actions=tuple(sorted(actions, key=lambda item: item.value)),
            expires_at=NOW + timedelta(hours=1),
        )

    async def get_connection_authority(self, **_):
        return self.value


def preparation_view(command) -> ConnectedActionPreparationView:
    requirement = ConnectedActionPolicy.requirement(command.action)
    review = command.review_payload
    return ConnectedActionPreparationView(
        request_id=command.request_id,
        owner_id=command.owner_id,
        command_binding_sha256=command.command_binding_sha256,
        grant_id=command.grant_id,
        action_id=command.action_id,
        task_id=command.task_id,
        turn_id=command.turn_id,
        connection_id=command.connection_id,
        provider=command.provider,
        resource=command.resource,
        action=command.action,
        authorization_revision=command.authorization_revision,
        authorization_snapshot_sha256=command.authorization_snapshot_sha256,
        granted_actions_sha256=command.granted_actions_sha256,
        granted_scopes_sha256=command.granted_scopes_sha256,
        grant_actions_sha256=action_set_sha256((command.action,)),
        task_state_revision=command.task_state_revision,
        payload_id=command.payload.payload_id,
        payload_reference_binding_sha256=command.payload.binding_sha256,
        parameters_sha256=command.payload.payload_sha256,
        resource_version_sha256=command.resource_version_sha256,
        policy_version=ConnectedActionPolicy.version,
        mutates_external_state=requirement.mutates_external_state,
        approval_class=requirement.approval_class,
        status=(
            ConnectedActionPreparationStatus.PENDING_APPROVAL
            if requirement.mutates_external_state
            else ConnectedActionPreparationStatus.READY
        ),
        approval_id=command.approval_id,
        approval_binding_sha256=command.approval_binding_sha256,
        preview_payload_id=None if review is None else review.payload_id,
        preview_reference_binding_sha256=None if review is None else review.binding_sha256,
        preview_sha256=None if review is None else review.payload_sha256,
        requested_at=command.requested_at,
        expires_at=command.expires_at,
    )


class Stage:
    def __init__(self):
        self.records = {}
        self.plan_payload_id = None
        self.begin_calls = []
        self.command = None

    async def prepare(self, *, context, plan_payload_id, command):
        del context
        self.plan_payload_id = plan_payload_id
        self.command = command
        result = preparation_view(command)
        self.records[result.request_id] = result
        return result

    async def read_preparation(self, *, owner_id, request_id):
        result = self.records.get(request_id)
        assert result is None or result.owner_id == owner_id
        return result

    async def readback_action_preparation(self, *, owner_id, request_id):
        return await self.read_preparation(owner_id=owner_id, request_id=request_id)

    async def begin_read(self, **kwargs):
        self.begin_calls.append(kwargs)


class MultiStepStage(Stage):
    def __init__(self):
        super().__init__()
        self.step_bindings = []

    async def prepare_step(self, *, context, binding, command):
        del context
        self.step_bindings.append(binding)
        self.command = command
        result = preparation_view(command)
        self.records[result.request_id] = result
        return result

    async def begin_read_step(self, **kwargs):
        self.step_bindings.append(kwargs["binding"])
        self.begin_calls.append(kwargs)


class Runtime:
    async def run(self, invocation, **_):
        terminal = ConnectedReadTerminalRecord(
            operation_id=invocation.intent.action_id,
            provider=invocation.intent.provider,
            resource=invocation.intent.resource,
            action=invocation.intent.action,
            binding_sha256=invocation.binding_sha256,
            authority_sha256="c" * 64,
            idempotency_key_hash=hashlib.sha256(
                invocation.intent.idempotency_key.encode()
            ).hexdigest(),
            observed_at=NOW,
        )
        observation = ConnectedReadObservation(
            operation_id=invocation.intent.action_id,
            provider=invocation.intent.provider,
            resource=invocation.intent.resource,
            value=(
                MessageSummary(
                    message_id="message-1",
                    resource_version="etag-1",
                    received_at=NOW,
                    subject="Untrusted subject",
                    sender="sender@example.com",
                ),
            ),
            observed_at=NOW,
        )
        return ConnectedActionRuntimeResult(
            operation_id=invocation.intent.action_id,
            outcome=ConnectedActionOutcome.READ,
            replayed=False,
            terminal=terminal,
            provider_result=observation,
        )


def context() -> ConnectedOperatorActionContext:
    request = ConnectedOperatorChatRequest(
        owner_id=OWNER,
        session_id=SESSION,
        chat_id=CHAT,
        message_id=MESSAGE,
        message="Check my recent email",
        time_zone="America/New_York",
    )
    return ConnectedOperatorActionContext(
        request=request,
        turn_id=TURN,
        claim_token=CLAIM,
        origin_session_binding_sha256="d" * 64,
        request_binding_sha256="e" * 64,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def coordinator(
    *,
    actions,
    payloads=None,
    stage=None,
    runtime=None,
    snapshots=None,
    multi_step_stage=None,
):
    payloads = payloads or MemoryPayloads()
    stage = stage or Stage()
    return (
        ConnectedOperatorActionCoordinator(
            planning_key=ConnectedPlanBindingKey("plan-key-1", b"p" * 32),
            authorities=Authorities(actions),
            payload_vault=payloads,
            payloads=ConnectedActionPayloadResolver(references=payloads, payloads=payloads),
            stage=stage,
            runtime=runtime or Runtime(),
            durable_read_results_attested=True,
            multi_step_stage=multi_step_stage,
            cancellation_snapshots=snapshots,
            now=lambda: NOW,
        ),
        payloads,
        stage,
    )


def read_plan() -> ConnectedOperatorPlan:
    return ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEARCH,
        request=MailSearchRequest.build(MailQuery(query="from:client", limit=10)),
        requires_approval=False,
    )


def multi_step_binding(
    *,
    step_id: str = STEP_ONE,
    step_index: int = 0,
    proposal_id: str = PROPOSAL_ONE,
) -> ConnectedOperatorMultiStepBinding:
    return ConnectedOperatorMultiStepBinding(
        loop_id=LOOP,
        step_id=step_id,
        step_index=step_index,
        task_state_revision=3 + step_index,
        owner_id=OWNER,
        session_id=SESSION,
        session_binding_sha256="d" * 64,
        chat_id=CHAT,
        message_id=MESSAGE,
        turn_id=TURN,
        turn_claim_token=CLAIM,
        request_binding_sha256="e" * 64,
        time_zone="America/New_York",
        planning_binding_sha256="f" * 64,
        proposal_id=proposal_id,
        proposal_sha256="1" * 64,
        proposal_binding_sha256="2" * 64,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEARCH,
        authorization_revision=3,
        authorization_snapshot_sha256="a" * 64,
        loop_expires_at=NOW + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_read_action_stages_then_executes_after_coordinator_restart():
    action = ConnectorActionKind.MAIL_SEARCH
    subject, payloads, stage = coordinator(actions=(action,))
    plan = ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=action,
        request=MailSearchRequest.build(MailQuery(query="from:client", limit=10)),
        requires_approval=False,
    )
    prepared = await subject.prepare(context=context(), plan=plan)
    assert prepared.status.value == "ready"
    assert stage.plan_payload_id is not None

    # A fresh process instance reconstructs the preparation from durable
    # readback; no in-memory cache is authority for execution.
    restarted, _, _ = coordinator(
        actions=(action,), payloads=payloads, stage=stage, runtime=Runtime()
    )
    result = await restarted.execute_read(
        context=context(), plan=plan, preparation=prepared
    )
    assert result.item_count == 1
    assert result.summary == "I found 1 matching message."
    assert stage.begin_calls[0]["preparation"].action_id == prepared.action_id
    assert "Untrusted subject" not in result.summary


@pytest.mark.asyncio
async def test_write_action_seals_review_then_stops_at_pending_approval():
    action = ConnectorActionKind.MAIL_SEND
    subject, payloads, _ = coordinator(actions=(action,))
    plan = ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=action,
        request=MailSendRequest.build(
            MailDraftSpec(
                to=("recipient@example.com",),
                subject="Private subject",
                body_text="Private body",
            )
        ),
        requires_approval=True,
    )
    prepared = await subject.prepare(context=context(), plan=plan)
    assert prepared.status.value == "pending_approval"
    assert prepared.approval_id is not None
    preview = next(
        value
        for value in payloads.values.values()
        if isinstance(value, dict) and value.get("version") == "connected-approval-review-envelope-v1"
    )
    assert "approvalBindingSha256" not in preview
    assert preview["reviewPayload"]["value"]["bodyText"] == "Private body"


@pytest.mark.asyncio
async def test_calendar_cancel_fails_closed_without_authoritative_snapshot():
    action = ConnectorActionKind.CALENDAR_CANCEL
    subject, _, _ = coordinator(actions=(action,))
    plan = ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=action,
        request=CalendarCancelRequest.build(
            calendar_id="primary",
            event_id="event-1",
            expected_resource_version="etag-1",
        ),
        requires_approval=True,
    )
    with pytest.raises(ConnectedOperatorAdapterError) as failure:
        await subject.prepare(context=context(), plan=plan)
    assert failure.value.code == "CONNECTED_OPERATOR_ACTION_AUTHORITY_CHANGED"


def test_coordinator_refuses_runtime_without_durable_read_results():
    payloads = MemoryPayloads()
    with pytest.raises(ValueError, match="durable connected read results"):
        ConnectedOperatorActionCoordinator(
            planning_key=ConnectedPlanBindingKey("plan-key-1", b"p" * 32),
            authorities=Authorities((ConnectorActionKind.MAIL_SEARCH,)),
            payload_vault=payloads,
            payloads=ConnectedActionPayloadResolver(references=payloads, payloads=payloads),
            stage=Stage(),
            runtime=Runtime(),
            durable_read_results_attested=False,
            now=lambda: NOW,
        )


@pytest.mark.asyncio
async def test_supabase_chat_stage_recovers_exact_prepare_response_loss_and_fences_read():
    action = ConnectorActionKind.MAIL_SEARCH
    builder, _, captured = coordinator(actions=(action,))
    plan = ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=action,
        request=MailSearchRequest.build(MailQuery(query="newer_than:1d", limit=5)),
        requires_approval=False,
    )
    prepared = await builder.prepare(context=context(), plan=plan)
    assert captured.command is not None

    class Database:
        def __init__(self):
            self.calls = []
            self.lost = True

        async def rpc(self, name, payload, **_):
            self.calls.append((name, payload))
            if name == "connected_operator_prepare_chat_action_v1":
                if self.lost:
                    self.lost = False
                    raise TimeoutError("response lost")
                return {"committed": True}
            return {
                "stage": "executing",
                "execution_request_id": payload["p_execution_request_id"],
                "preparation_request_id": payload["p_preparation_request_id"],
                "action_id": payload["p_action_id"],
                "updated_at": NOW.isoformat(),
            }

    database = Database()
    stage = SupabaseConnectedChatActionStage(database=database, preparations=captured)
    result = await stage.prepare(
        context=context(),
        plan_payload_id=captured.plan_payload_id,
        command=captured.command,
    )
    assert result.action_id == prepared.action_id
    assert [call[0] for call in database.calls[:2]] == [
        "connected_operator_prepare_chat_action_v1",
        "connected_operator_prepare_chat_action_v1",
    ]
    exact = database.calls[1][1]
    assert exact["p_payload_id"] == captured.plan_payload_id
    assert exact["p_parameters_payload_id"] == result.payload_id
    assert exact["p_session_binding_sha256"] == context().origin_session_binding_sha256

    await stage.begin_read(
        context=context(),
        execution_request_id="10000000-0000-4000-8000-000000000099",
        preparation=result,
    )
    assert database.calls[-1][0] == "connected_operator_begin_chat_read_v1"


@pytest.mark.asyncio
async def test_multi_step_ids_do_not_collide_for_two_steps_in_one_turn():
    stage = MultiStepStage()
    subject, _, _ = coordinator(
        actions=(ConnectorActionKind.MAIL_SEARCH,),
        multi_step_stage=stage,
    )
    first = await subject.prepare_step(
        context=context(),
        plan=read_plan(),
        binding=multi_step_binding(),
    )
    second = await subject.prepare_step(
        context=context(),
        plan=read_plan(),
        binding=multi_step_binding(
            step_id=STEP_TWO,
            step_index=1,
            proposal_id=PROPOSAL_TWO,
        ),
    )
    assert first.request_id != second.request_id
    assert first.action_id != second.action_id
    assert len(stage.records) == 2


@pytest.mark.asyncio
async def test_multi_step_exact_step_replay_reuses_every_identity():
    stage = MultiStepStage()
    subject, payloads, _ = coordinator(
        actions=(ConnectorActionKind.MAIL_SEARCH,),
        multi_step_stage=stage,
    )
    binding = multi_step_binding()
    first = await subject.prepare_step(
        context=context(), plan=read_plan(), binding=binding
    )
    second = await subject.prepare_step(
        context=context(), plan=read_plan(), binding=binding
    )
    assert second == first
    assert len(stage.records) == 1
    assert len(payloads.references) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("substitution", ("owner", "session", "turn"))
async def test_multi_step_rejects_cross_context_substitution(substitution):
    stage = MultiStepStage()
    subject, payloads, _ = coordinator(
        actions=(ConnectorActionKind.MAIL_SEARCH,),
        multi_step_stage=stage,
    )
    altered = context()
    if substitution == "owner":
        altered = replace(
            altered,
            request=replace(altered.request, owner_id=OTHER_OWNER),
        )
    elif substitution == "session":
        altered = replace(
            altered,
            request=replace(altered.request, session_id=OTHER_SESSION),
        )
    else:
        altered = replace(altered, turn_id=OTHER_TURN)
    with pytest.raises(ConnectedOperatorAdapterError) as denied:
        await subject.prepare_step(
            context=altered,
            plan=read_plan(),
            binding=multi_step_binding(),
        )
    assert denied.value.code == "CONNECTED_OPERATOR_ACTION_INVALID"
    assert not payloads.references
    assert not stage.records


def test_multi_step_binding_requires_canonical_uuid_identity_seed():
    with pytest.raises(ValueError, match="step_id"):
        replace(multi_step_binding(), step_id=STEP_TWO.upper())
