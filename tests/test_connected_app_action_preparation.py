from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.connected_app_action_preparation import (
    ConnectedActionPreparationCommand,
    ConnectedActionPreparationError,
    ConnectedActionPreparationService,
    ConnectedActionPreparationStatus,
    ConnectedActionPreparationView,
    action_preparation_result_matches,
)
from backend.connected_app_payload_vault import ConnectedPayloadRef
from backend.connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorApprovalClass,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from backend.connected_app_supabase_control_plane import (
    ConnectedControlPlaneError,
    SupabaseConnectedAppControlPlane,
    require_action_preparation_protocol,
)


NOW = datetime(2026, 11, 7, 21, 0, tzinfo=UTC)
EXPIRES = NOW + timedelta(minutes=10)
OWNER = "00000000-0000-4000-8000-000000000001"
SESSION_ID = "00000000-0000-4000-8000-00000000000b"
REQUEST = "00000000-0000-4000-8000-000000000002"
CONNECTION = "00000000-0000-4000-8000-000000000003"
WORK_CONNECTION = "00000000-0000-4000-8000-000000000013"
TASK = "00000000-0000-4000-8000-000000000004"
TURN = "00000000-0000-4000-8000-000000000005"
GRANT = "00000000-0000-4000-8000-000000000006"
ACTION = "00000000-0000-4000-8000-000000000007"
PAYLOAD = "00000000-0000-4000-8000-000000000008"
APPROVAL = "00000000-0000-4000-8000-000000000009"
PREVIEW = "00000000-0000-4000-8000-00000000000a"
SESSION = "1" * 64
SNAPSHOT = "a" * 64
SCOPES = "b" * 64
PARAMETERS = "c" * 64
PREVIEW_COMMITMENT = "d" * 64


def _ref(
    *,
    payload_id: str = PAYLOAD,
    action: ConnectorActionKind = ConnectorActionKind.MAIL_GET,
    commitment: str = PARAMETERS,
) -> ConnectedPayloadRef:
    return ConnectedPayloadRef(
        payload_id=payload_id,
        owner_id=OWNER,
        connection_id=CONNECTION,
        action_id=ACTION,
        provider=ConnectorProvider.GOOGLE,
        action=action,
        commitment_key_id="commitment-1",
        payload_sha256=commitment,
        created_at=NOW,
        expires_at=EXPIRES,
    )


def _command(*, write: bool = False) -> ConnectedActionPreparationCommand:
    action = ConnectorActionKind.MAIL_SEND if write else ConnectorActionKind.MAIL_GET
    payload = _ref(action=action)
    review = (
        _ref(payload_id=PREVIEW, action=action, commitment=PREVIEW_COMMITMENT) if write else None
    )
    return ConnectedActionPreparationCommand.build(
        request_id=REQUEST,
        owner_id=OWNER,
        session_id=SESSION_ID,
        session_binding_sha256=SESSION,
        grant_id=GRANT,
        action_id=ACTION,
        task_id=TASK,
        turn_id=TURN,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=action,
        authorization_revision=2,
        authorization_snapshot_sha256=SNAPSHOT,
        granted_actions_sha256=action_set_sha256(
            (ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND)
        ),
        granted_scopes_sha256=SCOPES,
        task_state_revision=1,
        payload=payload,
        resource_version_sha256=None,
        approval_id=APPROVAL if write else None,
        review_payload=review,
        requested_at=NOW,
        expires_at=EXPIRES,
    )


def _view(command: ConnectedActionPreparationCommand) -> ConnectedActionPreparationView:
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
        grant_actions_sha256=command.grant_actions_sha256,
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
        preview_reference_binding_sha256=(None if review is None else review.binding_sha256),
        preview_sha256=None if review is None else review.payload_sha256,
        requested_at=command.requested_at,
        expires_at=command.expires_at,
    )


def _row(view: ConnectedActionPreparationView) -> dict[str, object]:
    return {
        "request_id": view.request_id,
        "owner_id": view.owner_id,
        "command_binding_sha256": view.command_binding_sha256,
        "grant_id": view.grant_id,
        "action_id": view.action_id,
        "task_id": view.task_id,
        "turn_id": view.turn_id,
        "connection_id": view.connection_id,
        "provider": view.provider.value,
        "resource": view.resource.value,
        "action": view.action.value,
        "authorization_revision": view.authorization_revision,
        "authorization_snapshot_sha256": view.authorization_snapshot_sha256,
        "granted_actions_sha256": view.granted_actions_sha256,
        "granted_scopes_sha256": view.granted_scopes_sha256,
        "grant_actions_sha256": view.grant_actions_sha256,
        "task_state_revision": view.task_state_revision,
        "payload_id": view.payload_id,
        "payload_reference_binding_sha256": view.payload_reference_binding_sha256,
        "parameters_sha256": view.parameters_sha256,
        "resource_version_sha256": view.resource_version_sha256,
        "policy_version": view.policy_version,
        "mutates_external_state": view.mutates_external_state,
        "approval_class": view.approval_class.value,
        "status": view.status.value,
        "approval_id": view.approval_id,
        "approval_binding_sha256": view.approval_binding_sha256,
        "preview_payload_id": view.preview_payload_id,
        "preview_reference_binding_sha256": view.preview_reference_binding_sha256,
        "preview_sha256": view.preview_sha256,
        "requested_at": view.requested_at.isoformat(),
        "expires_at": view.expires_at.isoformat(),
    }


def test_read_preparation_builds_exact_runtime_intent_and_one_action_grant() -> None:
    command = _command()
    result = _view(command)

    assert action_preparation_result_matches(command, result)
    assert result.status is ConnectedActionPreparationStatus.READY
    assert result.intent().parameters_sha256 == PARAMETERS
    assert result.intent().action_id == ACTION
    assert result.grant().actions == frozenset({ConnectorActionKind.MAIL_GET})
    assert result.grant().actions_sha256 == action_set_sha256((ConnectorActionKind.MAIL_GET,))


def test_write_preparation_is_review_only_and_all_commitments_are_opaque() -> None:
    command = _command(write=True)
    result = _view(command)

    assert action_preparation_result_matches(command, result)
    assert result.status is ConnectedActionPreparationStatus.PENDING_APPROVAL
    assert result.approval_class is ConnectorApprovalClass.EXTERNAL_COMMUNICATION
    assert result.parameters_sha256 == PARAMETERS
    assert result.preview_sha256 == PREVIEW_COMMITMENT
    assert all("target" not in item.name for item in fields(ConnectedActionPreparationView))
    assert "recipient" not in repr(command).casefold()
    assert "content" not in _row(result)


def test_preparation_rejects_plain_or_partial_review_bindings() -> None:
    read = _command()
    write = _command(write=True)

    with pytest.raises(ValueError, match="read preparation cannot carry"):
        replace(read, approval_id=APPROVAL)
    with pytest.raises(ValueError, match="write preparation requires"):
        replace(write, review_payload=None)
    with pytest.raises(ValueError, match="command binding"):
        replace(write, command_binding_sha256="f" * 64)
    with pytest.raises(ValueError, match="payload lifetime"):
        replace(read, expires_at=EXPIRES + timedelta(seconds=1))
    with pytest.raises(ValueError, match="command binding"):
        replace(read, session_id="00000000-0000-4000-8000-00000000000c")
    assert SESSION_ID not in repr(read)


class Control:
    def __init__(self, value: ConnectedActionPreparationView) -> None:
        self.value = value
        self.fail_write = False
        self.readback: ConnectedActionPreparationView | None = None
        self.calls: list[str] = []

    async def prepare_action_once(self, _command):
        self.calls.append("prepare")
        if self.fail_write:
            raise TimeoutError
        return self.value

    async def readback_action_preparation(self, **_kwargs):
        self.calls.append("readback")
        return self.readback


@pytest.mark.asyncio
async def test_service_uses_exact_response_loss_readback_without_execution() -> None:
    command = _command(write=True)
    control = Control(_view(command))
    control.fail_write = True
    control.readback = _view(command)
    service = ConnectedActionPreparationService(control_plane=control)

    assert await service.prepare(command) == _view(command)
    assert control.calls == ["prepare", "readback"]
    assert not hasattr(service, "execute")


@pytest.mark.asyncio
async def test_service_fails_closed_on_missing_or_mismatched_readback() -> None:
    command = _command()
    control = Control(_view(command))
    control.fail_write = True
    service = ConnectedActionPreparationService(control_plane=control)
    with pytest.raises(ConnectedActionPreparationError) as missing:
        await service.prepare(command)
    assert missing.value.code == "CONNECTED_ACTION_PREPARATION_FAILED"
    assert missing.value.retryable is True

    control.readback = replace(_view(command), payload_id=PREVIEW)
    with pytest.raises(ConnectedActionPreparationError) as mismatch:
        await service.prepare(command)
    assert mismatch.value.code == "CONNECTED_ACTION_PREPARATION_RESULT_INVALID"


class RPC:
    def __init__(self) -> None:
        self.responses: dict[str, object] = {}
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        return self.responses.get(name)


class OAuth:
    async def start_once(self, _command):
        raise AssertionError

    async def read_start(self, **_kwargs):
        raise AssertionError

    async def complete_once(self, _command):
        raise AssertionError

    async def read_completion(self, **_kwargs):
        raise AssertionError


class Previews:
    async def resolve(self, **_kwargs):
        raise AssertionError


def _adapter(rpc: RPC) -> SupabaseConnectedAppControlPlane:
    return SupabaseConnectedAppControlPlane(
        database=rpc,
        oauth=OAuth(),
        previews=Previews(),
    )


@pytest.mark.asyncio
async def test_adapter_uses_exact_prepare_rpc_and_readback_retry_domain() -> None:
    command = _command(write=True)
    expected = _view(command)
    rpc = RPC()
    rpc.responses["connected_app_operator_prepare_action_v1"] = _row(expected)
    rpc.responses["connected_app_operator_read_action_preparation_v1"] = _row(expected)
    adapter = _adapter(rpc)

    assert await adapter.prepare_action_once(command) == expected
    assert await adapter.readback_action_preparation(owner_id=OWNER, request_id=REQUEST) == expected
    write_name, write_payload, write_retry = rpc.calls[0]
    assert write_name == "connected_app_operator_prepare_action_v1"
    assert write_retry is False
    assert set(write_payload) == {
        "p_request_id",
        "p_owner_id",
        "p_session_id",
        "p_session_binding_sha256",
        "p_command_binding_sha256",
        "p_grant_id",
        "p_action_id",
        "p_task_id",
        "p_turn_id",
        "p_connection_id",
        "p_provider",
        "p_resource",
        "p_action",
        "p_authorization_revision",
        "p_authorization_snapshot_sha256",
        "p_granted_actions_sha256",
        "p_granted_scopes_sha256",
        "p_task_state_revision",
        "p_payload_id",
        "p_payload_reference_binding_sha256",
        "p_parameters_sha256",
        "p_resource_version_sha256",
        "p_policy_version",
        "p_approval_id",
        "p_approval_binding_sha256",
        "p_preview_payload_id",
        "p_preview_reference_binding_sha256",
        "p_preview_sha256",
        "p_requested_at",
        "p_expires_at",
    }
    assert "target" not in " ".join(write_payload)
    assert rpc.calls[1][2] is True


@pytest.mark.asyncio
async def test_multi_account_action_remains_bound_to_selected_microsoft_connection() -> None:
    payload = ConnectedPayloadRef(
        payload_id=PAYLOAD,
        owner_id=OWNER,
        connection_id=WORK_CONNECTION,
        action_id=ACTION,
        provider=ConnectorProvider.MICROSOFT,
        action=ConnectorActionKind.MAIL_GET,
        commitment_key_id="commitment-1",
        payload_sha256=PARAMETERS,
        created_at=NOW,
        expires_at=EXPIRES,
    )
    command = ConnectedActionPreparationCommand.build(
        request_id=REQUEST,
        owner_id=OWNER,
        session_id=SESSION_ID,
        session_binding_sha256=SESSION,
        grant_id=GRANT,
        action_id=ACTION,
        task_id=TASK,
        turn_id=TURN,
        connection_id=WORK_CONNECTION,
        provider=ConnectorProvider.MICROSOFT,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_GET,
        authorization_revision=2,
        authorization_snapshot_sha256=SNAPSHOT,
        granted_actions_sha256=action_set_sha256((ConnectorActionKind.MAIL_GET,)),
        granted_scopes_sha256=SCOPES,
        task_state_revision=1,
        payload=payload,
        resource_version_sha256=None,
        requested_at=NOW,
        expires_at=EXPIRES,
    )
    expected = _view(command)
    rpc = RPC()
    rpc.responses["connected_app_operator_prepare_action_v1"] = _row(expected)
    adapter = _adapter(rpc)

    assert (await adapter.prepare_action_once(command)).connection_id == WORK_CONNECTION
    name, sent, retry = rpc.calls[0]
    assert name == "connected_app_operator_prepare_action_v1"
    assert sent["p_connection_id"] == WORK_CONNECTION
    assert sent["p_provider"] == "microsoft"
    assert retry is False


@pytest.mark.asyncio
async def test_adapter_rejects_extra_missing_or_semantically_invalid_rows() -> None:
    command = _command()
    valid = _row(_view(command))
    rpc = RPC()
    adapter = _adapter(rpc)

    rpc.responses["connected_app_operator_prepare_action_v1"] = {**valid, "content": "x"}
    with pytest.raises(ConnectedControlPlaneError):
        await adapter.prepare_action_once(command)
    rpc.responses["connected_app_operator_prepare_action_v1"] = {
        key: value for key, value in valid.items() if key != "grant_id"
    }
    with pytest.raises(ConnectedControlPlaneError):
        await adapter.prepare_action_once(command)
    rpc.responses["connected_app_operator_prepare_action_v1"] = {
        **valid,
        "status": "pending_approval",
    }
    with pytest.raises(ConnectedControlPlaneError):
        await adapter.prepare_action_once(command)


def test_preparation_protocol_guard_is_separate_and_exact() -> None:
    require_action_preparation_protocol(Control(_view(_command())))
    with pytest.raises(Exception):
        require_action_preparation_protocol(object())
