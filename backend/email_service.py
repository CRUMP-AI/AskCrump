from __future__ import annotations

import asyncio
import hashlib
import html
import math
from collections.abc import Awaitable, Callable

import httpx

from .config import Settings
from .verification_handoff import verification_email_url


class EmailDeliveryError(RuntimeError):
    """Controlled transactional-email failure suitable for API-layer handling."""

    def __init__(
        self,
        message: str = 'Transactional email delivery failed.',
        *,
        status_code: int | None = None,
        provider_code: str | None = None,
        retryable: bool = False,
        retry_after_seconds: int = 0,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider_code = provider_code
        self.retryable = retryable
        self.retry_after_seconds = max(0, min(3600, int(retry_after_seconds or 0)))


class EmailService:
    _KNOWN_PROVIDER_ERROR_CODES = frozenset({
        'concurrent_idempotent_requests',
        'invalid_idempotent_request',
    })

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self._client = client
        self._sleep = sleep

    @staticmethod
    def _idempotency_key(kind: str, email: str, token: str) -> str:
        digest = hashlib.sha256(f'{kind}:{email.lower()}:{token}'.encode('utf-8')).hexdigest()
        return f'ask-crump-{kind}-{digest}'

    @staticmethod
    def _retryable_status(status_code: int) -> bool:
        return status_code in {408, 429} or status_code >= 500

    @classmethod
    def _provider_error_code(cls, response: httpx.Response) -> str | None:
        """Return only provider codes whose retry semantics we explicitly support."""
        if response.status_code != 409:
            return None
        try:
            payload = response.json()
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None
        for key in ('name', 'code'):
            value = payload.get(key)
            if isinstance(value, str) and value in cls._KNOWN_PROVIDER_ERROR_CODES:
                return value
        return None

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get('retry-after')
            if retry_after:
                try:
                    parsed = float(retry_after)
                    if math.isfinite(parsed):
                        return max(0.25, min(4.0, parsed))
                except (ValueError, OverflowError):
                    pass
        return min(1.0 * (2 ** attempt), 4.0)

    @staticmethod
    def _retry_after_seconds(response: httpx.Response | None) -> int:
        if response is None:
            return 0
        raw = response.headers.get('retry-after')
        if not raw:
            return 0
        try:
            parsed = float(raw)
            if not math.isfinite(parsed):
                return 0
            return max(0, min(3600, math.ceil(parsed)))
        except (ValueError, OverflowError):
            return 0

    async def _send(
        self,
        to: str,
        subject: str,
        body_html: str,
        *,
        idempotency_key: str,
        provider_attempts: int = 3,
        from_email: str | None = None,
    ) -> bool:
        if not self.settings.resend_api_key:
            # Account creation still succeeds in local/test environments.
            return False

        if not 1 <= provider_attempts <= 3:
            raise ValueError('Provider attempts must be between one and three.')

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            for attempt in range(provider_attempts):
                response: httpx.Response | None = None
                try:
                    response = await client.post(
                        'https://api.resend.com/emails',
                        headers={
                            'Authorization': f'Bearer {self.settings.resend_api_key}',
                            'Content-Type': 'application/json',
                            'Idempotency-Key': idempotency_key,
                        },
                        json={
                            'from': from_email or self.settings.from_email,
                            'to': [to],
                            'subject': subject,
                            'html': body_html,
                        },
                    )
                except httpx.HTTPError as exc:
                    if attempt < provider_attempts - 1:
                        await self._sleep(self._retry_delay(None, attempt))
                        continue
                    raise EmailDeliveryError(
                        status_code=None,
                        retryable=True,
                    ) from exc

                if response.is_success:
                    return True

                provider_code = self._provider_error_code(response)
                retryable = self._retryable_status(response.status_code) or (
                    provider_code == 'concurrent_idempotent_requests'
                )
                if retryable and attempt < provider_attempts - 1:
                    await self._sleep(self._retry_delay(response, attempt))
                    continue

                raise EmailDeliveryError(
                    status_code=response.status_code,
                    provider_code=provider_code,
                    retryable=retryable,
                    retry_after_seconds=self._retry_after_seconds(response),
                )
        finally:
            if owns_client:
                await client.aclose()

    def _layout(
        self,
        heading: str,
        content: str,
        *,
        app_name: str | None = None,
        support_email: str | None = None,
    ) -> str:
        app = html.escape(app_name or self.settings.app_name)
        support = html.escape(support_email or self.settings.support_email)
        return f"""<!doctype html>
<html><body style="margin:0;background:#0f1419;color:#f7f4ee;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" style="max-width:600px;background:#171d23;border:1px solid #2b333c;border-radius:18px;overflow:hidden">
<tr><td style="padding:30px 32px;border-bottom:1px solid #2b333c"><div style="color:#c9b892;font-size:13px;letter-spacing:.16em;text-transform:uppercase">{app}</div><h1 style="margin:8px 0 0;font-size:28px">{html.escape(heading)}</h1></td></tr>
<tr><td style="padding:30px 32px;line-height:1.65">{content}</td></tr>
<tr><td style="padding:20px 32px;color:#9aa4ad;font-size:13px;border-top:1px solid #2b333c">Questions? {support}</td></tr>
</table></td></tr></table></body></html>"""

    async def send_verification(
        self,
        email: str,
        name: str | None,
        token: str,
        *,
        intent: str | None = None,
        plan: str | None = None,
        idempotency_key: str | None = None,
        provider_attempts: int = 3,
        template_version: str = 'verification-v1',
        app_name: str | None = None,
        app_url: str | None = None,
        support_email: str | None = None,
        from_email: str | None = None,
    ) -> bool:
        if template_version != 'verification-v1':
            raise ValueError('Verification email template is unsupported.')
        url = verification_email_url(
            app_url or self.settings.app_url,
            token,
            intent=intent,
            plan=plan,
        )
        safe_name = html.escape(name or 'there')
        content = f"""<p>Hi {safe_name},</p><p>Confirm your email and open your Ask Crump workspace.</p>
<p><a href="{html.escape(url)}" style="display:inline-block;background:#c9b892;color:#101419;text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700">Verify &amp; open Ask Crump</a></p>
<p style="color:#9aa4ad">This secure link is time-limited. If it has expired, request a fresh verification email. Its first successful use verifies your account and signs that browser in; later uses only confirm that the address is already verified. If you did not create this account, ignore this message.</p>"""
        return await self._send(
            email,
            f'Verify your {app_name or self.settings.app_name} account',
            self._layout(
                'Verify your email',
                content,
                app_name=app_name,
                support_email=support_email,
            ),
            idempotency_key=(
                idempotency_key or self._idempotency_key('verify', email, token)
            ),
            provider_attempts=provider_attempts,
            from_email=from_email,
        )

    async def send_password_reset(self, email: str, name: str | None, token: str) -> bool:
        url = f"{self.settings.app_url}/app?token={token}"
        safe_name = html.escape(name or 'there')
        content = f"""<p>Hi {safe_name},</p><p>Use the button below to choose a new password.</p>
<p><a href="{html.escape(url)}" style="display:inline-block;background:#c9b892;color:#101419;text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700">Reset password</a></p>
<p style="color:#9aa4ad">This link expires in one hour. If you did not request it, your password has not changed.</p>"""
        return await self._send(
            email,
            f'Reset your {self.settings.app_name} password',
            self._layout('Reset your password', content),
            idempotency_key=self._idempotency_key('password-reset', email, token),
        )
