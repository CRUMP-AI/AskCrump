from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.connected_app_contracts import (
    ConnectorAccountKind,
    MailDraftSpec,
    MailSendRequest,
)
from backend.connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_service import (
    ApprovalDecisionCommand,
    ConnectedApprovalDecision,
    ConnectedApprovalReviewPreview,
    ConnectedMailReviewPayload,
    ConnectedScheduleStatus,
    DisconnectCommand,
    OAuthCallbackCommand,
    OAuthStartCommand,
    ScheduleCreateCommand,
    ScheduleTransitionCommand,
    approval_execution_parameters_sha256,
    approval_review_preview_sha256,
)
from backend.connected_app_supabase_control_plane import (
    ConnectedControlPlaneError,
    SupabaseConnectedAppControlPlane,
    require_control_plane_protocol,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000010"
SESSION_HASH = "1" * 64
REQUEST = "00000000-0000-4000-8000-000000000002"
CONNECTION = "00000000-0000-4000-8000-000000000003"
WORK_CONNECTION = "00000000-0000-4000-8000-000000000013"
TASK = "00000000-0000-4000-8000-000000000004"
TURN = "00000000-0000-4000-8000-000000000005"
SCHEDULE = "00000000-0000-4000-8000-000000000006"
TEMPLATE = "00000000-0000-4000-8000-000000000007"
ACTION = "00000000-0000-4000-8000-000000000008"
APPROVAL = "00000000-0000-4000-8000-000000000009"
DECISION = "00000000-0000-4000-8000-00000000000a"
PAYLOAD_REF = "00000000-0000-4000-8000-00000000000b"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _connection(*, state: str = "active") -> dict[str, object]:
    return {
        "connection_id": CONNECTION,
        "provider": "google",
        "resource": "mail",
        "account_kind": "personal",
        "granted_actions": ["mail.get", "mail.send"],
        "authorization_state": state,
        "authorization_revision": 2,
        "authorization_snapshot_sha256": SHA_A if state == "active" else None,
        "authorization_expires_at": (
            (NOW + timedelta(hours=1)).isoformat() if state == "active" else None
        ),
        "updated_at": NOW.isoformat(),
    }


def _authority() -> dict[str, object]:
    return {
        "connection_id": CONNECTION,
        "provider": "google",
        "resource": "mail",
        "authorization_state": "active",
        "authorization_revision": 2,
        "authorization_snapshot_sha256": SHA_A,
        "granted_scopes_sha256": SHA_B,
        "granted_actions": ["mail.get", "mail.send"],
        "authorization_expires_at": (NOW + timedelta(hours=1)).isoformat(),
    }


def _schedule(*, status: str = "active", revision: int = 1) -> dict[str, object]:
    return {
        "schedule_id": SCHEDULE,
        "connection_id": CONNECTION,
        "task_id": TASK,
        "provider": "google",
        "resource": "calendar",
        "action": "calendar.create",
        "action_template_ref": TEMPLATE,
        "parameters_sha256": SHA_C,
        "task_state_revision": revision,
        "time_zone": "America/New_York",
        "cadence_seconds": 3600,
        "quiet_start_minute": 1320,
        "quiet_end_minute": 420,
        "requires_approval_every_run": True,
        "status": status,
        "next_run_at": ((NOW + timedelta(hours=1)).isoformat() if status == "active" else None),
        "updated_at": NOW.isoformat(),
    }


def _request() -> MailSendRequest:
    return MailSendRequest.build(
        MailDraftSpec(
            to=("recipient@example.com",),
            cc=(),
            bcc=(),
            subject="Reviewed subject",
            body_text="Reviewed body",
        )
    )


def _payload() -> ConnectedMailReviewPayload:
    return ConnectedMailReviewPayload(
        account=CONNECTION,
        to=("recipient@example.com",),
        cc=(),
        bcc=(),
        subject="Reviewed subject",
        body_text="Reviewed body",
        reply_context=None,
    )


def _preview() -> ConnectedApprovalReviewPreview:
    parameters = approval_execution_parameters_sha256(
        action=ConnectorActionKind.MAIL_SEND,
        provider_request=_request(),
        payload_commitment_sha256=SHA_B,
    )
    preview = approval_review_preview_sha256(
        approval_id=APPROVAL,
        action_id=ACTION,
        action=ConnectorActionKind.MAIL_SEND,
        approval_binding_sha256=SHA_A,
        parameters_sha256=parameters,
        resource_version_sha256=None,
        payload=_payload(),
        preview_commitment_sha256=SHA_C,
    )
    return ConnectedApprovalReviewPreview(
        approval_binding_sha256=SHA_A,
        parameters_sha256=parameters,
        preview_sha256=preview,
        payload=_payload(),
        connection_id=CONNECTION,
        action=ConnectorActionKind.MAIL_SEND,
        resource_version_sha256=None,
        provider_request=_request(),
    )


def _action() -> dict[str, object]:
    preview = _preview()
    return {
        "action_id": ACTION,
        "connection_id": CONNECTION,
        "task_id": TASK,
        "turn_id": TURN,
        "provider": "google",
        "resource": "mail",
        "action": "mail.send",
        "authorization_revision": 2,
        "authorization_snapshot_sha256": SHA_A,
        "granted_scopes_sha256": SHA_B,
        "policy_version": ConnectedActionPolicy.version,
        "action_revision": 1,
        "status": "pending_approval",
        "parameters_sha256": preview.parameters_sha256,
        "resource_version_sha256": None,
        "preview_sha256": preview.preview_sha256,
        "updated_at": NOW.isoformat(),
    }


def _approval(*, status: str = "pending") -> dict[str, object]:
    preview = _preview()
    decided = status in {"approved", "denied"}
    return {
        "approval_id": APPROVAL,
        "action_id": ACTION,
        "connection_id": CONNECTION,
        "task_id": TASK,
        "turn_id": TURN,
        "provider": "google",
        "resource": "mail",
        "action": "mail.send",
        "authorization_revision": 2,
        "authorization_snapshot_sha256": SHA_A,
        "granted_scopes_sha256": SHA_B,
        "policy_version": ConnectedActionPolicy.version,
        "action_revision": 1,
        "status": status,
        "approval_binding_sha256": SHA_A,
        "parameters_sha256": preview.parameters_sha256,
        "resource_version_sha256": None,
        "preview_sha256": preview.preview_sha256,
        "review_payload_ref": PAYLOAD_REF,
        "decision_id": DECISION if decided else None,
        "decision_session_binding_sha256": SESSION_HASH if decided else None,
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "decided_at": NOW.isoformat() if decided else None,
    }


class FakeDB:
    def __init__(self) -> None:
        self.responses: dict[str, object] = {}
        self.calls: list[tuple[str, dict[str, object], bool]] = []
        self.failure: Exception | None = None

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        if self.failure:
            raise self.failure
        return self.responses.get(name)


class FakeOAuth:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.value = object()

    async def start_once(self, command):
        self.calls.append(("start", command))
        return self.value

    async def read_start(self, **kwargs):
        self.calls.append(("read-start", kwargs))
        return self.value

    async def complete_once(self, command):
        self.calls.append(("complete", command))
        return self.value

    async def deny_once(self, **kwargs):
        self.calls.append(("deny", kwargs))

    async def read_completion(self, **kwargs):
        self.calls.append(("read-completion", kwargs))
        return self.value


class FakePreviews:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def resolve(self, **kwargs):
        self.calls.append(kwargs)
        return _preview()


def _control() -> tuple[SupabaseConnectedAppControlPlane, FakeDB, FakeOAuth, FakePreviews]:
    database = FakeDB()
    oauth = FakeOAuth()
    previews = FakePreviews()
    control = SupabaseConnectedAppControlPlane(
        database=database,
        oauth=oauth,
        previews=previews,
        now=lambda: NOW,
        new_uuid=lambda: SCHEDULE,
    )
    require_control_plane_protocol(control)
    return control, database, oauth, previews


@pytest.mark.asyncio
async def test_owner_read_surface_uses_only_exact_bounded_rpcs() -> None:
    control, database, _, previews = _control()
    database.responses.update(
        {
            "connected_app_operator_list_connections_v1": [_connection()],
            "connected_app_operator_get_connection_authority_v1": _authority(),
            "connected_app_operator_list_schedules_v1": [_schedule()],
            "connected_app_operator_get_schedule_v1": _schedule(),
            "connected_app_operator_list_actions_v1": [_action()],
            "connected_app_operator_get_action_v1": _action(),
            "connected_app_operator_list_approvals_v1": [_approval()],
            "connected_app_operator_get_approval_v1": _approval(),
        }
    )
    assert (await control.list_connections(owner_id=OWNER))[0].connection_id == CONNECTION
    assert (
        await control.get_connection_authority(owner_id=OWNER, connection_id=CONNECTION)
    ).authorization_revision == 2
    assert (await control.list_schedules(owner_id=OWNER))[0].schedule_id == SCHEDULE
    assert (
        await control.get_schedule(owner_id=OWNER, schedule_id=SCHEDULE)
    ).schedule_id == SCHEDULE
    assert (await control.list_actions(owner_id=OWNER))[0].action_id == ACTION
    assert (await control.get_action(owner_id=OWNER, action_id=ACTION)).action_id == ACTION
    assert (await control.list_approvals(owner_id=OWNER))[0].approval_id == APPROVAL
    assert (
        await control.get_approval(owner_id=OWNER, approval_id=APPROVAL)
    ).approval_id == APPROVAL
    assert all(retry is True for _, _, retry in database.calls)
    assert len(previews.calls) == 2
    assert all(call["owner_id"] == OWNER for call in previews.calls)
    assert all(call["connection_id"] == CONNECTION for call in previews.calls)
    assert all(call["action_id"] == ACTION for call in previews.calls)
    assert all(call["provider"] is ConnectorProvider.GOOGLE for call in previews.calls)
    assert all(call["action"] is ConnectorActionKind.MAIL_SEND for call in previews.calls)
    assert all(call["review_payload_ref"] == PAYLOAD_REF for call in previews.calls)


@pytest.mark.asyncio
async def test_write_surface_uses_no_transport_retry_and_exact_readback_domains() -> None:
    control, database, _, _ = _control()
    database.responses.update(
        {
            "connected_app_operator_disconnect_v1": _connection(state="revoked"),
            "connected_app_operator_read_disconnect_v1": _connection(state="revoked"),
            "connected_app_operator_create_schedule_v1": _schedule(),
            "connected_app_operator_read_schedule_create_v1": _schedule(),
            "connected_app_operator_transition_schedule_v1": _schedule(status="paused", revision=2),
            "connected_app_operator_read_schedule_transition_v1": _schedule(
                status="paused", revision=2
            ),
        }
    )
    disconnect = DisconnectCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        connection_id=CONNECTION,
        requested_at=NOW,
    )
    assert (
        await control.disconnect_once(disconnect)
    ).connection.authorization_state.value == "revoked"
    assert (
        await control.readback_disconnect(
            owner_id=OWNER, connection_id=CONNECTION, request_id=REQUEST
        )
    ).connection.connection_id == CONNECTION
    create = ScheduleCreateCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        connection_id=CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_C,
        time_zone="America/New_York",
        cadence_seconds=3600,
        quiet_start_minute=1320,
        quiet_end_minute=420,
        requires_approval_every_run=True,
        requested_at=NOW,
    )
    assert (await control.create_schedule_once(create)).schedule_id == SCHEDULE
    assert (
        await control.readback_schedule_create(owner_id=OWNER, request_id=REQUEST)
    ).schedule_id == SCHEDULE
    transition = ScheduleTransitionCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        schedule_id=SCHEDULE,
        expected_task_state_revision=1,
        expected_status=ConnectedScheduleStatus.ACTIVE,
        target=ConnectedScheduleStatus.PAUSED,
        requested_at=NOW,
    )
    assert (await control.transition_schedule_once(transition)).status.value == "paused"
    assert (
        await control.readback_schedule_transition(
            owner_id=OWNER, schedule_id=SCHEDULE, request_id=REQUEST
        )
    ).task_state_revision == 2
    write_rpcs = {
        "connected_app_operator_disconnect_v1",
        "connected_app_operator_create_schedule_v1",
        "connected_app_operator_transition_schedule_v1",
    }
    assert all(not retry for name, _, retry in database.calls if name in write_rpcs)
    for name, payload, _ in database.calls:
        if name in write_rpcs:
            assert len(payload["p_command_binding_sha256"]) == 64


@pytest.mark.asyncio
async def test_microsoft_account_kinds_list_distinctly_and_schedule_selected_connection() -> None:
    control, database, _, _ = _control()
    personal = {
        **_connection(),
        "provider": "microsoft",
        "account_kind": "personal",
    }
    work = {
        **_connection(),
        "connection_id": WORK_CONNECTION,
        "provider": "microsoft",
        "account_kind": "work_school",
    }
    work_schedule = {
        **_schedule(),
        "connection_id": WORK_CONNECTION,
        "provider": "microsoft",
    }
    database.responses["connected_app_operator_list_connections_v1"] = [personal, work]
    database.responses["connected_app_operator_create_schedule_v1"] = work_schedule

    connections = await control.list_connections(owner_id=OWNER)
    assert [(item.connection_id, item.account_kind.value) for item in connections] == [
        (CONNECTION, "personal"),
        (WORK_CONNECTION, "work_school"),
    ]
    command = ScheduleCreateCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        connection_id=WORK_CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.MICROSOFT,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_C,
        time_zone="America/New_York",
        cadence_seconds=3600,
        quiet_start_minute=1320,
        quiet_end_minute=420,
        requires_approval_every_run=True,
        requested_at=NOW,
    )
    assert (await control.create_schedule_once(command)).connection_id == WORK_CONNECTION
    schedule_call = next(
        call for call in database.calls if call[0] == "connected_app_operator_create_schedule_v1"
    )
    assert schedule_call[1]["p_connection_id"] == WORK_CONNECTION
    assert schedule_call[1]["p_provider"] == "microsoft"
    assert schedule_call[2] is False


@pytest.mark.asyncio
async def test_approval_decision_and_readback_bind_preview_reference() -> None:
    control, database, _, previews = _control()
    database.responses["connected_app_operator_decide_approval_v1"] = _approval(status="approved")
    database.responses["connected_app_operator_read_approval_decision_v1"] = _approval(
        status="approved"
    )
    preview = _preview()
    command = ApprovalDecisionCommand(
        decision_id=DECISION,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        approval_id=APPROVAL,
        action_id=ACTION,
        connection_id=CONNECTION,
        task_id=TASK,
        turn_id=TURN,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        authorization_revision=2,
        authorization_snapshot_sha256=SHA_A,
        granted_scopes_sha256=SHA_B,
        policy_version=ConnectedActionPolicy.version,
        action_revision=1,
        approval_binding_sha256=SHA_A,
        parameters_sha256=preview.parameters_sha256,
        resource_version_sha256=None,
        preview_sha256=preview.preview_sha256,
        decision=ConnectedApprovalDecision.APPROVED,
        decided_at=NOW,
    )
    assert (await control.decide_approval_once(command)).status.value == "approved"
    assert (
        await control.readback_approval_decision(
            owner_id=OWNER, approval_id=APPROVAL, decision_id=DECISION
        )
    ).decision_id == DECISION
    assert database.calls[0][2] is False
    assert database.calls[1][2] is True
    assert len(previews.calls) == 2


@pytest.mark.asyncio
async def test_oauth_is_explicitly_delegated_to_secret_safe_coordinator() -> None:
    control, _, oauth, _ = _control()
    command = OAuthStartCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        actions=frozenset({ConnectorActionKind.MAIL_GET}),
        redirect_uri="https://www.askcrump.com/api/connected-apps/oauth/callback/google",
        connection_id=None,
        requested_at=NOW,
    )
    assert await control.start_oauth_once(command) is oauth.value
    assert await control.readback_oauth_start(owner_id=OWNER, request_id=REQUEST) is oauth.value
    callback = OAuthCallbackCommand.build(
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        code="authorization-code-value",
        received_at=NOW,
    )
    assert await control.complete_oauth_callback(callback) is oauth.value
    await control.deny_oauth_callback(
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        state_sha256="d" * 64,
        received_at=NOW,
    )
    assert (
        await control.readback_oauth_callback(
            provider=ConnectorProvider.GOOGLE,
            callback_binding_sha256=callback.callback_binding_sha256,
        )
        is oauth.value
    )
    assert [name for name, _ in oauth.calls] == [
        "start",
        "read-start",
        "complete",
        "deny",
        "read-completion",
    ]


@pytest.mark.asyncio
async def test_malformed_or_failed_rpc_is_content_free_and_fails_closed() -> None:
    control, database, _, _ = _control()
    database.responses["connected_app_operator_list_connections_v1"] = [
        {**_connection(), "unexpected": "secret"}
    ]
    with pytest.raises(ConnectedControlPlaneError) as malformed:
        await control.list_connections(owner_id=OWNER)
    assert malformed.value.code == "CONNECTED_RPC_SHAPE_INVALID"

    database.failure = RuntimeError("database body with customer content")
    with pytest.raises(ConnectedControlPlaneError) as failed:
        await control.get_action(owner_id=OWNER, action_id=ACTION)
    assert str(failed.value) == "CONNECTED_RPC_FAILED"
    assert "customer" not in repr(failed.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "method_name", "rows"),
    (
        (
            "connected_app_operator_list_connections_v1",
            "list_connections",
            [_connection(), _connection()],
        ),
        (
            "connected_app_operator_list_actions_v1",
            "list_actions",
            [_action(), _action()],
        ),
        (
            "connected_app_operator_list_approvals_v1",
            "list_approvals",
            [_approval(), _approval()],
        ),
    ),
)
async def test_duplicate_public_identities_fail_closed(
    function_name: str, method_name: str, rows: list[dict[str, object]]
) -> None:
    control, database, _, _ = _control()
    database.responses[function_name] = rows
    with pytest.raises(ConnectedControlPlaneError) as failed:
        await getattr(control, method_name)(owner_id=OWNER)
    assert failed.value.code == "CONNECTED_RPC_SHAPE_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "method", "record"),
    (
        (
            "connected_app_operator_list_connections_v1",
            "list_connections",
            {**_connection(), "authorization_revision": True},
        ),
        (
            "connected_app_operator_list_schedules_v1",
            "list_schedules",
            {**_schedule(), "cadence_seconds": 0},
        ),
        (
            "connected_app_operator_list_actions_v1",
            "list_actions",
            {**_action(), "authorization_snapshot_sha256": "not-a-hash"},
        ),
    ),
)
async def test_semantically_invalid_exact_shape_is_quarantined(
    function_name: str, method: str, record: dict[str, object]
) -> None:
    control, database, _, _ = _control()
    database.responses[function_name] = [record]
    with pytest.raises(ConnectedControlPlaneError) as failed:
        await getattr(control, method)(owner_id=OWNER)
    assert failed.value.code == "CONNECTED_RPC_SHAPE_INVALID"


@pytest.mark.asyncio
async def test_missing_scalar_readbacks_are_exact_none() -> None:
    control, database, _, _ = _control()
    for name in (
        "connected_app_operator_get_connection_authority_v1",
        "connected_app_operator_get_schedule_v1",
        "connected_app_operator_get_action_v1",
        "connected_app_operator_get_approval_v1",
        "connected_app_operator_read_disconnect_v1",
        "connected_app_operator_read_schedule_create_v1",
        "connected_app_operator_read_schedule_transition_v1",
        "connected_app_operator_read_approval_decision_v1",
    ):
        database.responses[name] = None
    assert await control.get_connection_authority(owner_id=OWNER, connection_id=CONNECTION) is None
    assert await control.get_schedule(owner_id=OWNER, schedule_id=SCHEDULE) is None
    assert await control.get_action(owner_id=OWNER, action_id=ACTION) is None
    assert await control.get_approval(owner_id=OWNER, approval_id=APPROVAL) is None
    assert (
        await control.readback_disconnect(
            owner_id=OWNER, connection_id=CONNECTION, request_id=REQUEST
        )
        is None
    )
    assert await control.readback_schedule_create(owner_id=OWNER, request_id=REQUEST) is None
    assert (
        await control.readback_schedule_transition(
            owner_id=OWNER, schedule_id=SCHEDULE, request_id=REQUEST
        )
        is None
    )
    assert (
        await control.readback_approval_decision(
            owner_id=OWNER, approval_id=APPROVAL, decision_id=DECISION
        )
        is None
    )
    assert all(retry is True for _, _, retry in database.calls)


@pytest.mark.asyncio
async def test_schedule_next_run_is_stable_from_command_time() -> None:
    control, database, _, _ = _control()
    database.responses["connected_app_operator_create_schedule_v1"] = _schedule()
    command = ScheduleCreateCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256=SESSION_HASH,
        connection_id=CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_C,
        time_zone="America/New_York",
        cadence_seconds=3600,
        quiet_start_minute=1320,
        quiet_end_minute=420,
        requires_approval_every_run=True,
        requested_at=NOW,
    )
    await control.create_schedule_once(command)
    _, payload, retry = database.calls[-1]
    assert retry is False
    assert payload["p_next_run_at"] == (NOW + timedelta(hours=1)).isoformat()


@pytest.mark.asyncio
async def test_preview_resolver_failure_is_content_free_and_not_partially_returned() -> None:
    control, database, _, previews = _control()
    database.responses["connected_app_operator_list_approvals_v1"] = [_approval()]

    async def fail(**_kwargs):
        raise RuntimeError("decrypted recipient and subject")

    previews.resolve = fail
    with pytest.raises(ConnectedControlPlaneError) as failed:
        await control.list_approvals(owner_id=OWNER)
    assert failed.value.code == "CONNECTED_PREVIEW_FAILED"
    assert "recipient" not in repr(failed.value)


def test_constructor_rejects_incomplete_production_boundaries() -> None:
    _, database, oauth, previews = _control()
    with pytest.raises(TypeError):
        SupabaseConnectedAppControlPlane(database=object(), oauth=oauth, previews=previews)
    with pytest.raises(TypeError):
        SupabaseConnectedAppControlPlane(database=database, oauth=object(), previews=previews)
    with pytest.raises(TypeError):
        SupabaseConnectedAppControlPlane(database=database, oauth=oauth, previews=object())


def test_control_plane_error_never_accepts_dependency_text_as_a_public_code() -> None:
    error = ConnectedControlPlaneError("decrypted recipient and subject")
    assert error.code == "CONNECTED_RPC_FAILED"
    assert "recipient" not in repr(error)
