import pytest

from backend.connected_app_contracts import ConnectorAccountKind
from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider
from backend.connected_app_scopes import (
    ConnectedAppScopeError,
    ProviderScopeClass,
    delegated_scope_plan,
    scopes_cover,
)


def test_google_mail_read_and_send_are_incremental_and_exact():
    plan = delegated_scope_plan(
        ConnectorProvider.GOOGLE,
        {ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND},
    )

    assert plan.delegated_scopes == (
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "openid",
    )
    assert plan.highest_scope_class is ProviderScopeClass.RESTRICTED
    assert "https://mail.google.com/" not in plan.delegated_scopes


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (
            ConnectorActionKind.MAIL_CREATE_DRAFT,
            (
                "email",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.readonly",
                "openid",
            ),
        ),
        (
            ConnectorActionKind.MAIL_SEND,
            (
                "email",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "openid",
            ),
        ),
        (
            ConnectorActionKind.MAIL_REPLY,
            (
                "email",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "openid",
            ),
        ),
    ],
)
def test_google_mail_writes_include_exact_full_body_proof_consent(action, expected):
    plan = delegated_scope_plan(ConnectorProvider.GOOGLE, {action})

    assert plan.delegated_scopes == expected
    assert plan.highest_scope_class is ProviderScopeClass.RESTRICTED
    assert "https://mail.google.com/" not in plan.delegated_scopes
    assert "https://www.googleapis.com/auth/gmail.modify" not in plan.delegated_scopes
    assert not scopes_cover(
        provider=ConnectorProvider.GOOGLE,
        granted_scopes={scope for scope in expected if not scope.endswith("gmail.readonly")},
        actions={action},
    )
    assert scopes_cover(
        provider=ConnectorProvider.GOOGLE,
        granted_scopes=set(expected),
        actions={action},
    )


def test_google_free_busy_does_not_receive_event_body_or_write_scope():
    plan = delegated_scope_plan(
        ConnectorProvider.GOOGLE,
        {ConnectorActionKind.CALENDAR_FREE_BUSY},
    )

    assert plan.delegated_scopes == (
        "email",
        "https://www.googleapis.com/auth/calendar.events.freebusy",
        "openid",
    )
    assert plan.highest_scope_class is ProviderScopeClass.SENSITIVE


def test_google_owned_event_read_and_write_remain_narrow():
    read = delegated_scope_plan(
        ConnectorProvider.GOOGLE,
        {ConnectorActionKind.CALENDAR_LIST, ConnectorActionKind.CALENDAR_GET},
    )
    write = delegated_scope_plan(
        ConnectorProvider.GOOGLE,
        {ConnectorActionKind.CALENDAR_CREATE, ConnectorActionKind.CALENDAR_UPDATE},
    )

    assert read.delegated_scopes == (
        "email",
        "https://www.googleapis.com/auth/calendar.events.owned.readonly",
        "openid",
    )
    assert write.delegated_scopes == (
        "email",
        "https://www.googleapis.com/auth/calendar.events.owned",
        "openid",
    )
    assert read.highest_scope_class is ProviderScopeClass.SENSITIVE
    assert write.highest_scope_class is ProviderScopeClass.SENSITIVE


def test_google_permanent_mail_deletion_is_not_scopeable():
    with pytest.raises(ConnectedAppScopeError, match="not implemented"):
        delegated_scope_plan(
            ConnectorProvider.GOOGLE,
            {ConnectorActionKind.MAIL_DELETE_PERMANENT},
        )


@pytest.mark.parametrize(
    "action",
    [
        ConnectorActionKind.MAIL_CONNECT,
        ConnectorActionKind.MAIL_EXPAND_SCOPES,
        ConnectorActionKind.MAIL_REGISTER_WATCH,
        ConnectorActionKind.CALENDAR_CONNECT,
        ConnectorActionKind.CALENDAR_EXPAND_SCOPES,
        ConnectorActionKind.CALENDAR_REGISTER_WATCH,
    ],
)
def test_persistent_permissions_never_receive_runtime_scopes(action):
    with pytest.raises(ConnectedAppScopeError, match="user takeover"):
        delegated_scope_plan(ConnectorProvider.GOOGLE, {action})


def test_microsoft_send_and_reply_include_exact_draft_and_readback_consent():
    send = delegated_scope_plan(
        ConnectorProvider.MICROSOFT,
        {ConnectorActionKind.MAIL_SEND},
    )
    reply = delegated_scope_plan(
        ConnectorProvider.MICROSOFT,
        {ConnectorActionKind.MAIL_REPLY},
    )
    draft = delegated_scope_plan(
        ConnectorProvider.MICROSOFT,
        {ConnectorActionKind.MAIL_CREATE_DRAFT},
    )

    assert send.delegated_scopes == (
        "Mail.ReadWrite", "Mail.Send", "User.Read", "offline_access"
    )
    assert reply.delegated_scopes == (
        "Mail.ReadWrite", "Mail.Send", "User.Read", "offline_access"
    )
    assert draft.delegated_scopes == ("Mail.ReadWrite", "User.Read", "offline_access")
    assert not scopes_cover(
        provider=ConnectorProvider.MICROSOFT,
        granted_scopes={"Mail.Send"},
        actions={ConnectorActionKind.MAIL_SEND},
    )
    assert not scopes_cover(
        provider=ConnectorProvider.MICROSOFT,
        granted_scopes={"Mail.ReadWrite", "Mail.Send"},
        actions={ConnectorActionKind.MAIL_SEND},
    )
    assert scopes_cover(
        provider=ConnectorProvider.MICROSOFT,
        granted_scopes={"Mail.ReadWrite", "Mail.Send", "User.Read", "offline_access"},
        actions={ConnectorActionKind.MAIL_SEND},
    )


def test_scope_coverage_fails_closed_on_partial_grant():
    actions = {ConnectorActionKind.MAIL_REPLY}

    assert not scopes_cover(
        provider=ConnectorProvider.MICROSOFT,
        granted_scopes={"Mail.Send"},
        actions=actions,
    )
    assert scopes_cover(
        provider=ConnectorProvider.MICROSOFT,
        granted_scopes={"Mail.ReadWrite", "Mail.Send", "User.Read", "offline_access"},
        actions=actions,
    )


def test_microsoft_freebusy_is_work_school_only_and_uses_basic_scope():
    with pytest.raises(ConnectedAppScopeError, match="work or school"):
        delegated_scope_plan(
            ConnectorProvider.MICROSOFT,
            {ConnectorActionKind.CALENDAR_FREE_BUSY},
            account_kind=ConnectorAccountKind.PERSONAL,
        )

    plan = delegated_scope_plan(
        ConnectorProvider.MICROSOFT,
        {ConnectorActionKind.CALENDAR_FREE_BUSY},
        account_kind=ConnectorAccountKind.WORK_SCHOOL,
    )
    assert plan.delegated_scopes == ("Calendars.ReadBasic", "User.Read", "offline_access")
    assert not scopes_cover(
        provider=ConnectorProvider.MICROSOFT,
        account_kind=ConnectorAccountKind.PERSONAL,
        granted_scopes={"Calendars.ReadBasic", "User.Read", "offline_access"},
        actions={ConnectorActionKind.CALENDAR_FREE_BUSY},
    )


@pytest.mark.parametrize(
    "action",
    [
        ConnectorActionKind.MAIL_LIST,
        ConnectorActionKind.MAIL_FORWARD,
        ConnectorActionKind.MAIL_LABEL,
        ConnectorActionKind.MAIL_ARCHIVE,
        ConnectorActionKind.MAIL_TRASH,
        ConnectorActionKind.MAIL_DELETE_PERMANENT,
        ConnectorActionKind.CALENDAR_DELETE,
    ],
)
def test_unimplemented_actions_never_receive_runtime_scopes(action):
    with pytest.raises(ConnectedAppScopeError, match="not implemented"):
        delegated_scope_plan(ConnectorProvider.MICROSOFT, {action})
    assert not scopes_cover(
        provider=ConnectorProvider.MICROSOFT,
        granted_scopes={"Mail.ReadWrite", "Calendars.ReadWrite"},
        actions={action},
    )


def test_scope_plan_rejects_empty_or_untyped_actions():
    with pytest.raises(ConnectedAppScopeError):
        delegated_scope_plan(ConnectorProvider.GOOGLE, set())
    with pytest.raises(ConnectedAppScopeError):
        delegated_scope_plan(ConnectorProvider.GOOGLE, {"mail.get"})  # type: ignore[arg-type]
