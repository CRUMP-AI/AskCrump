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
from backend.connected_app_calendar_cancel_snapshot import (
    ConnectedCalendarCancelSnapshotCoordinator,
    ConnectedCalendarCancelSnapshotError,
    SupabaseConnectedCalendarCancelSnapshotStage,
)
from backend.connected_app_chat_operator import (
    ConnectedOperatorActionContext,
    ConnectedOperatorChatRequest,
)
from backend.connected_app_contracts import (
    CalendarCancelRequest,
    ConnectionAuthorizationState,
    EventSnapshot,
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
from backend.connected_app_scheduler import ConnectedScheduleClaim
from backend.connected_app_service import ConnectedConnectionAuthorityView


NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
OWNER = "85100000-0000-4000-8000-000000000001"
SESSION = "85100000-0000-4000-8000-000000000002"
CHAT = "85100000-0000-4000-8000-000000000003"
MESSAGE = "85100000-0000-4000-8000-000000000004"
TURN = "85100000-0000-4000-8000-000000000005"
TURN_CLAIM = "85100000-0000-4000-8000-000000000006"
CONNECTION = "85100000-0000-4000-8000-000000000007"
SCHEDULE = "85100000-0000-4000-8000-000000000008"
SCHEDULE_TASK = "85100000-0000-4000-8000-000000000009"
TEMPLATE = "85100000-0000-4000-8000-00000000000a"
SCHEDULE_CLAIM = "85100000-0000-4000-8000-00000000000b"
OCCURRENCE = "85100000-0000-4000-8000-00000000000c"
OCCURRENCE_ACTION = "85100000-0000-4000-8000-00000000000d"
OCCURRENCE_APPROVAL = "85100000-0000-4000-8000-00000000000e"
PLAN_PAYLOAD = "85100000-0000-4000-8000-00000000000f"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def event(*, version: str = "etag-1") -> EventSnapshot:
    return EventSnapshot(
        event_id="event-1",
        calendar_id="primary",
        resource_version=version,
        starts_at=NOW + timedelta(days=1),
        ends_at=NOW + timedelta(days=1, hours=1),
        time_zone="UTC",
        title="Untrusted private meeting",
        organizer="owner@example.test",
    )


def cancel_request() -> CalendarCancelRequest:
    return CalendarCancelRequest.build(
        calendar_id="primary",
        event_id="event-1",
        expected_resource_version="etag-1",
    )


def chat_context() -> ConnectedOperatorActionContext:
    return ConnectedOperatorActionContext(
        request=ConnectedOperatorChatRequest(
            owner_id=OWNER,
            session_id=SESSION,
            chat_id=CHAT,
            message_id=MESSAGE,
            message="Cancel my private meeting",
            time_zone="UTC",
        ),
        turn_id=TURN,
        claim_token=TURN_CLAIM,
        origin_session_binding_sha256=SHA_A,
        request_binding_sha256=SHA_B,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def cancel_plan() -> ConnectedOperatorPlan:
    return ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.ACTION,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CANCEL,
        request=cancel_request(),
        requires_approval=True,
    )


def schedule_claim(*, claim_id: str = SCHEDULE_CLAIM) -> ConnectedScheduleClaim:
    actions = (
        ConnectorActionKind.CALENDAR_CANCEL,
        ConnectorActionKind.CALENDAR_GET,
    )
    return ConnectedScheduleClaim(
        schedule_id=SCHEDULE,
        owner_id=OWNER,
        connection_id=CONNECTION,
        task_id=SCHEDULE_TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CANCEL,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_A,
        task_state_revision=3,
        time_zone="UTC",
        cadence_seconds=3600,
        quiet_start_minute=None,
        quiet_end_minute=None,
        requires_approval_every_run=True,
        scheduled_for=NOW - timedelta(minutes=1),
        claim_id=claim_id,
        claimed_at=NOW,
        claim_expires_at=NOW + timedelta(minutes=2),
        turn_id=TURN,
        grant_id=SCHEDULE_CLAIM,
        plan_payload_id=PLAN_PAYLOAD,
        plan_reference_binding_sha256=SHA_B,
        authorization_revision=4,
        authorization_snapshot_sha256=SHA_C,
        granted_actions_sha256=action_set_sha256(actions),
        granted_scopes_sha256=SHA_D,
        template_reference_binding_sha256=SHA_A,
        resource_version_sha256=hashlib.sha256(b"etag-1").hexdigest(),
        occurrence_id=OCCURRENCE,
        occurrence_action_id=OCCURRENCE_ACTION,
        occurrence_approval_id=OCCURRENCE_APPROVAL,
        occurrence_created_at=NOW - timedelta(seconds=10),
    )


class MemoryPayloads:
    def __init__(self) -> None:
        self.references: dict[str, ConnectedPayloadRef] = {}
        self.values: dict[str, object] = {}

    async def seal_json(self, **kwargs):
        encoded = json.dumps(
            kwargs["value"], sort_keys=True, ensure_ascii=True, separators=(",", ":")
        ).encode("ascii")
        commitment = hashlib.sha256(
            kwargs["payload_id"].encode("ascii") + b"\0" + encoded
        ).hexdigest()
        reference = ConnectedPayloadRef(
            payload_id=kwargs["payload_id"],
            owner_id=kwargs["owner_id"],
            connection_id=kwargs["connection_id"],
            action_id=kwargs["action_id"],
            provider=kwargs["provider"],
            action=kwargs["action"],
            commitment_key_id="cancel-snapshot-test-key",
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
    def __init__(self, *, include_get: bool = True) -> None:
        actions = [ConnectorActionKind.CALENDAR_CANCEL]
        if include_get:
            actions.append(ConnectorActionKind.CALENDAR_GET)
        self.calls: list[dict[str, object]] = []
        self.value = ConnectedConnectionAuthorityView(
            connection_id=CONNECTION,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.CALENDAR,
            authorization_state=ConnectionAuthorizationState.ACTIVE,
            authorization_revision=4,
            authorization_snapshot_sha256=SHA_C,
            granted_scopes_sha256=SHA_D,
            granted_actions=tuple(sorted(actions, key=lambda action: action.value)),
            expires_at=NOW + timedelta(hours=1),
        )

    async def get_connection_authority(self, **kwargs):
        self.calls.append(kwargs)
        return self.value


def preparation_view(command) -> ConnectedActionPreparationView:
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
        mutates_external_state=False,
        approval_class=ConnectedActionPolicy.requirement(command.action).approval_class,
        status=ConnectedActionPreparationStatus.READY,
        approval_id=None,
        approval_binding_sha256=None,
        preview_payload_id=None,
        preview_reference_binding_sha256=None,
        preview_sha256=None,
        requested_at=command.requested_at,
        expires_at=command.expires_at,
    )


class Stage:
    def __init__(self) -> None:
        self.chat_calls: list[dict[str, object]] = []
        self.schedule_calls: list[dict[str, object]] = []
        self.records: dict[str, ConnectedActionPreparationView] = {}
        self.chat_authorizations: list[dict[str, object]] = []
        self.schedule_authorizations: list[dict[str, object]] = []

    async def prepare_chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        view = preparation_view(kwargs["command"])
        self.records[view.request_id] = view
        return view

    async def prepare_schedule(self, **kwargs):
        self.schedule_calls.append(kwargs)
        view = preparation_view(kwargs["command"])
        self.records[view.request_id] = view
        return view

    async def authorize_chat(self, **kwargs):
        self.chat_authorizations.append(kwargs)

    async def authorize_schedule(self, **kwargs):
        self.schedule_authorizations.append(kwargs)


class Runtime:
    def __init__(
        self,
        *,
        snapshot: EventSnapshot | None = None,
        observed_at: datetime = NOW,
        resource_version: str = "etag-1",
    ) -> None:
        self.snapshot = snapshot or event()
        self.observed_at = observed_at
        self.resource_version = resource_version
        self.calls: list[dict[str, object]] = []

    async def run(self, invocation, **kwargs):
        self.calls.append({"invocation": invocation, **kwargs})
        terminal = ConnectedReadTerminalRecord(
            operation_id=invocation.intent.action_id,
            provider=invocation.intent.provider,
            resource=invocation.intent.resource,
            action=invocation.intent.action,
            binding_sha256=invocation.binding_sha256,
            authority_sha256=SHA_A,
            idempotency_key_hash=hashlib.sha256(
                invocation.intent.idempotency_key.encode("ascii")
            ).hexdigest(),
            observed_at=self.observed_at,
        )
        observation = ConnectedReadObservation(
            operation_id=invocation.intent.action_id,
            provider=invocation.intent.provider,
            resource=invocation.intent.resource,
            value=self.snapshot,
            observed_at=self.observed_at,
            resource_version=self.resource_version,
        )
        return ConnectedActionRuntimeResult(
            operation_id=invocation.intent.action_id,
            outcome=ConnectedActionOutcome.READ,
            replayed=False,
            terminal=terminal,
            provider_result=observation,
        )


def coordinator(
    *,
    authorities: Authorities | None = None,
    payloads: MemoryPayloads | None = None,
    stage: Stage | None = None,
    runtime: Runtime | None = None,
):
    authorities = authorities or Authorities()
    payloads = payloads or MemoryPayloads()
    stage = stage or Stage()
    runtime = runtime or Runtime()
    return (
        ConnectedCalendarCancelSnapshotCoordinator(
            planning_key=ConnectedPlanBindingKey("cancel-plan-key", b"p" * 32),
            authorities=authorities,
            payload_vault=payloads,
            payloads=ConnectedActionPayloadResolver(
                references=payloads,
                payloads=payloads,
            ),
            stage=stage,
            runtime=runtime,
            now=lambda: NOW,
        ),
        authorities,
        payloads,
        stage,
        runtime,
    )


@pytest.mark.asyncio
async def test_chat_snapshot_crosses_exact_child_read_authority_and_returns_event():
    subject, authorities, payloads, stage, runtime = coordinator()

    result = await subject.read_authoritative_event(
        context=chat_context(),
        plan=cancel_plan(),
    )

    assert result == event()
    assert authorities.calls == [{"owner_id": OWNER, "connection_id": CONNECTION}]
    assert len(payloads.references) == 1
    assert len(stage.chat_calls) == 1
    assert len(stage.chat_authorizations) == 1
    command = stage.chat_calls[0]["command"]
    assert command.action is ConnectorActionKind.CALENDAR_GET
    assert command.owner_id == OWNER
    assert command.session_id == SESSION
    assert command.turn_id == TURN
    assert command.resource_version_sha256 == hashlib.sha256(b"etag-1").hexdigest()
    assert stage.chat_calls[0]["parent_plan_payload_id"]
    assert stage.chat_authorizations[0]["command"] == command
    invocation = runtime.calls[0]["invocation"]
    assert invocation.request.calendar_id == "primary"
    assert invocation.request.event_id == "event-1"
    assert invocation.request.expected_resource_version == "etag-1"
    assert runtime.calls[0]["approval"] is None
    assert runtime.calls[0]["grant"].actions == frozenset(
        {ConnectorActionKind.CALENDAR_GET}
    )


@pytest.mark.asyncio
async def test_schedule_snapshot_is_claim_occurrence_isolated_and_uses_no_chat_authority_read():
    subject, authorities, _, stage, runtime = coordinator()

    result = await subject.read_authoritative_event(
        claim=schedule_claim(),
        request=cancel_request(),
    )

    assert result == event()
    assert authorities.calls == []
    assert not stage.chat_calls
    command = stage.schedule_calls[0]["command"]
    assert command.action is ConnectorActionKind.CALENDAR_GET
    assert command.owner_id == OWNER
    assert command.turn_id == TURN
    assert command.task_state_revision == 3
    assert stage.schedule_calls[0]["claim"].occurrence_id == OCCURRENCE
    assert stage.schedule_authorizations[0]["command"] == command
    assert runtime.calls[0]["invocation"].intent.action_id == command.action_id


@pytest.mark.asyncio
async def test_chat_refuses_missing_child_read_authority_before_payload_or_provider():
    authorities = Authorities(include_get=False)
    subject, _, payloads, stage, runtime = coordinator(authorities=authorities)

    with pytest.raises(ConnectedCalendarCancelSnapshotError) as failure:
        await subject.read_authoritative_event(
            context=chat_context(),
            plan=cancel_plan(),
        )

    assert failure.value.code == "CONNECTED_CANCEL_SNAPSHOT_AUTHORITY_CHANGED"
    assert not payloads.references
    assert not stage.chat_calls
    assert not stage.chat_authorizations
    assert not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "code"),
    (
        (Runtime(snapshot=event(version="etag-2"), resource_version="etag-2"),
         "CONNECTED_CANCEL_SNAPSHOT_AUTHORITY_CHANGED"),
        (Runtime(observed_at=NOW - timedelta(minutes=5, seconds=1)),
         "CONNECTED_CANCEL_SNAPSHOT_STALE"),
        (Runtime(observed_at=NOW + timedelta(seconds=6)),
         "CONNECTED_CANCEL_SNAPSHOT_STALE"),
    ),
)
async def test_snapshot_requires_exact_version_and_short_freshness(runtime, code):
    subject, _, _, _, _ = coordinator(runtime=runtime)
    with pytest.raises(ConnectedCalendarCancelSnapshotError) as failure:
        await subject.read_authoritative_event(
            context=chat_context(),
            plan=cancel_plan(),
        )
    assert failure.value.code == code


@pytest.mark.asyncio
async def test_exact_replay_reuses_child_id_and_new_schedule_claim_gets_new_id():
    subject, _, payloads, stage, runtime = coordinator()
    first_claim = schedule_claim()
    await subject.read_authoritative_event(claim=first_claim, request=cancel_request())
    await subject.read_authoritative_event(claim=first_claim, request=cancel_request())
    first_id = stage.schedule_calls[0]["command"].action_id
    assert stage.schedule_calls[1]["command"].action_id == first_id
    assert len(payloads.references) == 1
    assert len(runtime.calls) == 2

    next_claim = replace(
        first_claim,
        claim_id="85100000-0000-4000-8000-0000000000aa",
        claim_expires_at=NOW + timedelta(minutes=3),
    )
    await subject.read_authoritative_event(claim=next_claim, request=cancel_request())
    assert stage.schedule_calls[2]["command"].action_id != first_id
    assert len(payloads.references) == 2


@pytest.mark.asyncio
async def test_mixed_chat_and_schedule_authority_is_rejected_without_side_effect():
    subject, _, payloads, stage, runtime = coordinator()
    with pytest.raises(ConnectedCalendarCancelSnapshotError) as failure:
        await subject.read_authoritative_event(
            context=chat_context(),
            plan=cancel_plan(),
            claim=schedule_claim(),
            request=cancel_request(),
        )
    assert failure.value.code == "CONNECTED_CANCEL_SNAPSHOT_INVALID"
    assert not payloads.references
    assert not stage.chat_calls
    assert not stage.schedule_calls
    assert not stage.chat_authorizations
    assert not stage.schedule_authorizations
    assert not runtime.calls


@pytest.mark.asyncio
async def test_supabase_stage_recovers_prepare_response_loss_by_exact_readback():
    subject, _, _, captured_stage, _ = coordinator()
    await subject.read_authoritative_event(
        context=chat_context(),
        plan=cancel_plan(),
    )
    command = captured_stage.chat_calls[0]["command"]
    expected = captured_stage.records[command.request_id]

    class Database:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def rpc(self, function, params, **_):
            self.calls.append((function, params))
            if len(self.calls) == 1:
                raise TimeoutError("committed response was lost")
            return {"committed": True}

    class Preparations:
        async def readback_action_preparation(self, **kwargs):
            assert kwargs == {"owner_id": OWNER, "request_id": command.request_id}
            return expected

    database = Database()
    stage = SupabaseConnectedCalendarCancelSnapshotStage(
        database=database,
        preparations=Preparations(),
    )
    result = await stage.prepare_chat(
        context=chat_context(),
        parent_plan_payload_id=captured_stage.chat_calls[0]["parent_plan_payload_id"],
        command=command,
    )

    assert result == expected
    assert [name for name, _ in database.calls] == [
        "connected_app_prepare_cancel_snapshot_chat_v1",
        "connected_app_prepare_cancel_snapshot_chat_v1",
    ]
    assert database.calls[1][1] == database.calls[0][1]
    assert database.calls[0][1]["p_action"] == "calendar.get"
    assert database.calls[0][1]["p_parent_plan_payload_id"] == (
        captured_stage.chat_calls[0]["parent_plan_payload_id"]
    )


@pytest.mark.asyncio
async def test_supabase_stage_rejects_nonmatching_durable_readback_as_unknown():
    subject, _, _, captured_stage, _ = coordinator()
    await subject.read_authoritative_event(
        context=chat_context(),
        plan=cancel_plan(),
    )
    command = captured_stage.chat_calls[0]["command"]

    class Database:
        async def rpc(self, *_args, **_kwargs):
            return {"committed": True}

    class Preparations:
        async def readback_action_preparation(self, **_):
            return None

    stage = SupabaseConnectedCalendarCancelSnapshotStage(
        database=Database(), preparations=Preparations()
    )
    with pytest.raises(ConnectedCalendarCancelSnapshotError) as failure:
        await stage.prepare_chat(
            context=chat_context(),
            parent_plan_payload_id=captured_stage.chat_calls[0][
                "parent_plan_payload_id"
            ],
            command=command,
        )
    assert failure.value.code == "CONNECTED_CANCEL_SNAPSHOT_EFFECT_UNKNOWN"


@pytest.mark.asyncio
async def test_supabase_stage_recovers_authorization_response_loss_before_runtime():
    subject, _, _, captured_stage, _ = coordinator()
    await subject.read_authoritative_event(
        claim=schedule_claim(),
        request=cancel_request(),
    )
    command = captured_stage.schedule_calls[0]["command"]

    class Database:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def rpc(self, function, params, **_):
            self.calls.append((function, params))
            if len(self.calls) == 1:
                raise TimeoutError("authorization committed but response was lost")
            return {
                "request_id": command.request_id,
                "action_id": command.action_id,
                "status": "started",
                "updated_at": NOW.isoformat(),
            }

    class Preparations:
        async def readback_action_preparation(self, **_):
            return captured_stage.records[command.request_id]

    database = Database()
    stage = SupabaseConnectedCalendarCancelSnapshotStage(
        database=database,
        preparations=Preparations(),
    )
    await stage.authorize_schedule(claim=schedule_claim(), command=command)
    assert [name for name, _ in database.calls] == [
        "connected_app_begin_cancel_snapshot_schedule_v1",
        "connected_app_begin_cancel_snapshot_schedule_v1",
    ]
    assert database.calls[0][1] == database.calls[1][1]
    assert database.calls[0][1]["p_occurrence_id"] == OCCURRENCE


def test_snapshot_boundary_repr_redacts_dependencies_and_private_content():
    subject, _, _, _, _ = coordinator()
    stage = SupabaseConnectedCalendarCancelSnapshotStage(
        database=type("D", (), {"rpc": lambda *_args, **_kwargs: None})(),
        preparations=type(
            "P",
            (),
            {"readback_action_preparation": lambda *_args, **_kwargs: None},
        )(),
    )
    assert repr(subject) == (
        "ConnectedCalendarCancelSnapshotCoordinator(secrets='<redacted>')"
    )
    assert repr(stage) == (
        "SupabaseConnectedCalendarCancelSnapshotStage(database='<redacted>')"
    )
    assert "private meeting" not in repr(subject).lower()
