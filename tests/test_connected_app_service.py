from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import pickle
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

import pytest

from backend.connected_app_contracts import (
    CalendarCancelRequest,
    CalendarCreateRequest,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    EventSnapshot,
    EventSpec,
    MailDraftSpec,
    MailSendRequest,
)
from backend.connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    implemented_runtime_actions,
)
from backend.connected_app_scopes import delegated_scope_plan
from backend.connected_app_service import (
    ConnectedApprovalReviewPreview,
    ConnectedActionPublicStatus,
    ConnectedActionView,
    ConnectedAppReadiness,
    ConnectedAppService,
    ConnectedAppServiceError,
    ConnectedApprovalDecision,
    ConnectedApprovalStatus,
    ConnectedApprovalView,
    ConnectedConnectionView,
    ConnectedConnectionAuthorityView,
    ConnectedCalendarReviewPayload,
    ConnectedMailReviewPayload,
    DisconnectView,
    ConnectedScheduleStatus,
    ConnectedScheduleView,
    OAuthCallbackCommand,
    OAuthStartView,
    approval_execution_parameters_sha256,
    approval_review_display_sha256,
    approval_review_preview_sha256,
    connected_app_readiness_attestation_sha256,
    oauth_start_result_binding_sha256,
    schedule_create_result_matches,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
REQUEST = "00000000-0000-4000-8000-000000000003"
CONNECTION = "00000000-0000-4000-8000-000000000004"
FLOW = "00000000-0000-4000-8000-000000000005"
TASK = "00000000-0000-4000-8000-000000000006"
TEMPLATE = "00000000-0000-4000-8000-000000000007"
SCHEDULE = "00000000-0000-4000-8000-000000000008"
ACTION = "00000000-0000-4000-8000-000000000009"
TURN = "00000000-0000-4000-8000-00000000000a"
APPROVAL = "00000000-0000-4000-8000-00000000000b"
DECISION = "00000000-0000-4000-8000-00000000000c"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
MANIFEST_SHA = "e" * 64
GOOGLE_CLIENT_ID = "ask-crump-google-client.apps.googleusercontent.com"
MICROSOFT_CLIENT_ID = "00000000-0000-4000-8000-000000000099"
OAUTH_STATE = "s" * 43
PKCE_CHALLENGE = "p" * 43
GOOGLE_REDIRECT = "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
MICROSOFT_REDIRECT = "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"


def active_connection() -> ConnectedConnectionView:
    return ConnectedConnectionView(
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        granted_actions=(ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND),
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        expires_at=NOW + timedelta(hours=1),
        updated_at=NOW,
    )


def revoked_connection() -> ConnectedConnectionView:
    return replace(
        active_connection(),
        authorization_state=ConnectionAuthorizationState.REVOKED,
        authorization_snapshot_sha256=None,
        expires_at=None,
    )


def disconnected() -> DisconnectView:
    return DisconnectView(
        connection=revoked_connection(),
        grants_invalidated=True,
        schedules_invalidated=True,
        broker_cleanup_enqueued=True,
        updated_at=NOW,
    )


def schedule(
    *,
    status: ConnectedScheduleStatus = ConnectedScheduleStatus.ACTIVE,
    revision: int = 1,
) -> ConnectedScheduleView:
    return ConnectedScheduleView(
        schedule_id=SCHEDULE,
        connection_id=CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_B,
        task_state_revision=revision,
        time_zone="America/New_York",
        cadence_seconds=3600,
        quiet_start_minute=22 * 60,
        quiet_end_minute=7 * 60,
        requires_approval_every_run=True,
        status=status,
        next_run_at=(
            NOW + timedelta(hours=1) if status is ConnectedScheduleStatus.ACTIVE else None
        ),
        updated_at=NOW,
    )


def mail_review_payload() -> ConnectedMailReviewPayload:
    return ConnectedMailReviewPayload(
        account=CONNECTION,
        to=("recipient@example.com",),
        cc=(),
        bcc=(),
        subject="Exact approval subject",
        body_text="Confidential exact approval body",
        reply_context=None,
    )


def mail_preview_sha256() -> str:
    return approval_review_preview_sha256(
        approval_id=APPROVAL,
        action_id=ACTION,
        action=ConnectorActionKind.MAIL_SEND,
        approval_binding_sha256=SHA_A,
        parameters_sha256=mail_parameters_sha256(),
        resource_version_sha256=None,
        payload=mail_review_payload(),
        preview_commitment_sha256=SHA_C,
    )


def mail_parameters_sha256() -> str:
    return approval_execution_parameters_sha256(
        action=ConnectorActionKind.MAIL_SEND,
        provider_request=mail_provider_request(),
        payload_commitment_sha256=SHA_B,
    )


def mail_provider_request() -> MailSendRequest:
    return MailSendRequest.build(
        MailDraftSpec(
            to=("recipient@example.com",),
            cc=(),
            bcc=(),
            subject="Exact approval subject",
            body_text="Confidential exact approval body",
        )
    )


def pending_approval(*, expires_at: datetime | None = None) -> ConnectedApprovalView:
    preview_sha256 = mail_preview_sha256()
    return ConnectedApprovalView(
        approval_id=APPROVAL,
        action_id=ACTION,
        connection_id=CONNECTION,
        task_id=TASK,
        turn_id=TURN,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        granted_scopes_sha256=SHA_D,
        policy_version=ConnectedActionPolicy.version,
        action_revision=1,
        status=ConnectedApprovalStatus.PENDING,
        approval_binding_sha256=SHA_A,
        parameters_sha256=mail_parameters_sha256(),
        resource_version_sha256=None,
        preview_sha256=preview_sha256,
        review_preview=ConnectedApprovalReviewPreview(
            approval_binding_sha256=SHA_A,
            parameters_sha256=mail_parameters_sha256(),
            preview_sha256=preview_sha256,
            payload=mail_review_payload(),
            connection_id=CONNECTION,
            action=ConnectorActionKind.MAIL_SEND,
            resource_version_sha256=None,
            provider_request=mail_provider_request(),
        ),
        decision_id=None,
        decision_session_binding_sha256=None,
        expires_at=expires_at or NOW + timedelta(minutes=5),
        decided_at=None,
    )


def action_view() -> ConnectedActionView:
    return ConnectedActionView(
        action_id=ACTION,
        connection_id=CONNECTION,
        task_id=TASK,
        turn_id=TURN,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        granted_scopes_sha256=SHA_D,
        policy_version=ConnectedActionPolicy.version,
        action_revision=1,
        status=ConnectedActionPublicStatus.PENDING_APPROVAL,
        parameters_sha256=mail_parameters_sha256(),
        resource_version_sha256=None,
        preview_sha256=mail_preview_sha256(),
        updated_at=NOW,
    )


def connection_authority() -> ConnectedConnectionAuthorityView:
    return ConnectedConnectionAuthorityView(
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        granted_scopes_sha256=SHA_D,
        granted_actions=(ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND),
        expires_at=NOW + timedelta(hours=1),
    )


def calendar_authority() -> ConnectedConnectionAuthorityView:
    return ConnectedConnectionAuthorityView(
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        granted_scopes_sha256=SHA_D,
        granted_actions=(ConnectorActionKind.CALENDAR_CREATE,),
        expires_at=NOW + timedelta(hours=1),
    )


class FakeControlPlane:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_start = False
        self.fail_disconnect = False
        self.fail_create_schedule = False
        self.fail_decision = False
        self.decision_response_lost = False
        self.current_approval = pending_approval()
        self.current_action = action_view()
        self.current_authority = connection_authority()
        self.current_schedule = schedule()
        self.schedule_create_readback: ConnectedScheduleView | None = None
        self.create_result_override: ConnectedScheduleView | None = None
        self.last_decision_id: str | None = None
        self.last_oauth_command = None
        self.oauth_redirect_override: str | None = None
        self.oauth_scope_override: tuple[str, ...] | None = None
        self.oauth_host_override: str | None = None
        self.oauth_extra_parameter: tuple[str, str] | None = None
        self.oauth_client_id_override: str | None = None
        self.oauth_state_override: str | None = None
        self.oauth_challenge_override: str | None = None
        self.oauth_method_override: str | None = None
        self.oauth_response_type_override: str | None = None
        self.oauth_binding_override: str | None = None

    async def list_connections(self, *, owner_id: str):
        self.calls.append(f"list-connections:{owner_id}")
        return (active_connection(),)

    async def get_connection_authority(self, *, owner_id: str, connection_id: str):
        self.calls.append(f"get-authority:{owner_id}:{connection_id}")
        return self.current_authority

    async def start_oauth_once(self, command):
        self.calls.append("start-oauth")
        self.last_oauth_command = command
        if self.fail_start:
            raise RuntimeError("provider-secret-that-must-not-escape")
        return await self.readback_oauth_start(
            owner_id=command.owner_id, request_id=command.request_id
        )

    async def readback_oauth_start(self, *, owner_id: str, request_id: str):
        self.calls.append("readback-oauth")
        command = self.last_oauth_command
        assert command is not None
        plan = delegated_scope_plan(
            command.provider,
            command.actions,
            account_kind=command.account_kind,
        )
        parameters = {
            "client_id": self.oauth_client_id_override
            or (
                GOOGLE_CLIENT_ID
                if command.provider is ConnectorProvider.GOOGLE
                else MICROSOFT_CLIENT_ID
            ),
            "redirect_uri": self.oauth_redirect_override or command.redirect_uri,
            "response_type": self.oauth_response_type_override or "code",
            "scope": " ".join(self.oauth_scope_override or plan.delegated_scopes),
            "state": self.oauth_state_override or OAUTH_STATE,
            "code_challenge": self.oauth_challenge_override or PKCE_CHALLENGE,
            "code_challenge_method": self.oauth_method_override or "S256",
        }
        if command.provider is ConnectorProvider.GOOGLE:
            parameters.update({"access_type": "offline", "include_granted_scopes": "false"})
        else:
            parameters["response_mode"] = "query"
        if self.oauth_extra_parameter is not None:
            parameters[self.oauth_extra_parameter[0]] = self.oauth_extra_parameter[1]
        host = self.oauth_host_override or (
            "accounts.google.com"
            if command.provider is ConnectorProvider.GOOGLE
            else "login.microsoftonline.com"
        )
        path = (
            "/o/oauth2/v2/auth"
            if command.provider is ConnectorProvider.GOOGLE
            else (
                "/consumers/oauth2/v2.0/authorize"
                if command.account_kind is ConnectorAccountKind.PERSONAL
                else "/organizations/oauth2/v2.0/authorize"
            )
        )
        authorization_url = f"https://{host}{path}?{urlencode(parameters)}"
        expires_at = NOW + timedelta(minutes=5)
        return OAuthStartView(
            request_id=request_id,
            flow_id=FLOW,
            connection_id=CONNECTION,
            provider=command.provider,
            authorization_url=authorization_url,
            state_sha256=hashlib.sha256(OAUTH_STATE.encode()).hexdigest(),
            pkce_challenge=PKCE_CHALLENGE,
            command_binding_sha256=(
                self.oauth_binding_override
                or oauth_start_result_binding_sha256(
                    command,
                    flow_id=FLOW,
                    connection_id=CONNECTION,
                    authorization_url=authorization_url,
                    state_sha256=hashlib.sha256(OAUTH_STATE.encode()).hexdigest(),
                    pkce_challenge=PKCE_CHALLENGE,
                    expires_at=expires_at,
                )
            ),
            expires_at=expires_at,
        )

    async def complete_oauth_callback(self, command):
        self.calls.append("oauth-callback")
        return active_connection()

    async def deny_oauth_callback(self, **kwargs):
        self.calls.append("oauth-denied")
        self.last_oauth_command = kwargs

    async def readback_oauth_callback(self, **_kwargs):
        self.calls.append("readback-callback")
        return active_connection()

    async def disconnect_once(self, command):
        self.calls.append("disconnect")
        if self.fail_disconnect:
            raise RuntimeError("credential material")
        return disconnected()

    async def readback_disconnect(self, **_kwargs):
        self.calls.append("readback-disconnect")
        return disconnected()

    async def list_schedules(self, *, owner_id: str):
        self.calls.append(f"list-schedules:{owner_id}")
        return (self.current_schedule,)

    async def get_schedule(self, *, owner_id: str, schedule_id: str):
        self.calls.append(f"get-schedule:{owner_id}:{schedule_id}")
        return self.current_schedule

    async def create_schedule_once(self, command):
        self.calls.append("create-schedule")
        candidate = self.create_result_override or schedule()
        if schedule_create_result_matches(command, candidate):
            self.current_schedule = candidate
            self.schedule_create_readback = candidate
        if self.fail_create_schedule:
            raise RuntimeError("customer calendar content")
        return candidate

    async def readback_schedule_create(self, **_kwargs):
        self.calls.append("readback-schedule-create")
        return self.schedule_create_readback

    async def transition_schedule_once(self, command):
        self.calls.append("transition-schedule")
        self.current_schedule = replace(
            self.current_schedule,
            status=command.target,
            task_state_revision=command.expected_task_state_revision + 1,
            next_run_at=(
                NOW + timedelta(hours=1)
                if command.target is ConnectedScheduleStatus.ACTIVE
                else None
            ),
            updated_at=NOW,
        )
        return self.current_schedule

    async def readback_schedule_transition(self, **_kwargs):
        self.calls.append("readback-schedule-transition")
        return None

    async def list_actions(self, *, owner_id: str):
        self.calls.append(f"list-actions:{owner_id}")
        return (await self.get_action(owner_id=owner_id, action_id=ACTION),)

    async def get_action(self, *, owner_id: str, action_id: str):
        self.calls.append(f"get-action:{owner_id}")
        return self.current_action if action_id == ACTION else None

    async def list_approvals(self, *, owner_id: str):
        self.calls.append(f"list-approvals:{owner_id}")
        return (self.current_approval,)

    async def get_approval(self, *, owner_id: str, approval_id: str):
        self.calls.append(f"get-approval:{owner_id}:{approval_id}")
        return self.current_approval

    async def decide_approval_once(self, command):
        self.calls.append("decide-approval")
        self.last_decision_id = command.decision_id
        status = (
            ConnectedApprovalStatus.APPROVED
            if command.decision is ConnectedApprovalDecision.APPROVED
            else ConnectedApprovalStatus.DENIED
        )
        self.current_approval = replace(
            self.current_approval,
            status=status,
            decision_id=command.decision_id,
            decision_session_binding_sha256=command.session_binding_sha256,
            decided_at=command.decided_at,
        )
        if self.fail_decision or self.decision_response_lost:
            raise RuntimeError("raw message body")
        return self.current_approval

    async def readback_approval_decision(self, **kwargs):
        self.calls.append("readback-approval")
        if kwargs["decision_id"] != self.last_decision_id:
            return None
        status = ConnectedApprovalStatus.APPROVED
        self.current_approval = replace(self.current_approval, status=status, decided_at=NOW)
        return self.current_approval


def readiness(
    *,
    ready: bool = True,
    manifest: str = MANIFEST_SHA,
    checked_at: datetime = NOW - timedelta(minutes=1),
    expires_at: datetime = NOW + timedelta(minutes=10),
) -> ConnectedAppReadiness:
    return ConnectedAppReadiness(
        ready=ready,
        attestation_sha256=connected_app_readiness_attestation_sha256(
            ready=ready,
            composition_manifest_sha256=manifest,
            checked_at=checked_at,
            expires_at=expires_at,
        ),
        composition_manifest_sha256=manifest,
        checked_at=checked_at,
        expires_at=expires_at,
    )


def service(
    plane: FakeControlPlane,
    *,
    readiness_record: ConnectedAppReadiness | None = None,
    now: datetime = NOW,
):
    return ConnectedAppService(
        control_plane=plane,
        readiness_source=lambda: readiness_record
        or readiness(
            checked_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=10),
        ),
        expected_composition_manifest_sha256=MANIFEST_SHA,
        redirect_allowlist={
            ConnectorProvider.GOOGLE: frozenset({GOOGLE_REDIRECT}),
            ConnectorProvider.MICROSOFT: frozenset({MICROSOFT_REDIRECT}),
        },
        oauth_client_ids={
            ConnectorProvider.GOOGLE: GOOGLE_CLIENT_ID,
            ConnectorProvider.MICROSOFT: MICROSOFT_CLIENT_ID,
        },
        now=lambda: now,
    )


def test_readiness_source_can_renew_after_a_short_lapse() -> None:
    current = {
        "value": readiness(
            checked_at=NOW - timedelta(minutes=2),
            expires_at=NOW - timedelta(seconds=1),
        )
    }
    subject = ConnectedAppService(
        control_plane=FakeControlPlane(),
        readiness_source=lambda: current["value"],
        expected_composition_manifest_sha256=MANIFEST_SHA,
        redirect_allowlist={
            ConnectorProvider.GOOGLE: frozenset({GOOGLE_REDIRECT}),
            ConnectorProvider.MICROSOFT: frozenset({MICROSOFT_REDIRECT}),
        },
        oauth_client_ids={
            ConnectorProvider.GOOGLE: GOOGLE_CLIENT_ID,
            ConnectorProvider.MICROSOFT: MICROSOFT_CLIENT_ID,
        },
        now=lambda: NOW,
    )

    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPS_NOT_READY"):
        subject.require_ready()

    current["value"] = readiness(
        checked_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    subject.require_ready()


def test_public_readiness_manifest_is_exact_fresh_and_content_free():
    subject = service(FakeControlPlane())
    first = subject.public_readiness_manifest()
    second = subject.public_readiness_manifest()
    expected_actions = sorted(action.value for action in implemented_runtime_actions())
    assert first == {
        "providers": ["google", "microsoft"],
        "capabilities": {
            "google": expected_actions,
            "microsoft": expected_actions,
        },
        "oauthClientIds": {
            "google": GOOGLE_CLIENT_ID,
            "microsoft": MICROSOFT_CLIENT_ID,
        },
    }
    assert second == first
    assert second is not first
    assert second["capabilities"] is not first["capabilities"]
    assert "secret" not in repr(first).casefold()


@pytest.mark.asyncio
async def test_readiness_blocks_before_any_dependency_call():
    plane = FakeControlPlane()
    subject = service(
        plane,
        readiness_record=readiness(
            checked_at=NOW - timedelta(minutes=10),
            expires_at=NOW - timedelta(seconds=1),
        ),
    )
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPS_NOT_READY"):
        await subject.list_connections(owner_id=OWNER)
    assert plane.calls == []


@pytest.mark.parametrize(
    "readiness",
    (
        readiness(
            checked_at=NOW + timedelta(seconds=31),
            expires_at=NOW + timedelta(minutes=5),
        ),
        readiness(
            manifest=SHA_D,
            checked_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=5),
        ),
    ),
)
@pytest.mark.asyncio
async def test_readiness_rejects_future_clock_or_wrong_composition_manifest(readiness):
    plane = FakeControlPlane()
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPS_NOT_READY"):
        await service(plane, readiness_record=readiness).list_connections(owner_id=OWNER)
    assert plane.calls == []


def test_readiness_attestation_is_cryptographically_bound_to_manifest_and_window():
    record = readiness()
    with pytest.raises(ValueError, match="readiness attestation binding is invalid"):
        replace(record, composition_manifest_sha256=SHA_D)
    with pytest.raises(ValueError, match="readiness attestation binding is invalid"):
        replace(record, expires_at=record.expires_at - timedelta(seconds=1))


@pytest.mark.asyncio
async def test_oauth_requires_explicit_user_action_and_response_loss_readback():
    plane = FakeControlPlane()
    subject = service(plane)
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_USER_ACTION_REQUIRED"):
        await subject.start_oauth(
            request_id=REQUEST,
            owner_id=OWNER,
            session_id=SESSION,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            account_kind=ConnectorAccountKind.PERSONAL,
            actions=frozenset({ConnectorActionKind.MAIL_GET}),
            redirect_uri=GOOGLE_REDIRECT,
            connection_id=None,
            confirmed=False,
        )
    assert plane.calls == []

    plane.fail_start = True
    result = await subject.start_oauth(
        request_id=REQUEST,
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        actions=frozenset({ConnectorActionKind.MAIL_GET}),
        redirect_uri=GOOGLE_REDIRECT,
        connection_id=None,
        confirmed=True,
    )
    assert result.request_id == REQUEST
    assert plane.calls == ["start-oauth", "readback-oauth"]
    assert "provider-secret" not in repr(result)


@pytest.mark.asyncio
async def test_microsoft_oauth_start_binds_exact_client_redirect_and_offline_scope_plan():
    result = await service(FakeControlPlane()).start_oauth(
        request_id=REQUEST,
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.MICROSOFT,
        resource=ConnectorResource.CALENDAR,
        account_kind=ConnectorAccountKind.WORK_SCHOOL,
        actions=frozenset({ConnectorActionKind.CALENDAR_CREATE}),
        redirect_uri=MICROSOFT_REDIRECT,
        connection_id=None,
        confirmed=True,
    )
    parameters = result.query_parameters()
    assert parameters["client_id"] == MICROSOFT_CLIENT_ID
    assert parameters["redirect_uri"] == MICROSOFT_REDIRECT
    assert parameters["response_type"] == "code"
    assert parameters["code_challenge_method"] == "S256"
    assert parameters["response_mode"] == "query"
    assert urlsplit(result.authorization_url).path == "/organizations/oauth2/v2.0/authorize"
    assert (
        tuple(sorted(parameters["scope"].split(" ")))
        == delegated_scope_plan(
            ConnectorProvider.MICROSOFT,
            {ConnectorActionKind.CALENDAR_CREATE},
            account_kind=ConnectorAccountKind.WORK_SCHOOL,
        ).delegated_scopes
    )
    assert "offline_access" in parameters["scope"].split(" ")


@pytest.mark.asyncio
async def test_microsoft_oauth_start_rejects_account_kind_tenant_mismatch():
    plane = FakeControlPlane()
    original = plane.start_oauth_once

    async def mismatched(command):
        result = await original(command)
        authorization_url = result.authorization_url.replace("/organizations/", "/consumers/")
        return replace(
            result,
            authorization_url=authorization_url,
            command_binding_sha256=oauth_start_result_binding_sha256(
                command,
                flow_id=result.flow_id,
                connection_id=result.connection_id,
                authorization_url=authorization_url,
                state_sha256=result.state_sha256,
                pkce_challenge=result.pkce_challenge,
                expires_at=result.expires_at,
            ),
        )

    plane.start_oauth_once = mismatched
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_OAUTH_START_RESULT_INVALID"):
        await service(plane).start_oauth(
            request_id=REQUEST,
            owner_id=OWNER,
            session_id=SESSION,
            provider=ConnectorProvider.MICROSOFT,
            resource=ConnectorResource.CALENDAR,
            account_kind=ConnectorAccountKind.WORK_SCHOOL,
            actions=frozenset({ConnectorActionKind.CALENDAR_CREATE}),
            redirect_uri=MICROSOFT_REDIRECT,
            connection_id=None,
            confirmed=True,
        )


@pytest.mark.parametrize(
    ("attribute", "value"),
    (
        ("oauth_redirect_override", MICROSOFT_REDIRECT),
        (
            "oauth_scope_override",
            (
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.readonly",
            ),
        ),
        ("oauth_host_override", "mail.google.com"),
        ("oauth_client_id_override", "wrong-client.apps.googleusercontent.com"),
        ("oauth_extra_parameter", ("code", "raw-authorization-code")),
        ("oauth_extra_parameter", ("authorization_code", "raw-authorization-code")),
        ("oauth_extra_parameter", ("client_assertion", "raw-client-assertion")),
        ("oauth_extra_parameter", ("client_assertion_type", "raw-assertion-type")),
        ("oauth_extra_parameter", ("access_token", "raw-access-token")),
        ("oauth_extra_parameter", ("refresh_token", "raw-refresh-token")),
        ("oauth_extra_parameter", ("id_token", "raw-id-token")),
        ("oauth_extra_parameter", ("client_secret", "raw-client-secret")),
        ("oauth_extra_parameter", ("code_verifier", "raw-code-verifier")),
        ("oauth_state_override", "x" * 43),
        ("oauth_challenge_override", "z" * 43),
        ("oauth_method_override", "plain"),
        ("oauth_response_type_override", "token"),
        ("oauth_binding_override", SHA_C),
    ),
)
@pytest.mark.asyncio
async def test_oauth_start_rejects_misbinding_and_credential_injection(
    attribute: str,
    value: object,
):
    plane = FakeControlPlane()
    setattr(plane, attribute, value)
    with pytest.raises(ConnectedAppServiceError) as raised:
        await service(plane).start_oauth(
            request_id=REQUEST,
            owner_id=OWNER,
            session_id=SESSION,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            account_kind=ConnectorAccountKind.PERSONAL,
            actions=frozenset({ConnectorActionKind.MAIL_GET}),
            redirect_uri=GOOGLE_REDIRECT,
            connection_id=None,
            confirmed=True,
        )
    assert raised.value.code in {
        "CONNECTED_OAUTH_START_FAILED",
        "CONNECTED_OAUTH_START_RESULT_INVALID",
    }
    assert "raw-" not in str(raised.value)


@pytest.mark.asyncio
async def test_callback_is_strict_state_bound_and_redacted():
    plane = FakeControlPlane()
    subject = service(plane)
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_OAUTH_CALLBACK_INVALID"):
        await subject.complete_oauth_callback(
            owner_id=OWNER,
            session_id=SESSION,
            provider=ConnectorProvider.GOOGLE,
            state="short",
            code="bad\ncode-that-is-too-short",
        )
    assert plane.calls == []

    command = OAuthCallbackCommand.build(
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        code="c" * 16,
        received_at=NOW,
    )
    rendered = repr(command)
    assert "s" * 43 not in rendered
    assert "c" * 16 not in rendered
    with pytest.raises(TypeError, match="cannot be serialized"):
        asdict(command)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(command)
    result = await subject.complete_oauth_callback(
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        code="c" * 16,
    )
    assert result.connection_id == CONNECTION


@pytest.mark.asyncio
async def test_access_denied_callback_retires_exact_owner_session_state_authority():
    plane = FakeControlPlane()
    subject = service(plane)

    await subject.deny_oauth_callback(
        owner_id=OWNER,
        session_id=SESSION,
        provider=ConnectorProvider.GOOGLE,
        state="s" * 43,
        error="access_denied",
    )

    assert plane.calls == ["oauth-denied"]
    assert plane.last_oauth_command == {
        "owner_id": OWNER,
        "session_binding_sha256": hashlib.sha256(SESSION.encode()).hexdigest(),
        "provider": ConnectorProvider.GOOGLE,
        "state_sha256": hashlib.sha256(("s" * 43).encode()).hexdigest(),
        "received_at": NOW,
    }
    for rejected in ("temporarily_unavailable", "server_error", ""):
        with pytest.raises(
            ConnectedAppServiceError, match="CONNECTED_OAUTH_CALLBACK_INVALID"
        ):
            await subject.deny_oauth_callback(
                owner_id=OWNER,
                session_id=SESSION,
                provider=ConnectorProvider.GOOGLE,
                state="s" * 43,
                error=rejected,
            )
    assert "s" * 43 not in repr(plane.last_oauth_command)


@pytest.mark.asyncio
async def test_disconnect_is_idempotent_and_recovers_response_loss():
    plane = FakeControlPlane()
    plane.fail_disconnect = True
    result = await service(plane).disconnect(
        request_id=REQUEST,
        owner_id=OWNER,
        session_id=SESSION,
        connection_id=CONNECTION,
        confirmed=True,
    )
    assert result.connection.authorization_state is ConnectionAuthorizationState.REVOKED
    assert result.connection.public()["grantedActions"] == ["mail.get", "mail.send"]
    assert result.public()["brokerCleanupEnqueued"] is True
    assert plane.calls == ["disconnect", "readback-disconnect"]
    assert "credential material" not in repr(result)


@pytest.mark.asyncio
async def test_schedule_uses_iana_zone_dst_and_quiet_hours_and_write_approval():
    plane = FakeControlPlane()
    plane.current_authority = calendar_authority()
    plane.fail_create_schedule = True
    subject = service(plane)
    values = dict(
        request_id=REQUEST,
        owner_id=OWNER,
        session_id=SESSION,
        connection_id=CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_B,
        time_zone="America/New_York",
        cadence_seconds=3600,
        quiet_start="22:00",
        quiet_end="07:00",
        requires_approval_every_run=True,
        confirmed=True,
    )
    result = await subject.create_schedule(**values)
    assert result.public()["quietStart"] == "22:00"
    assert result.public()["quietEnd"] == "07:00"
    assert result.time_zone == "America/New_York"
    assert "readback-schedule-create" in plane.calls

    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_SCHEDULE_APPROVAL_REQUIRED"):
        await subject.create_schedule(**(values | {"requires_approval_every_run": False}))
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_SCHEDULE_INVALID"):
        await subject.create_schedule(**(values | {"time_zone": "EST"}))


@pytest.mark.asyncio
async def test_schedule_allows_fall_back_quiet_window_of_almost_25_elapsed_hours():
    fall_back = datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc)
    plane = FakeControlPlane()
    plane.current_authority = calendar_authority()
    plane.create_result_override = replace(
        schedule(),
        time_zone="America/New_York",
        cadence_seconds=60,
        quiet_start_minute=31,
        quiet_end_minute=30,
        next_run_at=fall_back + timedelta(hours=25),
        updated_at=fall_back,
    )
    result = await service(plane, now=fall_back).create_schedule(
        request_id=REQUEST,
        owner_id=OWNER,
        session_id=SESSION,
        connection_id=CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_B,
        time_zone="America/New_York",
        cadence_seconds=60,
        quiet_start="00:31",
        quiet_end="00:30",
        requires_approval_every_run=True,
        confirmed=True,
    )
    assert result.next_run_at == fall_back + timedelta(hours=25)


@pytest.mark.asyncio
async def test_schedule_create_requires_exact_current_granted_action_before_mutation():
    plane = FakeControlPlane()
    plane.current_authority = replace(
        calendar_authority(),
        granted_actions=(ConnectorActionKind.CALENDAR_LIST,),
    )
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_ACTION_NOT_GRANTED"):
        await service(plane).create_schedule(
            request_id=REQUEST,
            owner_id=OWNER,
            session_id=SESSION,
            connection_id=CONNECTION,
            task_id=TASK,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.CALENDAR,
            action=ConnectorActionKind.CALENDAR_CREATE,
            action_template_ref=TEMPLATE,
            parameters_sha256=SHA_B,
            time_zone="America/New_York",
            cadence_seconds=3600,
            quiet_start="22:00",
            quiet_end="07:00",
            requires_approval_every_run=True,
            confirmed=True,
        )
    assert "create-schedule" not in plane.calls


@pytest.mark.parametrize(
    "invalid_result",
    (
        schedule(status=ConnectedScheduleStatus.PAUSED),
        schedule(revision=2),
        replace(schedule(), next_run_at=NOW + timedelta(days=2)),
    ),
)
@pytest.mark.asyncio
async def test_schedule_create_requires_active_revision_one_bounded_next_run(invalid_result):
    plane = FakeControlPlane()
    plane.current_authority = calendar_authority()
    previous = plane.current_schedule
    plane.create_result_override = invalid_result
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_SCHEDULE_RESULT_INVALID"):
        await service(plane).create_schedule(
            request_id=REQUEST,
            owner_id=OWNER,
            session_id=SESSION,
            connection_id=CONNECTION,
            task_id=TASK,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.CALENDAR,
            action=ConnectorActionKind.CALENDAR_CREATE,
            action_template_ref=TEMPLATE,
            parameters_sha256=SHA_B,
            time_zone="America/New_York",
            cadence_seconds=3600,
            quiet_start="22:00",
            quiet_end="07:00",
            requires_approval_every_run=True,
            confirmed=True,
        )
    assert plane.current_schedule is previous
    assert plane.schedule_create_readback is None


@pytest.mark.asyncio
async def test_schedule_transition_graph_and_exact_revision_are_enforced():
    plane = FakeControlPlane()
    subject = service(plane)
    common = {
        "owner_id": OWNER,
        "session_id": SESSION,
        "schedule_id": SCHEDULE,
        "confirmed": True,
    }
    paused = await subject.transition_schedule(
        request_id=REQUEST,
        expected_task_state_revision=1,
        expected_status=ConnectedScheduleStatus.ACTIVE,
        target=ConnectedScheduleStatus.PAUSED,
        **common,
    )
    assert paused.status is ConnectedScheduleStatus.PAUSED
    assert paused.task_state_revision == 2
    assert paused.next_run_at is None

    resumed = await subject.transition_schedule(
        request_id="00000000-0000-4000-8000-00000000000d",
        expected_task_state_revision=2,
        expected_status=ConnectedScheduleStatus.PAUSED,
        target=ConnectedScheduleStatus.ACTIVE,
        **common,
    )
    assert resumed.status is ConnectedScheduleStatus.ACTIVE
    assert resumed.task_state_revision == 3

    cancelled = await subject.transition_schedule(
        request_id="00000000-0000-4000-8000-00000000000e",
        expected_task_state_revision=3,
        expected_status=ConnectedScheduleStatus.ACTIVE,
        target=ConnectedScheduleStatus.CANCELLED,
        **common,
    )
    assert cancelled.status is ConnectedScheduleStatus.CANCELLED
    assert cancelled.task_state_revision == 4

    calls_before = tuple(plane.calls)
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_SCHEDULE_TRANSITION_INVALID"):
        await subject.transition_schedule(
            request_id="00000000-0000-4000-8000-00000000000f",
            expected_task_state_revision=4,
            expected_status=ConnectedScheduleStatus.CANCELLED,
            target=ConnectedScheduleStatus.ACTIVE,
            **common,
        )
    assert tuple(plane.calls) == calls_before

    plane.current_schedule = schedule(
        status=ConnectedScheduleStatus.PAUSED,
        revision=7,
    )
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_SCHEDULE_TRANSITION_INVALID"):
        await subject.transition_schedule(
            request_id="00000000-0000-4000-8000-000000000010",
            expected_task_state_revision=6,
            expected_status=ConnectedScheduleStatus.PAUSED,
            target=ConnectedScheduleStatus.ACTIVE,
            **common,
        )
    assert plane.calls[-1].startswith("get-schedule:")


@pytest.mark.asyncio
async def test_approval_rejects_substitution_expiry_and_replay():
    plane = FakeControlPlane()
    subject = service(plane)
    values = dict(
        decision_id=DECISION,
        owner_id=OWNER,
        session_id=SESSION,
        approval_id=APPROVAL,
        action_id=ACTION,
        connection_id=CONNECTION,
        task_id=TASK,
        turn_id=TURN,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        granted_scopes_sha256=SHA_D,
        policy_version=ConnectedActionPolicy.version,
        action_revision=1,
        approval_binding_sha256=SHA_A,
        parameters_sha256=mail_parameters_sha256(),
        resource_version_sha256=None,
        preview_sha256=mail_preview_sha256(),
        decision=ConnectedApprovalDecision.APPROVED,
        confirmed=True,
    )
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPROVAL_BINDING_MISMATCH"):
        await subject.decide_approval(**(values | {"action_id": TASK}))
    assert "decide-approval" not in plane.calls
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPROVAL_BINDING_MISMATCH"):
        await subject.decide_approval(**(values | {"preview_sha256": SHA_D}))
    assert "decide-approval" not in plane.calls

    plane.current_approval = pending_approval(expires_at=NOW - timedelta(seconds=1))
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPROVAL_EXPIRED"):
        await subject.decide_approval(**values)

    plane.current_approval = pending_approval()
    plane.decision_response_lost = True
    decided = await subject.decide_approval(**values)
    assert decided.status is ConnectedApprovalStatus.APPROVED
    assert "readback-approval" in plane.calls
    plane.decision_response_lost = False
    replay = await subject.decide_approval(**values)
    assert replay.status is ConnectedApprovalStatus.APPROVED
    plane.current_action = replace(
        action_view(),
        status=ConnectedActionPublicStatus.SUCCEEDED,
        updated_at=NOW + timedelta(seconds=1),
    )
    plane.current_authority = replace(
        connection_authority(),
        authorization_revision=2,
        authorization_snapshot_sha256=SHA_C,
        granted_scopes_sha256=SHA_C,
    )
    plane.calls.clear()
    replay_after_advance = await subject.decide_approval(**values)
    assert replay_after_advance.status is ConnectedApprovalStatus.APPROVED
    assert plane.calls == [f"get-approval:{OWNER}:{APPROVAL}", "readback-approval"]
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPROVAL_ALREADY_DECIDED"):
        await subject.decide_approval(
            **(values | {"decision_id": "00000000-0000-4000-8000-00000000000d"})
        )


@pytest.mark.asyncio
async def test_scheduled_occurrence_projection_is_decidable_through_owner_service():
    """A review-backed schedule action satisfies the ordinary decision preflight.

    Migration 066000 makes the existing action projection synthesize this
    pending action from the schedule occurrence's approval review.  The
    service deliberately keeps using its normal owner/action/connection
    checks; scheduled writes do not get a weaker approval path.
    """

    plane = FakeControlPlane()
    subject = service(plane)
    listed = await subject.list_approvals(owner_id=OWNER)
    pending = listed[0]

    decided = await subject.decide_approval(
        decision_id=DECISION,
        owner_id=OWNER,
        session_id=SESSION,
        approval_id=pending.approval_id,
        action_id=pending.action_id,
        connection_id=pending.connection_id,
        task_id=pending.task_id,
        turn_id=pending.turn_id,
        provider=pending.provider,
        resource=pending.resource,
        action=pending.action,
        authorization_revision=pending.authorization_revision,
        authorization_snapshot_sha256=pending.authorization_snapshot_sha256,
        granted_scopes_sha256=pending.granted_scopes_sha256,
        policy_version=pending.policy_version,
        action_revision=pending.action_revision,
        approval_binding_sha256=pending.approval_binding_sha256,
        parameters_sha256=pending.parameters_sha256,
        resource_version_sha256=pending.resource_version_sha256,
        preview_sha256=pending.preview_sha256,
        decision=ConnectedApprovalDecision.APPROVED,
        confirmed=True,
    )

    assert decided.status is ConnectedApprovalStatus.APPROVED
    assert decided.action_id == ACTION
    assert plane.calls == [
        f"list-approvals:{OWNER}",
        f"get-approval:{OWNER}:{APPROVAL}",
        f"get-action:{OWNER}",
        f"get-authority:{OWNER}:{CONNECTION}",
        "decide-approval",
    ]


@pytest.mark.parametrize(
    ("record_name", "replacement"),
    (
        (
            "current_authority",
            replace(
                connection_authority(),
                authorization_revision=2,
                authorization_snapshot_sha256=SHA_C,
            ),
        ),
        (
            "current_authority",
            replace(connection_authority(), granted_scopes_sha256=SHA_C),
        ),
        (
            "current_authority",
            replace(
                connection_authority(),
                granted_actions=(ConnectorActionKind.MAIL_GET,),
            ),
        ),
        (
            "current_action",
            replace(action_view(), task_id=SCHEDULE),
        ),
        (
            "current_action",
            replace(action_view(), provider=ConnectorProvider.MICROSOFT),
        ),
        (
            "current_action",
            replace(action_view(), policy_version="connected-app-policy-old"),
        ),
        (
            "current_action",
            replace(action_view(), action_revision=2),
        ),
        (
            "current_approval",
            replace(pending_approval(), turn_id=SCHEDULE),
        ),
    ),
)
@pytest.mark.asyncio
async def test_approval_rejects_reconnect_scope_downgrade_and_substitution(
    record_name: str,
    replacement: object,
):
    plane = FakeControlPlane()
    setattr(plane, record_name, replacement)
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPROVAL_BINDING_MISMATCH"):
        await service(plane).decide_approval(
            decision_id=DECISION,
            owner_id=OWNER,
            session_id=SESSION,
            approval_id=APPROVAL,
            action_id=ACTION,
            connection_id=CONNECTION,
            task_id=TASK,
            turn_id=TURN,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            action=ConnectorActionKind.MAIL_SEND,
            authorization_revision=1,
            authorization_snapshot_sha256=SHA_A,
            granted_scopes_sha256=SHA_D,
            policy_version=ConnectedActionPolicy.version,
            action_revision=1,
            approval_binding_sha256=SHA_A,
            parameters_sha256=mail_parameters_sha256(),
            resource_version_sha256=None,
            preview_sha256=mail_preview_sha256(),
            decision=ConnectedApprovalDecision.APPROVED,
            confirmed=True,
        )
    assert "decide-approval" not in plane.calls


def test_oauth_start_view_rejects_credential_material_in_authorization_url():
    parameters = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "state": OAUTH_STATE,
        "code_challenge": PKCE_CHALLENGE,
        "code_challenge_method": "S256",
        "access_token": "must-not-escape",
    }
    with pytest.raises(ValueError, match="authorization URL query is invalid"):
        OAuthStartView(
            request_id=REQUEST,
            flow_id=FLOW,
            connection_id=CONNECTION,
            provider=ConnectorProvider.GOOGLE,
            authorization_url=(
                f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(parameters)}"
            ),
            state_sha256=hashlib.sha256(OAUTH_STATE.encode()).hexdigest(),
            pkce_challenge=PKCE_CHALLENGE,
            command_binding_sha256=SHA_A,
            expires_at=NOW + timedelta(minutes=5),
        )


@pytest.mark.asyncio
async def test_action_summary_is_content_free_and_exact_approval_preview_repr_is_redacted():
    plane = FakeControlPlane()
    subject = service(plane)
    action = await subject.get_action(owner_id=OWNER, action_id=ACTION)
    approval = (await subject.list_approvals(owner_id=OWNER))[0]
    assert action.public()["previewSha256"] == mail_preview_sha256()
    assert approval.public()["reviewPreview"]["previewSha256"] == mail_preview_sha256()
    assert approval.public()["reviewPreview"]["displaySha256"] == (
        approval_review_display_sha256(
            approval_id=APPROVAL,
            action_id=ACTION,
            action=ConnectorActionKind.MAIL_SEND,
            approval_binding_sha256=SHA_A,
            parameters_sha256=mail_parameters_sha256(),
            resource_version_sha256=None,
            payload=mail_review_payload(),
        )
    )
    assert approval.public()["reviewPreview"]["displaySha256"] != mail_preview_sha256()
    assert approval.public()["reviewPreview"]["payload"]["bodyText"] == (
        "Confidential exact approval body"
    )
    redacted = f"{repr(action)} {repr(approval)} {repr(approval.review_preview)}".casefold()
    assert "confidential exact approval body" not in redacted
    assert "exact approval subject" not in redacted
    serialized = f"{action.public()} {repr(action)} {repr(approval)}".casefold()
    for forbidden in (
        "provider-secret",
        "raw message body",
        "credential material",
        "customer calendar content",
        "access_token",
        "refresh_token",
    ):
        assert forbidden not in serialized
    serialized_preview = asdict(approval.review_preview)
    assert "provider_request" not in serialized_preview
    assert "authoritative_event" not in serialized_preview
    assert serialized_preview["request_target_binding_sha256"] == (
        mail_provider_request().target_binding_sha256
    )
    assert serialized_preview["request_target_binding_sha256"] != mail_parameters_sha256()


def test_public_approval_bindings_are_keyed_commitments_not_plaintext_digests():
    provider_request = mail_provider_request()
    parameters = approval_execution_parameters_sha256(
        action=ConnectorActionKind.MAIL_SEND,
        provider_request=provider_request,
        payload_commitment_sha256=SHA_B,
    )
    alternate = approval_execution_parameters_sha256(
        action=ConnectorActionKind.MAIL_SEND,
        provider_request=provider_request,
        payload_commitment_sha256=SHA_D,
    )

    assert parameters == SHA_B
    assert alternate == SHA_D
    assert parameters != provider_request.target_binding_sha256
    assert mail_preview_sha256() == SHA_C


def test_review_preview_uses_utf8_byte_limits_not_unicode_code_points():
    with pytest.raises(ValueError, match="approval preview text is invalid"):
        replace(mail_review_payload(), body_text="\U0001f600" * 30_000)
    with pytest.raises(ValueError, match="approval preview text is invalid"):
        replace(mail_review_payload(), body_text="\ud800")


def test_review_preview_digest_rejects_action_payload_substitution():
    record = pending_approval()
    tampered_payload = replace(
        mail_review_payload(),
        body_text="Substituted body that was never reviewed",
    )
    with pytest.raises(ValueError, match="derived from the provider request"):
        ConnectedApprovalReviewPreview(
            approval_binding_sha256=SHA_A,
            parameters_sha256=mail_parameters_sha256(),
            preview_sha256=record.preview_sha256,
            payload=tampered_payload,
            connection_id=CONNECTION,
            action=ConnectorActionKind.MAIL_SEND,
            resource_version_sha256=None,
            provider_request=mail_provider_request(),
        )


def test_calendar_review_preview_is_action_specific_and_crypto_bound():
    provider_request = CalendarCreateRequest.build(
        EventSpec(
            calendar_id="work-calendar",
            title="Planning session",
            starts_at=datetime(2026, 11, 9, 14, 0, tzinfo=ZoneInfo("America/New_York")),
            ends_at=datetime(2026, 11, 9, 14, 30, tzinfo=ZoneInfo("America/New_York")),
            time_zone="America/New_York",
            attendees=("attendee@example.com",),
            location="Online",
            description="Review the release plan.",
        )
    )
    payload = ConnectedCalendarReviewPayload(
        calendar="work-calendar",
        event_context=None,
        title="Planning session",
        start="2026-11-09T14:00:00-05:00",
        end="2026-11-09T14:30:00-05:00",
        time_zone="America/New_York",
        attendees=("attendee@example.com",),
        location="Online",
        description="Review the release plan.",
    )
    parameters_sha256 = approval_execution_parameters_sha256(
        action=ConnectorActionKind.CALENDAR_CREATE,
        provider_request=provider_request,
        payload_commitment_sha256=SHA_B,
    )
    preview_sha256 = approval_review_preview_sha256(
        approval_id=APPROVAL,
        action_id=ACTION,
        action=ConnectorActionKind.CALENDAR_CREATE,
        approval_binding_sha256=SHA_A,
        parameters_sha256=parameters_sha256,
        resource_version_sha256=None,
        payload=payload,
        preview_commitment_sha256=SHA_C,
    )
    record = replace(
        pending_approval(),
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        parameters_sha256=parameters_sha256,
        resource_version_sha256=None,
        preview_sha256=preview_sha256,
        review_preview=ConnectedApprovalReviewPreview(
            approval_binding_sha256=SHA_A,
            parameters_sha256=parameters_sha256,
            preview_sha256=preview_sha256,
            payload=payload,
            connection_id=CONNECTION,
            action=ConnectorActionKind.CALENDAR_CREATE,
            resource_version_sha256=None,
            provider_request=provider_request,
        ),
    )
    assert record.public()["reviewPreview"]["payload"]["timeZone"] == ("America/New_York")

    invalid_payload = replace(payload, event_context="existing-event")
    invalid_digest = approval_review_preview_sha256(
        approval_id=APPROVAL,
        action_id=ACTION,
        action=ConnectorActionKind.CALENDAR_CREATE,
        approval_binding_sha256=SHA_A,
        parameters_sha256=parameters_sha256,
        resource_version_sha256=None,
        payload=invalid_payload,
        preview_commitment_sha256=SHA_D,
    )
    with pytest.raises(ValueError, match="derived from the provider request"):
        replace(
            record,
            preview_sha256=invalid_digest,
            review_preview=ConnectedApprovalReviewPreview(
                approval_binding_sha256=SHA_A,
                parameters_sha256=parameters_sha256,
                preview_sha256=invalid_digest,
                payload=invalid_payload,
                connection_id=CONNECTION,
                action=ConnectorActionKind.CALENDAR_CREATE,
                resource_version_sha256=None,
                provider_request=provider_request,
            ),
        )


def test_calendar_cancel_preview_requires_exact_authoritative_event_snapshot():
    version = "event-version-1"
    provider_request = CalendarCancelRequest.build(
        calendar_id="work-calendar",
        event_id="event-123",
        expected_resource_version=version,
    )
    snapshot = EventSnapshot(
        event_id="event-123",
        calendar_id="work-calendar",
        resource_version=version,
        starts_at=datetime(2026, 11, 9, 14, 0, tzinfo=ZoneInfo("America/New_York")),
        ends_at=datetime(2026, 11, 9, 14, 30, tzinfo=ZoneInfo("America/New_York")),
        time_zone="America/New_York",
        title="Planning session",
        attendees=("attendee@example.com",),
        location="Online",
        description="Review the release plan.",
    )
    payload = ConnectedCalendarReviewPayload(
        calendar="work-calendar",
        event_context="event-123",
        title="Planning session",
        start="2026-11-09T14:00:00-05:00",
        end="2026-11-09T14:30:00-05:00",
        time_zone="America/New_York",
        attendees=("attendee@example.com",),
        location="Online",
        description="Review the release plan.",
    )
    parameters_sha256 = approval_execution_parameters_sha256(
        action=ConnectorActionKind.CALENDAR_CANCEL,
        provider_request=provider_request,
        payload_commitment_sha256=SHA_C,
    )
    resource_version_sha256 = hashlib.sha256(version.encode()).hexdigest()
    preview = ConnectedApprovalReviewPreview(
        approval_binding_sha256=SHA_A,
        parameters_sha256=parameters_sha256,
        preview_sha256=SHA_B,
        payload=payload,
        connection_id=CONNECTION,
        action=ConnectorActionKind.CALENDAR_CANCEL,
        resource_version_sha256=resource_version_sha256,
        provider_request=provider_request,
        authoritative_event=snapshot,
    )
    serialized = asdict(preview)
    assert "provider_request" not in serialized
    assert "authoritative_event" not in serialized
    with pytest.raises(ValueError, match="not authoritative"):
        ConnectedApprovalReviewPreview(
            approval_binding_sha256=SHA_A,
            parameters_sha256=parameters_sha256,
            preview_sha256=SHA_B,
            payload=replace(payload, title="Different benign event"),
            connection_id=CONNECTION,
            action=ConnectorActionKind.CALENDAR_CANCEL,
            resource_version_sha256=resource_version_sha256,
            provider_request=provider_request,
            authoritative_event=snapshot,
        )
