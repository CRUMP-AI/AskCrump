from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.connected_app_agent import (
    ConnectedOperatorDisposition,
    ConnectedOperatorPlan,
    ConnectedOperatorPlanningResult,
    ConnectedOperatorSchedule,
)
from backend.connected_app_chat_completion import (
    ConnectedChatCompletionKey,
    ConnectedChatCompletionKind,
)
from backend.connected_app_chat_operator import (
    ConnectedOperatorChatError,
    ConnectedOperatorChatRequest,
    ConnectedOperatorChatService,
    ConnectedOperatorPreparedAction,
    ConnectedOperatorReadResult,
    ConnectedOperatorScheduleResult,
    ConnectedPreparedActionStatus,
)
from backend.connected_app_chat_turn import (
    ConnectedChatBindingKey,
    ConnectedChatTurnClaim,
    ConnectedChatTurnStage,
    ConnectedChatTurnState,
)
from backend.connected_app_contracts import (
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    MailDraftSpec,
    MailQuery,
    MailSearchRequest,
    MailSendRequest,
)
from backend.connected_app_plan_once import ConnectedPlanBindingKey
from backend.connected_app_multi_step import (
    ConnectedMultiStepLoopRecord,
    ConnectedMultiStepStatus,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_service import ConnectedConnectionView


NOW = datetime(2026, 11, 8, 5, 0, tzinfo=UTC)
OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
CHAT = "00000000-0000-4000-8000-000000000003"
MESSAGE = "00000000-0000-4000-8000-000000000004"
TURN = "00000000-0000-4000-8000-000000000005"
CLAIM = "00000000-0000-4000-8000-000000000006"
CONNECTION = "00000000-0000-4000-8000-000000000007"
REQUEST_ID = "00000000-0000-4000-8000-000000000008"
ACTION_ID = "00000000-0000-4000-8000-000000000009"
APPROVAL_ID = "00000000-0000-4000-8000-00000000000a"
RESULT_ID = "00000000-0000-4000-8000-00000000000b"
SHA = "a" * 64


def request() -> ConnectedOperatorChatRequest:
    return ConnectedOperatorChatRequest(
        owner_id=OWNER,
        session_id=SESSION,
        chat_id=CHAT,
        message_id=MESSAGE,
        message="Check my email for the newest client reply.",
        time_zone="America/New_York",
    )


def connection(*actions: ConnectorActionKind) -> ConnectedConnectionView:
    return ConnectedConnectionView(
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        granted_actions=tuple(sorted(actions, key=lambda item: item.value)),
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA,
        expires_at=NOW + timedelta(days=30),
        updated_at=NOW,
    )


def read_plan() -> ConnectedOperatorPlan:
    return ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEARCH,
        request=MailSearchRequest.build(MailQuery(query="from:client@example.com")),
        requires_approval=False,
    )


def write_plan() -> ConnectedOperatorPlan:
    return ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        request=MailSendRequest.build(
            MailDraftSpec(
                to=("client@example.com",),
                subject="Follow-up",
                body_text="Thanks for the update.",
            )
        ),
        requires_approval=True,
    )


def schedule_plan() -> ConnectedOperatorPlan:
    return ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.SCHEDULE,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEARCH,
        request=MailSearchRequest.build(MailQuery(query="is:unread")),
        schedule=ConnectedOperatorSchedule(
            cadence_seconds=3600,
            time_zone="America/New_York",
            quiet_start=None,
            quiet_end=None,
            requires_approval_every_run=False,
        ),
        requires_approval=False,
    )


class Turns:
    def __init__(self, claims: list[ConnectedChatTurnClaim] | None = None) -> None:
        self.claims = list(claims or [claimed()])
        self.calls = []

    async def claim(self, command):
        self.calls.append(command)
        return self.claims.pop(0)


def claimed() -> ConnectedChatTurnClaim:
    return ConnectedChatTurnClaim(
        ConnectedChatTurnState.CLAIMED,
        TURN,
        ConnectedChatTurnStage.CLAIMED,
        CLAIM,
        None,
        NOW,
    )


class Plans:
    def __init__(self, result: ConnectedOperatorPlanningResult) -> None:
        self.result = result
        self.calls = []

    async def plan_once(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return self.result


class Completions:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    async def complete(self, command):
        self.calls.append(command)
        if self.error:
            raise self.error
        return SimpleNamespace(response_data=command.response_data)


class Connections:
    def __init__(self, values: tuple[ConnectedConnectionView, ...]) -> None:
        self.values = values
        self.calls = []

    async def list_connections(self, **kwargs):
        self.calls.append(kwargs)
        return self.values


class Actions:
    def __init__(self, prepared: ConnectedOperatorPreparedAction) -> None:
        self.prepared = prepared
        self.prepare_calls = []
        self.read_calls = []

    async def prepare(self, **kwargs):
        self.prepare_calls.append(kwargs)
        return self.prepared

    async def execute_read(self, **kwargs):
        self.read_calls.append(kwargs)
        return ConnectedOperatorReadResult(
            action_id=self.prepared.action_id,
            result_reference_id=RESULT_ID,
            summary="I found one recent client reply.",
            item_count=1,
        )


class Delegated:
    def __init__(self) -> None:
        self.calls = []

    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        return "Email is a way to exchange digital messages."


class Schedules:
    def __init__(self) -> None:
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return ConnectedOperatorScheduleResult(
            schedule_id=RESULT_ID,
            next_run_at=NOW + timedelta(hours=1),
        )


def service(
    *,
    planning: ConnectedOperatorPlanningResult,
    connection_values: tuple[ConnectedConnectionView, ...] | None = None,
    turns: Turns | None = None,
    completions: Completions | None = None,
    actions: Actions | None = None,
    schedules: Schedules | None = None,
    multi_step=None,
    multi_step_enabled: bool = False,
):
    turn_store = turns or Turns()
    plan_store = Plans(planning)
    completion_store = completions or Completions()
    connection_store = Connections(
        connection_values
        if connection_values is not None
        else (connection(ConnectorActionKind.MAIL_SEARCH, ConnectorActionKind.MAIL_SEND),)
    )
    action_store = actions or Actions(
        ConnectedOperatorPreparedAction(
            request_id=REQUEST_ID,
            action_id=ACTION_ID,
            status=ConnectedPreparedActionStatus.READY,
        )
    )
    delegated = Delegated()
    value = ConnectedOperatorChatService(
        binding_key=ConnectedChatBindingKey("chat-v1", b"c" * 32),
        planning_key=ConnectedPlanBindingKey("plan-v1", b"p" * 32),
        completion_key=ConnectedChatCompletionKey("completion-v1", b"r" * 32),
        turns=turn_store,
        plans=plan_store,
        completions=completion_store,
        connections=connection_store,
        actions=action_store,
        delegated=delegated,
        schedules=schedules,
        multi_step=multi_step,
        multi_step_enabled=multi_step_enabled,
        composition_manifest_sha256="f" * 64,
        now=lambda: NOW,
    )
    return (
        value,
        turn_store,
        plan_store,
        completion_store,
        connection_store,
        action_store,
        delegated,
    )


@pytest.mark.asyncio
async def test_clarification_is_atomically_completed_after_one_plan() -> None:
    value, _, plans, completions, _, actions, delegated = service(
        planning=ConnectedOperatorPlanningResult(
            ConnectedOperatorDisposition.CLARIFY,
            question="Which client should I search for?",
        )
    )
    response = await value.handle(request())
    assert response.status_code == 200
    assert response.content["response"] == "Which client should I search for?"
    assert len(plans.calls) == 1
    assert completions.calls[0].kind is ConnectedChatCompletionKind.CLARIFICATION
    assert actions.prepare_calls == []
    assert delegated.calls == []


@pytest.mark.asyncio
async def test_read_prepares_and_executes_exactly_once_then_completes() -> None:
    prepared = ConnectedOperatorPreparedAction(
        request_id=REQUEST_ID,
        action_id=ACTION_ID,
        status=ConnectedPreparedActionStatus.READY,
    )
    actions = Actions(prepared)
    value, _, plans, completions, _, _, _ = service(
        planning=ConnectedOperatorPlanningResult(
            ConnectedOperatorDisposition.ACTION, plan=read_plan()
        ),
        actions=actions,
    )
    response = await value.handle(request())
    assert response.content["connectedOperator"]["state"] == "completed"
    assert len(plans.calls) == len(actions.prepare_calls) == len(actions.read_calls) == 1
    assert completions.calls[0].kind is ConnectedChatCompletionKind.ACTION_TERMINAL


@pytest.mark.asyncio
async def test_write_stops_at_pending_approval_and_never_executes_provider() -> None:
    prepared = ConnectedOperatorPreparedAction(
        request_id=REQUEST_ID,
        action_id=ACTION_ID,
        status=ConnectedPreparedActionStatus.PENDING_APPROVAL,
        approval_id=APPROVAL_ID,
    )
    actions = Actions(prepared)
    value, _, _, completions, _, _, _ = service(
        planning=ConnectedOperatorPlanningResult(
            ConnectedOperatorDisposition.ACTION, plan=write_plan()
        ),
        actions=actions,
    )
    response = await value.handle(request())
    assert response.content["connectedOperator"]["state"] == "pending_approval"
    assert len(actions.prepare_calls) == 1
    assert actions.read_calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.PENDING_APPROVAL


@pytest.mark.asyncio
async def test_no_connection_answers_truthfully_without_model_or_provider() -> None:
    value, _, plans, completions, _, actions, delegated = service(
        planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE),
        connection_values=(),
    )
    response = await value.handle(request())
    assert response.content["connectedOperator"]["state"] == "needs_connection"
    assert plans.calls == []
    assert actions.prepare_calls == []
    assert delegated.calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.DELEGATED


@pytest.mark.asyncio
async def test_expired_connection_is_not_sent_to_model() -> None:
    expired = replace(
        connection(ConnectorActionKind.MAIL_SEARCH),
        expires_at=NOW - timedelta(seconds=1),
    )
    value, _, plans, completions, _, actions, _ = service(
        planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE),
        connection_values=(expired,),
    )
    response = await value.handle(request())
    assert response.content["connectedOperator"]["state"] == "needs_connection"
    assert plans.calls == actions.prepare_calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.DELEGATED


@pytest.mark.asyncio
async def test_none_delegates_without_claiming_a_second_chat_job() -> None:
    value, turns, plans, completions, _, actions, delegated = service(
        planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE)
    )
    response = await value.handle(request())
    assert response.content["connectedOperator"]["state"] == "delegated"
    assert len(turns.calls) == len(plans.calls) == len(delegated.calls) == 1
    assert actions.prepare_calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.DELEGATED


@pytest.mark.asyncio
async def test_schedule_fails_truthfully_to_clarification_without_template_custody() -> None:
    value, _, _, completions, _, actions, _ = service(
        planning=ConnectedOperatorPlanningResult(
            ConnectedOperatorDisposition.SCHEDULE, plan=schedule_plan()
        )
    )
    response = await value.handle(request())
    assert response.content["connectedOperator"]["state"] == "schedule_unavailable"
    assert actions.prepare_calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.CLARIFICATION


@pytest.mark.asyncio
async def test_schedule_uses_only_injected_durable_template_boundary() -> None:
    schedules = Schedules()
    value, _, _, completions, _, actions, _ = service(
        planning=ConnectedOperatorPlanningResult(
            ConnectedOperatorDisposition.SCHEDULE, plan=schedule_plan()
        ),
        schedules=schedules,
    )
    response = await value.handle(request())
    assert response.content["connectedOperator"]["state"] == "schedule_created"
    assert len(schedules.calls) == 1
    assert actions.prepare_calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.SCHEDULE_CREATED


@pytest.mark.asyncio
async def test_explicit_recurrence_still_creates_one_schedule_with_multi_step_enabled() -> None:
    class MultiStep:
        def __init__(self) -> None:
            self.calls = []

        async def start_from_chat(self, **kwargs):
            self.calls.append(kwargs)
            raise AssertionError("explicit recurrence must not enter the continuation loop")

    schedules = Schedules()
    multi_step = MultiStep()
    value, _, plans, completions, _, actions, _ = service(
        planning=ConnectedOperatorPlanningResult(
            ConnectedOperatorDisposition.SCHEDULE, plan=schedule_plan()
        ),
        schedules=schedules,
        multi_step=multi_step,
        multi_step_enabled=True,
    )
    recurring_request = replace(
        request(), message="Every 24 hours check my inbox for new client replies."
    )
    response = await value.handle(recurring_request)
    assert response.content["connectedOperator"]["state"] == "schedule_created"
    assert len(plans.calls) == 1
    assert len(schedules.calls) == 1
    assert multi_step.calls == []
    assert actions.prepare_calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.SCHEDULE_CREATED


@pytest.mark.asyncio
async def test_zero_step_multi_step_completion_delegates_without_false_action_claim() -> None:
    class MultiStep:
        def __init__(self) -> None:
            self.calls = []

        async def start_from_chat(self, **kwargs):
            self.calls.append(kwargs)
            return ConnectedMultiStepLoopRecord(
                loop_id="00000000-0000-4000-8000-00000000000c",
                owner_id=OWNER,
                session_id=SESSION,
                session_binding_sha256="b" * 64,
                chat_id=CHAT,
                message_id=MESSAGE,
                turn_id=TURN,
                turn_claim_token=CLAIM,
                time_zone="America/New_York",
                request_binding_sha256="c" * 64,
                status=ConnectedMultiStepStatus.COMPLETED,
                current_step=0,
                max_steps=8,
                task_state_revision=2,
                pending_approval_id=None,
                last_result_reference_id=None,
                last_result_binding_sha256=None,
                expires_at=NOW + timedelta(minutes=30),
                updated_at=NOW,
            )

    multi_step = MultiStep()
    value, _, _, completions, _, actions, delegated = service(
        planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE),
        multi_step=multi_step,
        multi_step_enabled=True,
    )
    ordinary_candidate = replace(
        request(), message="Check whether calendar is a Python data structure."
    )
    response = await value.handle(ordinary_candidate)
    assert response.content["response"] == "Email is a way to exchange digital messages."
    assert response.content["connectedOperator"] == {
        "version": 1,
        "state": "delegated",
    }
    assert len(multi_step.calls) == 1
    assert len(delegated.calls) == 1
    assert actions.prepare_calls == []
    assert completions.calls[0].kind is ConnectedChatCompletionKind.DELEGATED


@pytest.mark.asyncio
async def test_completed_replay_returns_cache_without_planner_or_provider() -> None:
    cached = {
        "response": "Cached result.",
        "assistantMessage": {"id": ACTION_ID, "inReplyTo": MESSAGE},
    }
    replay = ConnectedChatTurnClaim(
        ConnectedChatTurnState.COMPLETED,
        TURN,
        ConnectedChatTurnStage.TERMINAL,
        None,
        cached,
        NOW,
    )
    value, _, plans, completions, connections, actions, delegated = service(
        planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE),
        turns=Turns([replay]),
    )
    response = await value.handle(request())
    assert response.content == {"success": True, **cached, "cached": True}
    assert plans.calls == completions.calls == connections.calls == []
    assert actions.prepare_calls == delegated.calls == []


@pytest.mark.asyncio
async def test_busy_returns_conflict_without_planner_or_provider() -> None:
    busy = ConnectedChatTurnClaim(
        ConnectedChatTurnState.BUSY,
        TURN,
        ConnectedChatTurnStage.PLANNING,
        None,
        None,
        NOW,
    )
    value, _, plans, completions, connections, actions, _ = service(
        planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE),
        turns=Turns([busy]),
    )
    response = await value.handle(request())
    assert response.status_code == 409
    assert response.content["code"] == "CONNECTED_OPERATOR_CHAT_BUSY"
    assert plans.calls == completions.calls == connections.calls == []
    assert actions.prepare_calls == []


@pytest.mark.asyncio
async def test_attachment_request_fails_truthfully_before_claim_or_model() -> None:
    value, turns, plans, completions, connections, actions, delegated = service(
        planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE)
    )
    attached = replace(
        request(),
        attachment_ids=("00000000-0000-4000-8000-00000000000c",),
    )
    with pytest.raises(ConnectedOperatorChatError) as raised:
        await value.handle(attached)
    assert raised.value.code == "CONNECTED_OPERATOR_ATTACHMENT_UNSUPPORTED"
    assert raised.value.status_code == 400
    assert turns.calls == plans.calls == completions.calls == connections.calls == []
    assert actions.prepare_calls == delegated.calls == []


@pytest.mark.asyncio
async def test_ambiguous_completion_fails_closed_without_duplicate_write() -> None:
    completions = Completions(error=RuntimeError("response lost"))
    value, _, plans, _, _, actions, _ = service(
        planning=ConnectedOperatorPlanningResult(
            ConnectedOperatorDisposition.ACTION, plan=read_plan()
        ),
        completions=completions,
    )
    with pytest.raises(ConnectedOperatorChatError) as raised:
        await value.handle(request())
    assert raised.value.code == "CONNECTED_OPERATOR_CHAT_EFFECT_UNKNOWN"
    assert len(plans.calls) == len(actions.prepare_calls) == len(actions.read_calls) == 1
    assert len(completions.calls) == 1


def test_request_and_service_reprs_do_not_expose_content_or_keys() -> None:
    value, *_ = service(planning=ConnectedOperatorPlanningResult(ConnectedOperatorDisposition.NONE))
    assert request().message not in repr(request())
    assert "636363" not in repr(value)
