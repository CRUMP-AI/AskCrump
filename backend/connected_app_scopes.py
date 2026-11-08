"""Least-privilege delegated scope plans for connected mail and calendars.

The catalog is data only.  It does not start OAuth, store credentials, or make
provider calls.  Persistent connection and scope-expansion actions are denied by
the policy kernel and are intentionally absent here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .connected_app_contracts import ConnectorAccountKind
from .connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    runtime_action_implemented,
)


class ProviderScopeClass(StrEnum):
    STANDARD = "standard"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class ProviderScopePlan:
    provider: ConnectorProvider
    actions: frozenset[ConnectorActionKind]
    delegated_scopes: tuple[str, ...]
    highest_scope_class: ProviderScopeClass


class ConnectedAppScopeError(ValueError):
    """The requested action set has no safe delegated scope plan."""


_GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"
_GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
_GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
_GMAIL_MODIFY = "https://www.googleapis.com/auth/gmail.modify"

_GCAL_FREE_BUSY = "https://www.googleapis.com/auth/calendar.events.freebusy"
_GCAL_OWNED_READ = (
    "https://www.googleapis.com/auth/calendar.events.owned.readonly"
)
_GCAL_OWNED_WRITE = "https://www.googleapis.com/auth/calendar.events.owned"

# Stable account identity is part of the credential/connection boundary, not
# an optional profile feature.  Google exposes the immutable OIDC ``sub`` only
# when identity scopes are requested; email is retained solely for the
# provider-side userinfo lookup and is immediately reduced to a one-way hash.
_GOOGLE_OPENID = "openid"
_GOOGLE_EMAIL = "email"

# Microsoft v2 issues a refresh token only when offline_access is explicitly
# requested.  Every connected-app grant is designed for revocable background
# work, so a Microsoft action plan without this protocol scope would silently
# degrade into a short-lived, non-autonomous connection.
_MICROSOFT_OFFLINE_ACCESS = "offline_access"
# Microsoft Graph's least-privileged delegated permission for /me, whose
# immutable id is reduced to the connection's external-account hash.
_MICROSOFT_USER_READ = "User.Read"

_GOOGLE_ACTION_SCOPES: dict[ConnectorActionKind, tuple[str, ...]] = {
    ConnectorActionKind.MAIL_SEARCH: (_GMAIL_READ,),
    ConnectorActionKind.MAIL_GET: (_GMAIL_READ,),
    # Every supported Gmail write is settled only after an authoritative full
    # body read.  gmail.compose can read drafts but cannot call messages.get;
    # gmail.send cannot read messages at all.  Keep explicit gmail.readonly
    # consent in each exact write plan so provider outcome proof is possible.
    ConnectorActionKind.MAIL_CREATE_DRAFT: (_GMAIL_COMPOSE, _GMAIL_READ),
    ConnectorActionKind.MAIL_SEND: (_GMAIL_READ, _GMAIL_SEND),
    ConnectorActionKind.MAIL_REPLY: (_GMAIL_READ, _GMAIL_SEND),
    ConnectorActionKind.MAIL_FORWARD: (_GMAIL_READ, _GMAIL_SEND),
    ConnectorActionKind.MAIL_LABEL: (_GMAIL_MODIFY,),
    ConnectorActionKind.MAIL_ARCHIVE: (_GMAIL_MODIFY,),
    ConnectorActionKind.MAIL_TRASH: (_GMAIL_MODIFY,),
    ConnectorActionKind.CALENDAR_LIST: (_GCAL_OWNED_READ,),
    ConnectorActionKind.CALENDAR_GET: (_GCAL_OWNED_READ,),
    ConnectorActionKind.CALENDAR_FREE_BUSY: (_GCAL_FREE_BUSY,),
    ConnectorActionKind.CALENDAR_CREATE: (_GCAL_OWNED_WRITE,),
    ConnectorActionKind.CALENDAR_UPDATE: (_GCAL_OWNED_WRITE,),
    ConnectorActionKind.CALENDAR_CANCEL: (_GCAL_OWNED_WRITE,),
    ConnectorActionKind.CALENDAR_DELETE: (_GCAL_OWNED_WRITE,),
}

_MICROSOFT_ACTION_SCOPES: dict[ConnectorActionKind, tuple[str, ...]] = {
    ConnectorActionKind.MAIL_SEARCH: ("Mail.Read",),
    ConnectorActionKind.MAIL_GET: ("Mail.Read",),
    ConnectorActionKind.MAIL_CREATE_DRAFT: ("Mail.ReadWrite",),
    # Graph's proof-capable send flow is create immutable draft -> send that
    # exact draft -> authoritative full readback in Sent Items.  Mail.Send does
    # not grant draft creation/readback, so both scopes are mandatory.  Reply
    # likewise uses createReply + draft PATCH before sending.
    ConnectorActionKind.MAIL_SEND: ("Mail.ReadWrite", "Mail.Send"),
    ConnectorActionKind.MAIL_REPLY: ("Mail.ReadWrite", "Mail.Send"),
    ConnectorActionKind.MAIL_FORWARD: ("Mail.Read", "Mail.Send"),
    ConnectorActionKind.MAIL_LABEL: ("Mail.ReadWrite",),
    ConnectorActionKind.MAIL_ARCHIVE: ("Mail.ReadWrite",),
    ConnectorActionKind.MAIL_TRASH: ("Mail.ReadWrite",),
    ConnectorActionKind.MAIL_DELETE_PERMANENT: ("Mail.ReadWrite",),
    ConnectorActionKind.CALENDAR_LIST: ("Calendars.Read",),
    ConnectorActionKind.CALENDAR_GET: ("Calendars.Read",),
    ConnectorActionKind.CALENDAR_FREE_BUSY: ("Calendars.ReadBasic",),
    ConnectorActionKind.CALENDAR_CREATE: ("Calendars.ReadWrite",),
    ConnectorActionKind.CALENDAR_UPDATE: ("Calendars.ReadWrite",),
    ConnectorActionKind.CALENDAR_CANCEL: ("Calendars.ReadWrite",),
    ConnectorActionKind.CALENDAR_DELETE: ("Calendars.ReadWrite",),
}

_PERSISTENT_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_CONNECT,
        ConnectorActionKind.MAIL_EXPAND_SCOPES,
        ConnectorActionKind.MAIL_REGISTER_WATCH,
        ConnectorActionKind.CALENDAR_CONNECT,
        ConnectorActionKind.CALENDAR_EXPAND_SCOPES,
        ConnectorActionKind.CALENDAR_REGISTER_WATCH,
    }
)


def _scope_class(provider: ConnectorProvider, scopes: set[str]) -> ProviderScopeClass:
    if provider is ConnectorProvider.MICROSOFT:
        return ProviderScopeClass.STANDARD
    if any(scope in {_GMAIL_READ, _GMAIL_COMPOSE, _GMAIL_MODIFY} for scope in scopes):
        return ProviderScopeClass.RESTRICTED
    if _GMAIL_SEND in scopes or scopes.intersection(
        {_GCAL_FREE_BUSY, _GCAL_OWNED_READ, _GCAL_OWNED_WRITE}
    ):
        return ProviderScopeClass.SENSITIVE
    return ProviderScopeClass.STANDARD


def delegated_scope_plan(
    provider: ConnectorProvider,
    actions: Iterable[ConnectorActionKind],
    *,
    account_kind: ConnectorAccountKind | None = None,
) -> ProviderScopePlan:
    """Return the exact delegated scope union for one bounded action set.

    Google permanent deletion is intentionally unsupported because its only
    Gmail scope also grants complete mailbox access and permanent deletion.
    OAuth connection, scope expansion, and persistent watches require a separate
    user-takeover flow and never receive a runtime tool scope plan.
    """

    if not isinstance(provider, ConnectorProvider):
        raise ConnectedAppScopeError("provider must be a ConnectorProvider")
    requested = frozenset(actions)
    if not requested or any(not isinstance(action, ConnectorActionKind) for action in requested):
        raise ConnectedAppScopeError("actions must contain ConnectorActionKind values")
    if requested & _PERSISTENT_ACTIONS:
        raise ConnectedAppScopeError("persistent permissions require user takeover")
    if any(not runtime_action_implemented(action) for action in requested):
        raise ConnectedAppScopeError("requested action is not implemented for runtime use")
    if (
        provider is ConnectorProvider.MICROSOFT
        and ConnectorActionKind.CALENDAR_FREE_BUSY in requested
        and account_kind is not ConnectorAccountKind.WORK_SCHOOL
    ):
        raise ConnectedAppScopeError(
            "Microsoft delegated free/busy requires a work or school account"
        )
    if (
        provider is ConnectorProvider.GOOGLE
        and ConnectorActionKind.MAIL_DELETE_PERMANENT in requested
    ):
        raise ConnectedAppScopeError("Google permanent mail deletion is unsupported")

    catalog = (
        _GOOGLE_ACTION_SCOPES
        if provider is ConnectorProvider.GOOGLE
        else _MICROSOFT_ACTION_SCOPES
    )
    missing = requested.difference(catalog)
    if missing:
        raise ConnectedAppScopeError("requested actions have no delegated scope plan")
    scopes = {scope for action in requested for scope in catalog[action]}
    if provider is ConnectorProvider.GOOGLE:
        scopes.update({_GOOGLE_OPENID, _GOOGLE_EMAIL})
    else:
        scopes.add(_MICROSOFT_OFFLINE_ACCESS)
        scopes.add(_MICROSOFT_USER_READ)
    return ProviderScopePlan(
        provider=provider,
        actions=requested,
        delegated_scopes=tuple(sorted(scopes)),
        highest_scope_class=_scope_class(provider, scopes),
    )


def scopes_cover(
    *,
    provider: ConnectorProvider,
    granted_scopes: Iterable[str],
    actions: Iterable[ConnectorActionKind],
    account_kind: ConnectorAccountKind | None = None,
) -> bool:
    """Fail closed unless the granted delegated scopes cover every action."""

    try:
        plan = delegated_scope_plan(
            provider,
            actions,
            account_kind=account_kind,
        )
    except ConnectedAppScopeError:
        return False
    granted = frozenset(str(scope) for scope in granted_scopes)
    return set(plan.delegated_scopes).issubset(granted)
