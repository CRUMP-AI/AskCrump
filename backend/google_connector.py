"""Google connector for Gmail and Google Calendar.

This is the provider implementation behind the ``google`` entries in
the capability registry. It speaks to Google's REST endpoints directly
with httpx, keeps the requested scopes to the minimal separable set in
the registry, and reads access tokens only through the token vault.

Scope note: the connect flow requests the read set only --
``gmail.readonly`` and ``calendar.readonly`` -- and the default
authorization URL is unchanged. The write scopes are staged here as
constants for the Slice 2 write path: ``gmail.compose`` (drafts),
``gmail.send`` (sends), and ``calendar.events`` (``calendar.create``
is registered with it). They are not requested by the connect flow
in this change; a write-scope connect step lands once a production
OAuth client is in place. Drafting and sending run behind the
approval flow: the run service freezes the exact payload on an
approval card before any adapter executes it.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode
import uuid

import httpx

from . import agent_registry
from .config import Settings
from .db import eq
from .google_vault import GoogleVault

GOOGLE_AUTHORIZATION_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GMAIL_BASE_URL = 'https://gmail.googleapis.com/gmail/v1/users/me'
CALENDAR_BASE_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary'

STATE_TTL_SECONDS = 600


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

    def make_state(self, user_id: str) -> str:
        payload = {
            'uid': str(user_id),
            'nonce': uuid.uuid4().hex,
            'exp': int(time.time()) + STATE_TTL_SECONDS,
        }
        part = _b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        return f'{part}.{self._sign(part)}'

    def validate_state(self, state: str, user_id: str) -> dict[str, Any]:
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
        self, user_id: str, scopes: tuple[str, ...] | None = None
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
        requested = tuple(scopes) if scopes else READ_SCOPES
        params = {
            'client_id': self.settings.google_oauth_client_id,
            'redirect_uri': self.settings.google_oauth_redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(requested),
            'access_type': 'offline',
            'prompt': 'consent',
            'include_granted_scopes': 'true',
            'state': self.make_state(user_id),
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
        self, code: str, *, user_id: str, state: str
    ) -> dict[str, Any]:
        if not self.oauth_configured:
            raise GoogleConnectorError(
                'Google connections are not configured yet.',
                'GOOGLE_NOT_CONFIGURED',
                503,
            )
        self.validate_state(state, user_id)
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
        scopes = tuple(
            str(item) for item in str(token_payload.get('scope') or '').split() if item
        ) or READ_SCOPES
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

    async def disconnect(
        self, user_id: str, account_email: str | None = None
    ) -> dict[str, Any]:
        if self.db is None:
            return {'connected': False, 'accounts': []}
        rows = await self.list_connections(user_id)
        for row in rows:
            if account_email and str(row.get('account_email') or '') != account_email:
                continue
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
        return await self.status(user_id)

    async def access_token_for(
        self, user_id: str, account_email: str | None = None
    ) -> str:
        rows = await self.list_connections(user_id)
        for row in rows:
            if row.get('status') != 'connected':
                continue
            if account_email and str(row.get('account_email') or '') != account_email:
                continue
            ciphertext = str(row.get('access_token_ciphertext') or '')
            if not ciphertext:
                continue
            return self.vault.decrypt(ciphertext)
        raise ConnectionRequiredError()

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
        self, user_id: str, *, to: str, subject: str, body: str
    ) -> dict[str, Any]:
        access_token = await self.access_token_for(user_id)
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
        self, user_id: str, *, to: str, subject: str, body: str
    ) -> dict[str, Any]:
        access_token = await self.access_token_for(user_id)
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
