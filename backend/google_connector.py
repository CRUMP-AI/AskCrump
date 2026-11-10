"""Google connector for Gmail and Google Calendar.

This is the provider implementation behind the ``google`` entries in
the capability registry. It speaks to Google's REST endpoints directly
with httpx, keeps the requested scopes to the minimal separable set in
the registry, and reads access tokens only through the token vault.

Account binding: a user can connect more than one Google account, and
every execution binds to ONE specific connection before it runs. If
the run names a connection (``connectionId`` / ``accountEmail`` in its
payload), that connection binds; otherwise the user's default
connection binds. The schema carries no stored default marker, so the
default is a deterministic order over the connection rows: earliest
connected first, tie-broken by connection id. Scopes are evaluated
against the bound connection alone — never unioned across the user's
connections — and the access token handed to a provider call always
comes from that same bound row, so a grant held by one account can
never authorize a call made with another account's token.

Scope note: the connect flow requests the read set by default --
``gmail.readonly`` and ``calendar.readonly`` -- and the default
authorization URL is unchanged. Write access is a separate, explicit
step-up: a connect request with ``level=write`` builds the
authorization URL from ``WRITE_SCOPES`` (the read set plus
``gmail.compose`` for drafts, ``gmail.send`` for sends, and
``calendar.events``, which ``calendar.create`` is registered with).
The requested level is bound into the HMAC-signed state, so a state
minted for one level cannot be replayed for the other. The stored
connection records the scopes Google actually granted in the token
response, never the scopes that were requested. Drafting and sending
run behind the approval flow: the run service freezes the exact
payload on an approval card before any adapter executes it.

Token lifecycle: access tokens are short-lived, so the bound-token
path refreshes them. When the bound connection's stored token is
expired (or inside the refresh skew), the stored refresh token is
exchanged at Google's token endpoint and the new access token is
persisted back through the vault in the same stored format; a
rotated refresh token is persisted when Google returns one, and the
stored refresh token is kept when it does not. A failed refresh
(revoked grant, ``invalid_grant``, network error) raises
``CONNECTION_REQUIRED`` so the user reconnects — an expired token is
never handed to a provider call. Refresh is single-flight per
connection within a connector instance: concurrent callers wait on
one exchange, then re-read the stored row and reuse the fresh token.
Disconnect revokes the grant at Google first (the stored refresh
token, which revokes the grant, falling back to the access token)
and then clears the local row exactly as before; a failed revocation
never blocks the local disconnect, and the outcome is reported on
the returned status instead of being claimed as revoked.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode
import uuid

import httpx

from . import agent_registry
from .config import Settings
from .db import eq
from .google_vault import GoogleVault

logger = logging.getLogger('askcrump.google_connector')

GOOGLE_AUTHORIZATION_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
GMAIL_BASE_URL = 'https://gmail.googleapis.com/gmail/v1/users/me'
CALENDAR_BASE_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary'

STATE_TTL_SECONDS = 600

# A stored access token counts as expired once its remaining lifetime
# drops to this skew, so a token never dies mid-request.
TOKEN_REFRESH_SKEW_SECONDS = 60

CONNECT_LEVELS = frozenset({'read', 'write'})


class GoogleConnectorError(RuntimeError):
    def __init__(self, message: str, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ConnectionRequiredError(GoogleConnectorError):
    def __init__(self, message: str = 'Connect Google to use this capability.') -> None:
        super().__init__(message, 'CONNECTION_REQUIRED', 409)


class InsufficientScopeError(GoogleConnectorError):
    def __init__(
        self,
        message: str = (
            'Google has not granted the permission this action needs. '
            'Reconnect Google and approve the requested access.'
        ),
    ) -> None:
        super().__init__(message, 'INSUFFICIENT_SCOPE', 403)


def _normalize_level(level: str | None) -> str:
    normalized = str(level or 'read')
    if normalized not in CONNECT_LEVELS:
        raise GoogleConnectorError(
            'The connection level is invalid.',
            'INVALID_CONNECT_LEVEL',
            400,
        )
    return normalized


def _connection_order_key(row: dict[str, Any]) -> tuple[str, str, str]:
    """Total, deterministic order over a user's connection rows.

    Earliest connected first; ties break by connection id, then by
    account email, so the same set of rows always orders the same way
    regardless of the order the store returned them in. This ordering
    is the default-binding rule until the schema grows a stored
    default-connection marker.
    """
    return (
        str(row.get('created_at') or ''),
        str(row.get('id') or ''),
        str(row.get('account_email') or ''),
    )


def binding_selectors(payload: Any) -> dict[str, str | None]:
    """Extract the connection a run payload names, if it names one.

    ``connectionId`` wins over ``accountEmail``; the snake_case
    spellings are accepted the way other payload fields are. No
    selector means the run binds the user's default connection.
    """
    selectors: dict[str, str | None] = {
        'connection_id': None,
        'account_email': None,
    }
    if not isinstance(payload, dict):
        return selectors
    connection_id = payload.get('connectionId') or payload.get('connection_id')
    if connection_id:
        selectors['connection_id'] = str(connection_id).strip() or None
    account_email = payload.get('accountEmail') or payload.get('account_email')
    if account_email:
        selectors['account_email'] = str(account_email).strip() or None
    return selectors


def check_granted_scopes(
    connection: dict[str, Any], required_scopes: tuple[str, ...]
) -> None:
    """Fail when the bound connection's own grant lacks a scope.

    Only the bound connection's recorded scopes are consulted — never
    a union across the user's connections. A record with no scope
    information leaves the grant unknown: the check passes and the
    provider call runs, where a Google 403 ``insufficientPermissions``
    response maps to the same ``INSUFFICIENT_SCOPE`` code (the
    attempt-and-map path the connector has always had).
    """
    granted = {str(scope) for scope in connection.get('scopes') or []}
    if not granted:
        return
    missing = [scope for scope in required_scopes if scope not in granted]
    if missing:
        raise InsufficientScopeError(
            'Google has not granted the permission this action needs '
            f"({' '.join(missing)}). Reconnect Google and approve the "
            'requested access.'
        )


def _parse_token_expiry(value: Any) -> datetime | None:
    """Parse a stored ``token_expires_at`` into an aware datetime.

    Rows written before expiry was recorded, or with an unparseable
    value, return None and are treated as carrying no known expiry:
    the stored token is used as-is, as it was before refresh existed.
    """
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _token_needs_refresh(connection: dict[str, Any]) -> bool:
    expiry = _parse_token_expiry(connection.get('token_expires_at'))
    if expiry is None:
        return False
    deadline = datetime.now(timezone.utc) + timedelta(
        seconds=TOKEN_REFRESH_SKEW_SECONDS
    )
    return expiry <= deadline


def _scope_union(capability_ids: tuple[str, ...]) -> tuple[str, ...]:
    scopes: list[str] = []
    for capability_id in capability_ids:
        item = agent_registry.get_capability(capability_id)
        if item is None:
            continue
        for scope in item.required_scopes:
            if scope not in scopes:
                scopes.append(scope)
    return tuple(scopes)


READ_SCOPES = _scope_union(('gmail.search', 'calendar.list'))
GMAIL_WRITE_SCOPES = _scope_union(('gmail.draft', 'gmail.send'))
WRITE_SCOPES = _scope_union(
    ('gmail.search', 'calendar.list', 'calendar.create', 'gmail.draft', 'gmail.send')
)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def build_raw_message(*, to: str, subject: str, body: str) -> str:
    """Build an RFC 5322 message and base64url-encode it for Gmail.

    The Gmail API takes the whole message as one base64url string in
    the ``raw`` field. Header values reject CR/LF outright so a
    payload can never smuggle extra headers into the message.
    """
    for value in (to, subject):
        if '\r' in str(value) or '\n' in str(value):
            raise GoogleConnectorError(
                'The email headers are invalid.',
                'INVALID_MESSAGE',
                400,
            )
    message = EmailMessage()
    message['To'] = str(to)
    message['Subject'] = str(subject)
    message.set_content(str(body))
    return _b64encode(message.as_bytes())


def _header_map(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get('payload') or {}
    headers: dict[str, str] = {}
    for item in payload.get('headers') or []:
        name = str(item.get('name') or '').lower()
        if name:
            headers[name] = str(item.get('value') or '')
    return headers


def message_summary(message: dict[str, Any]) -> dict[str, Any]:
    headers = _header_map(message)
    return {
        'id': str(message.get('id') or ''),
        'from': headers.get('from', ''),
        'subject': headers.get('subject', ''),
        'snippet': str(message.get('snippet') or ''),
        'date': headers.get('date', ''),
    }


def event_summary(event: dict[str, Any]) -> dict[str, Any]:
    start = event.get('start') or {}
    end = event.get('end') or {}
    attendees = [
        str(item.get('email') or '')
        for item in event.get('attendees') or []
        if isinstance(item, dict) and item.get('email')
    ]
    return {
        'id': str(event.get('id') or ''),
        'summary': str(event.get('summary') or ''),
        'start': start.get('dateTime') or start.get('date') or '',
        'end': end.get('dateTime') or end.get('date') or '',
        'location': str(event.get('location') or ''),
        'attendees': attendees,
    }


class GoogleConnector:
    """OAuth, connection storage, and Gmail/Calendar provider calls."""

    def __init__(
        self,
        settings: Settings,
        db: Any | None = None,
        vault: GoogleVault | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.vault = vault if vault is not None else GoogleVault()
        self._client = http_client
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    @property
    def oauth_configured(self) -> bool:
        return bool(
            self.settings.google_oauth_client_id
            and self.settings.google_oauth_client_secret
            and self.settings.google_oauth_redirect_uri
        )

    @property
    def configured(self) -> bool:
        return self.oauth_configured and self.vault.configured

    # -- Signed state --------------------------------------------------

    def _sign(self, payload_part: str) -> str:
        secret = str(self.settings.google_oauth_client_secret or '').encode('utf-8')
        digest = hmac.new(secret, payload_part.encode('ascii'), hashlib.sha256).digest()
        return _b64encode(digest)

    def make_state(self, user_id: str, level: str = 'read') -> str:
        payload = {
            'uid': str(user_id),
            'level': _normalize_level(level),
            'nonce': uuid.uuid4().hex,
            'exp': int(time.time()) + STATE_TTL_SECONDS,
        }
        part = _b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        return f'{part}.{self._sign(part)}'

    def validate_state(
        self, state: str, user_id: str, *, expected_level: str | None = None
    ) -> dict[str, Any]:
        try:
            part, signature = str(state or '').split('.', 1)
            payload = json.loads(_b64decode(part).decode('utf-8'))
        except Exception as exc:
            raise GoogleConnectorError(
                'The sign-in link is invalid. Start the connection again.',
                'GOOGLE_STATE_INVALID',
            ) from exc
        if not hmac.compare_digest(signature, self._sign(part)):
            raise GoogleConnectorError(
                'The sign-in link is invalid. Start the connection again.',
                'GOOGLE_STATE_INVALID',
            )
        if str(payload.get('uid') or '') != str(user_id):
            raise GoogleConnectorError(
                'The sign-in link does not match this account.',
                'GOOGLE_STATE_INVALID',
            )
        if int(payload.get('exp') or 0) < int(time.time()):
            raise GoogleConnectorError(
                'The sign-in link has expired. Start the connection again.',
                'GOOGLE_STATE_INVALID',
            )
        # The level lives inside the signed payload, so it cannot be
        # changed without breaking the signature above. States minted
        # before levels existed carry no level; those were read
        # connects, so they validate as read and nothing else.
        level = str(payload.get('level') or 'read')
        if level not in CONNECT_LEVELS:
            raise GoogleConnectorError(
                'The sign-in link is invalid. Start the connection again.',
                'GOOGLE_STATE_INVALID',
            )
        if expected_level is not None and level != _normalize_level(expected_level):
            raise GoogleConnectorError(
                'The sign-in link does not match the requested access '
                'level. Start the connection again.',
                'GOOGLE_STATE_INVALID',
            )
        payload['level'] = level
        return payload

    def state_user_id(self, state: str) -> str:
        try:
            part, _signature = str(state or '').split('.', 1)
            payload = json.loads(_b64decode(part).decode('utf-8'))
        except Exception as exc:
            raise GoogleConnectorError(
                'The sign-in link is invalid. Start the connection again.',
                'GOOGLE_STATE_INVALID',
            ) from exc
        user_id = str(payload.get('uid') or '')
        # The callback carries no session, so the full signed check runs
        # against the user id recovered from the state payload itself.
        self.validate_state(state, user_id)
        return user_id

    # -- OAuth ---------------------------------------------------------

    def authorization_url(
        self,
        user_id: str,
        scopes: tuple[str, ...] | None = None,
        *,
        level: str | None = None,
    ) -> str:
        if not self.oauth_configured:
            raise GoogleConnectorError(
                'Google connections are not configured yet.',
                'GOOGLE_NOT_CONFIGURED',
                503,
            )
        if not self.vault.configured:
            raise GoogleConnectorError(
                'Google token storage is not configured yet.',
                'GOOGLE_VAULT_NOT_CONFIGURED',
                503,
            )
        if scopes is not None:
            requested = tuple(scopes)
        elif _normalize_level(level) == 'write':
            requested = WRITE_SCOPES
        else:
            requested = READ_SCOPES
        if level is not None:
            bound_level = _normalize_level(level)
        elif scopes is not None:
            bound_level = 'write' if set(requested) - set(READ_SCOPES) else 'read'
        else:
            bound_level = 'read'
        params = {
            'client_id': self.settings.google_oauth_client_id,
            'redirect_uri': self.settings.google_oauth_redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(requested),
            'access_type': 'offline',
            'prompt': 'consent',
            'include_granted_scopes': 'true',
            'state': self.make_state(user_id, bound_level),
        }
        return f'{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}'

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.request(
                method, url, headers=headers, params=params, data=data, json=json_body
            )
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code >= 400:
            detail = ''
            try:
                detail = response.text or ''
            except Exception:
                detail = ''
            if response.status_code == 403 and 'insufficientPermissions' in detail:
                raise InsufficientScopeError()
            raise GoogleConnectorError(
                'Google did not complete that request.',
                'GOOGLE_API_ERROR',
                502,
            )
        if not response.content:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def exchange_code(
        self,
        code: str,
        *,
        user_id: str,
        state: str,
        expected_level: str | None = None,
    ) -> dict[str, Any]:
        if not self.oauth_configured:
            raise GoogleConnectorError(
                'Google connections are not configured yet.',
                'GOOGLE_NOT_CONFIGURED',
                503,
            )
        self.validate_state(state, user_id, expected_level=expected_level)
        token_payload = await self._request(
            'POST',
            GOOGLE_TOKEN_URL,
            data={
                'code': str(code or ''),
                'client_id': self.settings.google_oauth_client_id,
                'client_secret': self.settings.google_oauth_client_secret,
                'redirect_uri': self.settings.google_oauth_redirect_uri,
                'grant_type': 'authorization_code',
            },
        )
        access_token = str(token_payload.get('access_token') or '')
        if not access_token:
            raise GoogleConnectorError(
                'Google did not return an access token.',
                'GOOGLE_API_ERROR',
                502,
            )
        profile = await self._request(
            'GET',
            f'{GMAIL_BASE_URL}/profile',
            headers={'Authorization': f'Bearer {access_token}'},
        )
        account_email = str(profile.get('emailAddress') or '').strip().lower()
        if not account_email:
            raise GoogleConnectorError(
                'Google did not return the connected account.',
                'GOOGLE_API_ERROR',
                502,
            )
        # Store what Google granted, not what was requested: the
        # token response's scope field is the granted set, which can
        # be a subset of the request. A token response with no scope
        # field leaves the grant unknown, so store no scopes rather
        # than assuming a set was granted.
        scopes = tuple(
            str(item) for item in str(token_payload.get('scope') or '').split() if item
        )
        expires_in = int(token_payload.get('expires_in') or 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        connection = await self._store_connection(
            user_id=user_id,
            account_email=account_email,
            scopes=scopes,
            access_token=access_token,
            refresh_token=str(token_payload.get('refresh_token') or ''),
            token_expires_at=expires_at,
        )
        return connection

    async def _store_connection(
        self,
        *,
        user_id: str,
        account_email: str,
        scopes: tuple[str, ...],
        access_token: str,
        refresh_token: str,
        token_expires_at: datetime,
    ) -> dict[str, Any]:
        if self.db is None:
            raise GoogleConnectorError(
                'Connection storage is not available.',
                'GOOGLE_NOT_CONFIGURED',
                503,
            )
        payload: dict[str, Any] = {
            'user_id': str(user_id),
            'provider': 'google',
            'account_email': account_email,
            'scopes': list(scopes),
            'access_token_ciphertext': self.vault.encrypt(access_token),
            'refresh_token_ciphertext': (
                self.vault.encrypt(refresh_token) if refresh_token else ''
            ),
            'token_expires_at': token_expires_at.isoformat(),
            'status': 'connected',
        }
        if hasattr(self.db, 'upsert'):
            rows = await self.db.upsert(
                'agent_connections', payload, on_conflict='user_id,provider,account_email'
            )
            row = rows[0] if isinstance(rows, list) and rows else payload
        else:
            existing = await self.db.select_one(
                'agent_connections',
                filters={
                    'user_id': eq(user_id),
                    'provider': eq('google'),
                    'account_email': eq(account_email),
                },
            )
            if existing:
                rows = await self.db.update(
                    'agent_connections',
                    payload,
                    filters={'id': eq(existing['id'])},
                )
                row = rows[0] if isinstance(rows, list) and rows else payload
            else:
                rows = await self.db.insert('agent_connections', payload)
                row = rows[0] if isinstance(rows, list) and rows else payload
        return {
            'email': account_email,
            'scopes': list(scopes),
            'status': 'connected',
            'id': row.get('id') if isinstance(row, dict) else None,
        }

    # -- Connection state ----------------------------------------------

    async def list_connections(self, user_id: str) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        rows = await self.db.select(
            'agent_connections',
            filters={'user_id': eq(user_id), 'provider': eq('google')},
        )
        return rows or []

    async def status(self, user_id: str) -> dict[str, Any]:
        rows = await self.list_connections(user_id)
        accounts = [
            {
                'email': str(row.get('account_email') or ''),
                'scopes': list(row.get('scopes') or []),
                'status': str(row.get('status') or ''),
            }
            for row in rows
        ]
        return {
            'connected': any(item['status'] == 'connected' for item in accounts),
            'accounts': accounts,
        }

    async def _revoke_stored_token(
        self, row: dict[str, Any]
    ) -> dict[str, Any]:
        """Ask Google to revoke one connection's grant.

        The refresh token is preferred because revoking it revokes
        the whole grant; the access token is the fallback. This never
        raises: the outcome is reported to the caller so a failed
        revocation is surfaced honestly instead of being claimed.
        """
        token = ''
        had_ciphertext = False
        for field in ('refresh_token_ciphertext', 'access_token_ciphertext'):
            ciphertext = str(row.get(field) or '')
            if not ciphertext:
                continue
            had_ciphertext = True
            try:
                token = self.vault.decrypt(ciphertext)
            except Exception:
                token = ''
            if token:
                break
        if not token:
            return {
                'attempted': False,
                'revoked': False,
                'error': 'stored_token_unavailable' if had_ciphertext else None,
            }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.request(
                'POST', GOOGLE_REVOKE_URL, data={'token': token}
            )
        except httpx.HTTPError:
            logger.warning(
                'Google token revocation request failed for connection %s',
                row.get('id'),
            )
            return {
                'attempted': True,
                'revoked': False,
                'error': 'revoke_request_failed',
            }
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code == 200:
            return {'attempted': True, 'revoked': True, 'error': None}
        logger.warning(
            'Google token revocation returned %s for connection %s',
            response.status_code,
            row.get('id'),
        )
        return {
            'attempted': True,
            'revoked': False,
            'error': f'revoke_http_{response.status_code}',
        }

    async def disconnect(
        self, user_id: str, account_email: str | None = None
    ) -> dict[str, Any]:
        if self.db is None:
            return {'connected': False, 'accounts': []}
        rows = await self.list_connections(user_id)
        revocations: list[dict[str, Any]] = []
        for row in rows:
            if account_email and str(row.get('account_email') or '') != account_email:
                continue
            # Revoke at Google before the local tokens are cleared —
            # afterwards there is nothing left to revoke with. A
            # failed revocation is recorded on the returned status
            # but never blocks the disconnect the user asked for.
            outcome = await self._revoke_stored_token(row)
            revocations.append(
                {'email': str(row.get('account_email') or ''), **outcome}
            )
            await self.db.update(
                'agent_connections',
                {
                    'status': 'revoked',
                    'access_token_ciphertext': '',
                    'refresh_token_ciphertext': '',
                    'token_expires_at': None,
                },
                filters={'id': eq(row['id'])},
            )
        status = await self.status(user_id)
        status['revocations'] = revocations
        return status

    # -- Connection binding --------------------------------------------
    #
    # Execution binds to ONE connection (see the module docstring for
    # the rule). A stored default marker would replace the ordering
    # rule below, not the contract: resolve once, check that row's
    # scopes, and use that row's token.

    async def bound_connection(
        self,
        user_id: str,
        *,
        connection_id: str | None = None,
        account_email: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the single connection an execution binds to.

        Only connected rows holding a token are eligible. An explicit
        selector that matches no eligible row fails with
        ``CONNECTION_REQUIRED`` — a run never silently falls back to a
        different account than the one it named.
        """
        rows = await self.list_connections(user_id)
        eligible = [
            row
            for row in rows
            if row.get('status') == 'connected'
            and str(row.get('access_token_ciphertext') or '')
        ]
        if connection_id:
            for row in eligible:
                if str(row.get('id') or '') == str(connection_id):
                    return row
            raise ConnectionRequiredError(
                'The Google account selected for this run is not connected.'
            )
        if account_email:
            wanted = str(account_email).strip().lower()
            for row in eligible:
                if str(row.get('account_email') or '').strip().lower() == wanted:
                    return row
            raise ConnectionRequiredError(
                'The Google account selected for this run is not connected.'
            )
        if not eligible:
            raise ConnectionRequiredError()
        return min(eligible, key=_connection_order_key)

    # -- Token refresh ---------------------------------------------------
    #
    # Refresh lives here, inside the bound-token path, so every caller
    # (executor adapters, read routes, the Today brief) inherits it and
    # it only ever operates on the bound connection.

    async def _reload_connection(
        self, connection: dict[str, Any]
    ) -> dict[str, Any]:
        """Re-read a connection row by id, falling back to the given row."""
        connection_id = str(connection.get('id') or '')
        if self.db is None or not connection_id:
            return connection
        try:
            if hasattr(self.db, 'select_one'):
                row = await self.db.select_one(
                    'agent_connections', filters={'id': eq(connection_id)}
                )
                if isinstance(row, dict) and row:
                    return row
            rows = await self.list_connections(
                str(connection.get('user_id') or '')
            )
            for row in rows:
                if str(row.get('id') or '') == connection_id:
                    return row
        except Exception:
            return connection
        return connection

    async def _exchange_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token at Google's token endpoint.

        Every failure — a revoked grant (``invalid_grant``), any other
        error response, or a network error — becomes
        ``CONNECTION_REQUIRED``: the grant is gone or unreachable, the
        user must reconnect, and the expired access token is never
        used as a fallback.
        """
        if not self.oauth_configured:
            raise ConnectionRequiredError(
                'Your Google connection has expired. Reconnect Google.'
            )
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.request(
                'POST',
                GOOGLE_TOKEN_URL,
                data={
                    'client_id': self.settings.google_oauth_client_id,
                    'client_secret': self.settings.google_oauth_client_secret,
                    'refresh_token': refresh_token,
                    'grant_type': 'refresh_token',
                },
            )
        except httpx.HTTPError as exc:
            raise ConnectionRequiredError(
                'Your Google connection has expired. Reconnect Google.'
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code >= 400:
            raise ConnectionRequiredError(
                'Your Google connection has expired. Reconnect Google.'
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise ConnectionRequiredError(
                'Your Google connection has expired. Reconnect Google.'
            ) from exc
        if not isinstance(payload, dict) or not payload.get('access_token'):
            raise ConnectionRequiredError(
                'Your Google connection has expired. Reconnect Google.'
            )
        return payload

    async def _fresh_access_token(
        self, connection: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        """Return the bound connection's token, refreshing it if expired.

        A token with time left is returned with no token-endpoint
        call. An expired token is refreshed under a per-connection
        lock; after the lock is taken the stored row is re-read, so
        concurrent callers share one exchange and later callers reuse
        the token the first one persisted. Refreshed tokens are
        persisted through the vault in the existing stored format —
        the rotated refresh token when Google returns one, the stored
        refresh token otherwise.
        """
        if not _token_needs_refresh(connection):
            return connection, self.vault.decrypt(
                str(connection.get('access_token_ciphertext') or '')
            )
        lock_key = str(
            connection.get('id')
            or connection.get('account_email')
            or 'google'
        )
        lock = self._refresh_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            current = await self._reload_connection(connection)
            if str(current.get('status') or '') != 'connected':
                raise ConnectionRequiredError(
                    'The Google account selected for this run is not connected.'
                )
            if not _token_needs_refresh(current):
                return current, self.vault.decrypt(
                    str(current.get('access_token_ciphertext') or '')
                )
            refresh_token = self.vault.decrypt(
                str(current.get('refresh_token_ciphertext') or '')
            )
            if not refresh_token:
                raise ConnectionRequiredError(
                    'Your Google connection has expired. Reconnect Google.'
                )
            payload = await self._exchange_refresh_token(refresh_token)
            access_token = str(payload.get('access_token') or '')
            try:
                expires_in = int(payload.get('expires_in') or 3600)
            except (TypeError, ValueError):
                expires_in = 3600
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=expires_in
            )
            rotated_refresh = str(payload.get('refresh_token') or '')
            update: dict[str, Any] = {
                'access_token_ciphertext': self.vault.encrypt(access_token),
                'token_expires_at': expires_at.isoformat(),
            }
            if rotated_refresh:
                update['refresh_token_ciphertext'] = self.vault.encrypt(
                    rotated_refresh
                )
            if self.db is not None and current.get('id'):
                await self.db.update(
                    'agent_connections',
                    update,
                    filters={'id': eq(current['id'])},
                )
            refreshed = {**current, **update}
            return refreshed, access_token

    async def bound_access_token(
        self,
        user_id: str,
        *,
        connection_id: str | None = None,
        account_email: str | None = None,
        required_scopes: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], str]:
        """Resolve the bound connection, check ITS scopes, return its token.

        The scope check and the token come from the same resolved row,
        with no re-selection in between, so a grant held by a different
        connection can never authorize a call made with this
        connection's token. An expired bound token is refreshed first
        (see ``_fresh_access_token``); the returned token is always
        the bound connection's own.
        """
        connection = await self.bound_connection(
            user_id, connection_id=connection_id, account_email=account_email
        )
        check_granted_scopes(connection, required_scopes)
        return await self._fresh_access_token(connection)

    async def access_token_for(
        self,
        user_id: str,
        account_email: str | None = None,
        *,
        connection_id: str | None = None,
    ) -> str:
        _connection, token = await self.bound_access_token(
            user_id, connection_id=connection_id, account_email=account_email
        )
        return token

    # -- Provider calls --------------------------------------------------

    def _auth_headers(self, access_token: str) -> dict[str, str]:
        return {'Authorization': f'Bearer {access_token}'}

    async def search_messages(
        self, access_token: str, query: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        listing = await self._request(
            'GET',
            f'{GMAIL_BASE_URL}/messages',
            headers=self._auth_headers(access_token),
            params={'q': query, 'maxResults': max(1, min(int(max_results), 50))},
        )
        summaries: list[dict[str, Any]] = []
        for item in listing.get('messages') or []:
            message_id = str(item.get('id') or '')
            if not message_id:
                continue
            summaries.append(await self.get_message(access_token, message_id))
        return summaries

    async def get_message(
        self, access_token: str, message_id: str
    ) -> dict[str, Any]:
        message = await self._request(
            'GET',
            f'{GMAIL_BASE_URL}/messages/{message_id}',
            headers=self._auth_headers(access_token),
            params={
                'format': 'metadata',
                'metadataHeaders': ['From', 'Subject', 'Date'],
            },
        )
        return message_summary(message)

    async def list_events(
        self,
        access_token: str,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            'singleEvents': 'true',
            'orderBy': 'startTime',
            'maxResults': max(1, min(int(max_results), 250)),
        }
        if time_min:
            params['timeMin'] = time_min
        if time_max:
            params['timeMax'] = time_max
        payload = await self._request(
            'GET',
            f'{CALENDAR_BASE_URL}/events',
            headers=self._auth_headers(access_token),
            params=params,
        )
        return [event_summary(item) for item in payload.get('items') or []]

    async def create_event(
        self,
        access_token: str,
        *,
        summary: str,
        start: str,
        end: str,
        attendees: list[str] | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            'summary': str(summary or ''),
            'start': {'dateTime': start},
            'end': {'dateTime': end},
        }
        if attendees:
            body['attendees'] = [{'email': item} for item in attendees]
        if description:
            body['description'] = description
        if location:
            body['location'] = location
        created = await self._request(
            'POST',
            f'{CALENDAR_BASE_URL}/events',
            headers=self._auth_headers(access_token),
            json_body=body,
        )
        return event_summary(created)

    async def create_draft(
        self,
        user_id: str,
        *,
        to: str,
        subject: str,
        body: str,
        account_email: str | None = None,
        connection_id: str | None = None,
    ) -> dict[str, Any]:
        access_token = await self.access_token_for(
            user_id, account_email, connection_id=connection_id
        )
        return await self.create_draft_with_token(
            access_token, to=to, subject=subject, body=body
        )

    async def create_draft_with_token(
        self, access_token: str, *, to: str, subject: str, body: str
    ) -> dict[str, Any]:
        raw = build_raw_message(to=to, subject=subject, body=body)
        created = await self._request(
            'POST',
            f'{GMAIL_BASE_URL}/drafts',
            headers=self._auth_headers(access_token),
            json_body={'message': {'raw': raw}},
        )
        inner = created.get('message')
        inner = inner if isinstance(inner, dict) else {}
        return {
            'id': str(created.get('id') or ''),
            'messageId': str(inner.get('id') or ''),
            'threadId': str(inner.get('threadId') or ''),
        }

    async def send_message(
        self,
        user_id: str,
        *,
        to: str,
        subject: str,
        body: str,
        account_email: str | None = None,
        connection_id: str | None = None,
    ) -> dict[str, Any]:
        access_token = await self.access_token_for(
            user_id, account_email, connection_id=connection_id
        )
        return await self.send_message_with_token(
            access_token, to=to, subject=subject, body=body
        )

    async def send_message_with_token(
        self, access_token: str, *, to: str, subject: str, body: str
    ) -> dict[str, Any]:
        raw = build_raw_message(to=to, subject=subject, body=body)
        sent = await self._request(
            'POST',
            f'{GMAIL_BASE_URL}/messages/send',
            headers=self._auth_headers(access_token),
            json_body={'raw': raw},
        )
        return {
            'id': str(sent.get('id') or ''),
            'threadId': str(sent.get('threadId') or ''),
            'labelIds': [str(item) for item in sent.get('labelIds') or []],
        }
