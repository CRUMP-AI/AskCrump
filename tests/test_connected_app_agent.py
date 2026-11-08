from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from backend.connected_app_agent import (
    ConnectedOperatorDisposition,
    ConnectedOperatorPlanningContext,
    ConnectedOperatorPlanError,
    ConnectedOperatorPlanner,
    connected_operator_candidate,
    connected_operator_schedule_candidate,
)
from backend.connected_app_contracts import ConnectionAuthorizationState, ConnectorAccountKind
from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider, ConnectorResource
from backend.connected_app_service import ConnectedConnectionView


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
CONNECTION = "00000000-0000-4000-8000-000000000001"
OWNER = "00000000-0000-4000-8000-000000000011"
SHA = "a" * 64


def test_candidate_gate_is_bounded_and_deterministic():
    assert connected_operator_candidate("Check my email for the appointment.") is True
    assert connected_operator_candidate("Help me improve this paragraph.") is False
    assert connected_operator_candidate(123) is False
    assert connected_operator_candidate("email " + "x" * 12_001) is False


@pytest.mark.parametrize(
    "message",
    (
        "Schedule lunch with Jane Tuesday at noon.",
        "What’s on my agenda tomorrow?",
        "Find the note from Jane about the budget.",
        "Draft a reply to the vendor.",
        "Send a note to the team.",
        "Invite Jane to lunch Tuesday.",
        "Set up lunch with Jane tomorrow.",
        "Cancel the appointment tomorrow.",
        "Move the meeting to 3 PM.",
        "Change the event location to Room 2.",
        "Delete the calendar event next Friday.",
        "Do I have any emails from Sarah?",
        "Any new emails?",
        "When am I free tomorrow?",
        "Set a meeting with Sarah tomorrow.",
        "Make an appointment with Sarah tomorrow.",
        "Add an event tomorrow at 2 PM.",
    ),
)
def test_candidate_gate_recognizes_natural_connected_operator_idioms(message):
    assert connected_operator_candidate(message) is True


@pytest.mark.parametrize(
    "message",
    (
        "Explain how cron scheduling works.",
        "Draft a project proposal.",
        "Send me a summary of this paragraph.",
        "Reply with JSON only.",
        "A calendar is a data structure.",
        "Write a note about this chapter.",
        "Cancel the database migration.",
        "Move the paragraph to the end.",
        "Change the event loop implementation.",
        "Delete this email.",
        "Do I have any email addresses in this spreadsheet?",
        "Any new email protocol changes?",
        "Set the meeting variable in this code tomorrow.",
        "Add an event loop example tomorrow.",
        "Make an appointment class in Python tomorrow.",
    ),
)
def test_candidate_gate_rejects_unrelated_action_word_false_positives(message):
    assert connected_operator_candidate(message) is False


def test_schedule_candidate_requires_both_recurrence_and_connected_intent():
    assert connected_operator_schedule_candidate("Every weekday check my inbox.") is True
    assert connected_operator_schedule_candidate("Check my inbox once.") is False
    assert connected_operator_schedule_candidate("Every weekday improve my paragraph.") is False


class Model:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[dict[str, object]] = []

    async def complete(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if isinstance(self.value, BaseException):
            raise self.value
        if isinstance(self.value, str):
            return self.value
        return json.dumps(self.value, separators=(",", ":"))


def connection(*actions: ConnectorActionKind) -> ConnectedConnectionView:
    return ConnectedConnectionView(
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=(
            ConnectorResource.CALENDAR
            if actions and actions[0].value.startswith("calendar.")
            else ConnectorResource.MAIL
        ),
        account_kind=ConnectorAccountKind.PERSONAL,
        granted_actions=tuple(actions),
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA,
        expires_at=NOW + timedelta(days=30),
        updated_at=NOW,
    )


def base(kind="action", action="mail.search", parameters=None, schedule=None, question=None):
    return {
        "kind": kind,
        "connectionId": CONNECTION if kind in {"action", "schedule"} else None,
        "action": action if kind in {"action", "schedule"} else None,
        "parameters": parameters if kind in {"action", "schedule"} else None,
        "schedule": schedule,
        "question": question,
    }


@pytest.mark.asyncio
async def test_unrelated_chat_never_calls_planning_model():
    model = Model(RuntimeError("must not run"))
    result = await ConnectedOperatorPlanner(model).plan(
        owner_id=OWNER,
        message="Help me improve this paragraph.",
        connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.NONE
    assert model.calls == []


@pytest.mark.asyncio
async def test_prepared_completion_can_be_parsed_repeatedly_without_second_model_call():
    model = Model(
        base(
            parameters={
                "query": "from:alex@example.com",
                "folderIds": ["inbox"],
                "after": None,
                "before": None,
                "limit": 10,
            }
        )
    )
    planner = ConnectedOperatorPlanner(model, now=lambda: NOW)
    prepared = planner.prepare(
        owner_id=OWNER,
        message="Check my email from Alex.",
        connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
        user_time_zone="America/New_York",
    )
    assert isinstance(prepared, ConnectedOperatorPlanningContext)
    assert model.calls == []
    raw = await planner.complete(prepared)
    first = planner.parse(prepared, raw)
    replay = planner.parse(prepared, raw)
    assert first.disposition is ConnectedOperatorDisposition.ACTION
    assert replay.plan == first.plan
    assert len(model.calls) == 1
    assert model.calls[0]["owner_id"] == OWNER


@pytest.mark.asyncio
async def test_missing_connection_returns_safe_clarification_without_model():
    model = Model(RuntimeError("must not run"))
    result = await ConnectedOperatorPlanner(model).plan(
        owner_id=OWNER,
        message="Check my inbox for the receipt.",
        connections=(),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.CLARIFY
    assert "Connect" in (result.question or "")
    assert model.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unavailable",
    (
        replace(
            connection(ConnectorActionKind.MAIL_SEARCH),
            authorization_state=ConnectionAuthorizationState.REVOKED,
        ),
        replace(
            connection(ConnectorActionKind.MAIL_SEARCH),
            expires_at=NOW,
        ),
    ),
)
async def test_revoked_or_expired_connection_is_never_offered_to_model(unavailable):
    model = Model(RuntimeError("must not run"))
    result = await ConnectedOperatorPlanner(model, now=lambda: NOW).plan(
        owner_id=OWNER,
        message="Check my inbox for the receipt.",
        connections=(unavailable,),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.CLARIFY
    assert model.calls == []


@pytest.mark.asyncio
async def test_mail_search_builds_typed_read_plan_and_redacts_repr():
    model = Model(
        base(
            parameters={
                "query": "receipt",
                "folderIds": ["inbox"],
                "after": "2026-11-01T00:00:00-04:00",
                "before": None,
                "limit": 10,
            }
        )
    )
    result = await ConnectedOperatorPlanner(model, now=lambda: NOW).plan(
        owner_id=OWNER,
        message="Check my email for a receipt from this week.",
        connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.ACTION
    assert result.plan is not None
    assert result.plan.action is ConnectorActionKind.MAIL_SEARCH
    assert result.plan.requires_approval is False
    assert result.plan.request.query.query == "receipt"
    assert "receipt" not in repr(result.plan)
    assert "userRequest" in model.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_send_is_only_a_policy_owned_approval_proposal():
    model = Model(
        base(
            action="mail.send",
            parameters={
                "to": ["person@example.com"],
                "cc": [],
                "bcc": [],
                "subject": "Meeting",
                "bodyText": "Can we meet tomorrow?",
                "replyToMessageId": None,
                "expectedResourceVersion": None,
            },
        )
    )
    result = await ConnectedOperatorPlanner(model).plan(
        owner_id=OWNER,
        message="Email person@example.com and ask to meet tomorrow.",
        connections=(connection(ConnectorActionKind.MAIL_SEND),),
        user_time_zone="America/New_York",
    )
    assert result.plan is not None and result.plan.requires_approval is True
    assert result.plan.request.spec.to == ("person@example.com",)
    assert "person@example.com" not in repr(result.plan)


@pytest.mark.asyncio
async def test_same_scope_sibling_action_is_not_substitutable():
    model = Model(
        base(
            action="mail.reply",
            parameters={
                "to": ["person@example.com"],
                "cc": [],
                "bcc": [],
                "subject": "Re: Meeting",
                "bodyText": "Yes",
                "replyToMessageId": "provider-message-1",
                "expectedResourceVersion": "etag-1",
            },
        )
    )
    with pytest.raises(ConnectedOperatorPlanError) as error:
        await ConnectedOperatorPlanner(model).plan(
            owner_id=OWNER,
            message="Reply to that email.",
            connections=(connection(ConnectorActionKind.MAIL_SEND),),
            user_time_zone="America/New_York",
        )
    assert error.value.code == "CONNECTED_OPERATOR_PLAN_UNAUTHORIZED"


@pytest.mark.asyncio
async def test_recurring_calendar_write_always_requires_fresh_per_run_approval():
    model = Model(
        base(
            kind="schedule",
            action="calendar.create",
            parameters={
                "calendarId": "primary",
                "title": "Office hours",
                "startsAt": "2026-11-09T09:00:00-05:00",
                "endsAt": "2026-11-09T10:00:00-05:00",
                "timeZone": "America/New_York",
                "description": "",
                "location": "",
                "attendees": [],
                "sourceEventId": None,
                "expectedResourceVersion": None,
            },
            schedule={
                "cadenceSeconds": 604800,
                "timeZone": "America/New_York",
                "quietStart": "22:00",
                "quietEnd": "07:00",
            },
        )
    )
    result = await ConnectedOperatorPlanner(model).plan(
        owner_id=OWNER,
        message="Every 168 hours, schedule office hours on my calendar.",
        connections=(connection(ConnectorActionKind.CALENDAR_CREATE),),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.SCHEDULE
    assert result.plan is not None and result.plan.schedule is not None
    assert result.plan.schedule.requires_approval_every_run is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "Every weekday check my inbox.",
        "Check my inbox daily.",
        "Check my inbox weekly.",
        "Check my inbox monthly.",
        "Every 24 hours at 9 AM check my inbox.",
        "Every 24 hours at noon check my inbox.",
        "Every 24 hours at midnight check my inbox.",
    ),
)
async def test_calendar_recurrence_clarifies_without_model_call(message):
    model = Model(RuntimeError("unsupported recurrence must not call the model"))
    result = await ConnectedOperatorPlanner(model).plan(
        owner_id=OWNER,
        message=message,
        connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.CLARIFY
    assert "fixed elapsed interval" in (result.question or "")
    assert model.calls == []


@pytest.mark.asyncio
async def test_model_cannot_change_the_explicit_fixed_interval():
    model = Model(
        base(
            kind="schedule",
            parameters={
                "query": "urgent",
                "folderIds": ["inbox"],
                "after": None,
                "before": None,
                "limit": 5,
            },
            schedule={
                "cadenceSeconds": 7200,
                "timeZone": "America/New_York",
                "quietStart": None,
                "quietEnd": None,
            },
        )
    )
    with pytest.raises(ConnectedOperatorPlanError) as error:
        await ConnectedOperatorPlanner(model).plan(
            owner_id=OWNER,
            message="Every 3 hours check my inbox.",
            connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
            user_time_zone="America/New_York",
        )
    assert error.value.code == "CONNECTED_OPERATOR_PLAN_UNAUTHORIZED"


@pytest.mark.asyncio
async def test_model_cannot_invent_a_schedule_without_explicit_recurrence():
    model = Model(
        base(
            kind="schedule",
            parameters={
                "query": "urgent",
                "folderIds": ["inbox"],
                "after": None,
                "before": None,
                "limit": 5,
            },
            schedule={
                "cadenceSeconds": 3600,
                "timeZone": "America/New_York",
                "quietStart": None,
                "quietEnd": None,
            },
        )
    )
    with pytest.raises(ConnectedOperatorPlanError) as error:
        await ConnectedOperatorPlanner(model).plan(
            owner_id=OWNER,
            message="Check my email now.",
            connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
            user_time_zone="America/New_York",
        )
    assert error.value.code == "CONNECTED_OPERATOR_PLAN_UNAUTHORIZED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    (
        '{"kind":"none","kind":"action","connectionId":null,"action":null,'
        '"parameters":null,"schedule":null,"question":null}',
        '{"kind":"none","connectionId":null,"action":null,"parameters":NaN,'
        '"schedule":null,"question":null}',
        '{"kind":"none","connectionId":null,"action":null,"parameters":null,'
        '"schedule":null,"question":null,"extra":true}',
        "```json\n{}\n```",
    ),
)
async def test_malformed_model_output_fails_closed(raw):
    with pytest.raises(ConnectedOperatorPlanError) as error:
        await ConnectedOperatorPlanner(Model(raw)).plan(
            owner_id=OWNER,
            message="Check my email.",
            connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
            user_time_zone="America/New_York",
        )
    assert error.value.code == "CONNECTED_OPERATOR_PLAN_INVALID"


@pytest.mark.asyncio
async def test_model_failure_is_content_free():
    with pytest.raises(ConnectedOperatorPlanError) as error:
        await ConnectedOperatorPlanner(Model(RuntimeError("sensitive provider content"))).plan(
            owner_id=OWNER,
            message="Check my email.",
            connections=(connection(ConnectorActionKind.MAIL_SEARCH),),
            user_time_zone="America/New_York",
        )
    assert error.value.code == "CONNECTED_OPERATOR_PLAN_INVALID"
    assert "sensitive" not in str(error.value)
