from __future__ import annotations

import asyncio
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any

import httpx

from .config import Settings
from .db import SupabaseDB, eq
from .security import iso_now

logger = logging.getLogger('askcrump.push')


@dataclass(slots=True)
class PushResult:
    attempted: int = 0
    delivered: int = 0
    disabled: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            'attempted': self.attempted,
            'delivered': self.delivered,
            'disabled': self.disabled,
            'skipped': self.skipped,
        }


class PushService:
    """Sends native push notifications through APNs and FCM.

    Device tokens are registered by the official Capacitor Push Notifications
    plugin. Missing provider credentials make delivery a safe no-op so local and
    web deployments continue to work.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._fcm_credentials: Any = None
        self._fcm_expiry: datetime | None = None
        self._apns_token: str | None = None
        self._apns_expiry: datetime | None = None

    def _service_account_info(self) -> dict[str, Any] | None:
        raw = self.settings.google_service_account_json
        if not raw:
            return None
        candidate = raw.strip()
        try:
            if not candidate.startswith('{'):
                candidate = base64.b64decode(candidate).decode('utf-8')
            value = json.loads(candidate)
            return value if isinstance(value, dict) else None
        except (ValueError, TypeError, binascii.Error):
            logger.error('GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON or base64 JSON.')
            return None

    async def _fcm_access_token(self) -> str | None:
        info = self._service_account_info()
        if not info:
            return None
        now = datetime.now(timezone.utc)
        if self._fcm_credentials and self._fcm_expiry and self._fcm_expiry > now + timedelta(minutes=5):
            return str(self._fcm_credentials.token)
        try:
            from google.auth.transport.requests import Request as GoogleRequest
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=['https://www.googleapis.com/auth/firebase.messaging'],
            )
            await asyncio.to_thread(credentials.refresh, GoogleRequest())
            self._fcm_credentials = credentials
            expiry = credentials.expiry
            self._fcm_expiry = expiry.replace(tzinfo=timezone.utc) if expiry and not expiry.tzinfo else expiry
            return str(credentials.token)
        except Exception:
            logger.exception('Unable to create an FCM access token.')
            return None

    def _apns_provider_token(self) -> str | None:
        if not all((
            self.settings.apns_key_id,
            self.settings.apns_team_id,
            self.settings.apns_private_key,
        )):
            return None
        now = datetime.now(timezone.utc)
        if self._apns_token and self._apns_expiry and self._apns_expiry > now + timedelta(minutes=5):
            return self._apns_token
        try:
            import jwt

            key = self.settings.apns_private_key.replace('\\n', '\n')
            token = jwt.encode(
                {'iss': self.settings.apns_team_id, 'iat': int(now.timestamp())},
                key,
                algorithm='ES256',
                headers={'kid': self.settings.apns_key_id},
            )
            self._apns_token = token
            self._apns_expiry = now + timedelta(minutes=50)
            return token
        except Exception:
            logger.exception('Unable to create an APNs provider token.')
            return None

    async def _send_android(self, token: str, title: str, body: str, data: dict[str, str]) -> tuple[bool, bool]:
        access_token = await self._fcm_access_token()
        project_id = self.settings.fcm_project_id
        if not access_token or not project_id:
            return False, False
        payload = {
            'message': {
                'token': token,
                'notification': {'title': title, 'body': body},
                'data': data,
                'android': {
                    'priority': 'high',
                    'notification': {
                        'channel_id': 'crump_check_ins',
                        'sound': 'default',
                        'tag': data.get('chatId') or 'ask-crump',
                    },
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send',
                    headers={'Authorization': f'Bearer {access_token}'},
                    json=payload,
                )
            if response.status_code < 300:
                return True, False
            text = response.text.lower()
            stale = response.status_code in {404, 410} or 'unregistered' in text or 'registration-token-not-registered' in text
            logger.warning('FCM rejected push: %s %s', response.status_code, response.text[:300])
            return False, stale
        except httpx.HTTPError:
            logger.exception('FCM push request failed.')
            return False, False

    async def _send_ios(self, token: str, title: str, body: str, data: dict[str, str]) -> tuple[bool, bool]:
        provider_token = self._apns_provider_token()
        bundle_id = self.settings.apns_bundle_id
        if not provider_token or not bundle_id:
            return False, False
        host = 'https://api.push.apple.com' if self.settings.apns_environment == 'production' else 'https://api.sandbox.push.apple.com'
        payload = {
            'aps': {
                'alert': {'title': title, 'body': body},
                'sound': 'default',
                'thread-id': data.get('chatId') or 'ask-crump',
                'mutable-content': 1,
            },
            **data,
        }
        try:
            async with httpx.AsyncClient(http2=True, timeout=20) as client:
                response = await client.post(
                    f'{host}/3/device/{token}',
                    headers={
                        'authorization': f'bearer {provider_token}',
                        'apns-topic': bundle_id,
                        'apns-push-type': 'alert',
                        'apns-priority': '10',
                    },
                    json=payload,
                )
            if response.status_code == 200:
                return True, False
            reason = ''
            try:
                reason = str(response.json().get('reason') or '')
            except ValueError:
                reason = response.text
            stale = response.status_code in {404, 410} or reason in {'BadDeviceToken', 'DeviceTokenNotForTopic', 'Unregistered'}
            logger.warning('APNs rejected push: %s %s', response.status_code, reason[:200])
            return False, stale
        except httpx.HTTPError:
            logger.exception('APNs push request failed.')
            return False, False

    async def send_user(
        self,
        db: SupabaseDB,
        user_id: str,
        *,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> PushResult:
        rows = await db.select(
            'push_tokens',
            columns='id,token,platform,enabled',
            filters={'user_id': eq(user_id), 'enabled': eq(True)},
            limit=50,
        )
        result = PushResult()
        safe_data = {str(key): str(value)[:1000] for key, value in (data or {}).items() if value is not None}
        for row in rows:
            token = str(row.get('token') or '').strip()
            platform = str(row.get('platform') or '').lower()
            if not token:
                continue
            if platform not in {'ios', 'android'}:
                result.skipped += 1
                continue
            result.attempted += 1
            if platform == 'ios':
                delivered, stale = await self._send_ios(token, title, body, safe_data)
            else:
                delivered, stale = await self._send_android(token, title, body, safe_data)
            if delivered:
                result.delivered += 1
                await db.update('push_tokens', {'last_used_at': iso_now(), 'updated_at': iso_now()}, filters={'id': eq(row['id'])})
            elif stale:
                result.disabled += 1
                await db.update('push_tokens', {'enabled': False, 'updated_at': iso_now()}, filters={'id': eq(row['id'])})
        return result
