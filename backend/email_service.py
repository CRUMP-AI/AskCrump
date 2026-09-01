from __future__ import annotations

import asyncio
import hashlib
import html
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
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


class EmailService:
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
        return status_code == 429 or status_code >= 500

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get('retry-after')
            if retry_after:
                try:
                    return max(0.25, min(4.0, float(retry_after)))
                except ValueError:
                    pass
        return min(1.0 * (2 ** attempt), 4.0)

    async def _send(
        self,
        to: str,
        subject: str,
        body_html: str,
        *,
        idempotency_key: str,
    ) -> bool:
        if not self.settings.resend_api_key:
            # Account creation still succeeds in local/test environments.
            return False

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            for attempt in range(3):
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
                            'from': self.settings.from_email,
                            'to': [to],
                            'subject': subject,
                            'html': body_html,
                        },
                    )
                except httpx.HTTPError as exc:
                    if attempt < 2:
                        await self._sleep(self._retry_delay(None, attempt))
                        continue
                    raise EmailDeliveryError(
                        status_code=None,
                        retryable=True,
                    ) from exc

                if response.is_success:
                    return True

                retryable = self._retryable_status(response.status_code)
                if retryable and attempt < 2:
                    await self._sleep(self._retry_delay(response, attempt))
                    continue

                raise EmailDeliveryError(
                    status_code=response.status_code,
                    retryable=retryable,
                )
        finally:
            if owns_client:
                await client.aclose()

    def _layout(self, heading: str, content: str) -> str:
        app = html.escape(self.settings.app_name)
        return f"""<!doctype html>
<html><body style="margin:0;background:#0f1419;color:#f7f4ee;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" style="max-width:600px;background:#171d23;border:1px solid #2b333c;border-radius:18px;overflow:hidden">
<tr><td style="padding:30px 32px;border-bottom:1px solid #2b333c"><div style="color:#c9b892;font-size:13px;letter-spacing:.16em;text-transform:uppercase">{app}</div><h1 style="margin:8px 0 0;font-size:28px">{html.escape(heading)}</h1></td></tr>
<tr><td style="padding:30px 32px;line-height:1.65">{content}</td></tr>
<tr><td style="padding:20px 32px;color:#9aa4ad;font-size:13px;border-top:1px solid #2b333c">Questions? {html.escape(self.settings.support_email)}</td></tr>
</table></td></tr></table></body></html>"""

    async def send_verification(
        self,
        email: str,
        name: str | None,
        token: str,
        *,
        intent: str | None = None,
        plan: str | None = None,
    ) -> bool:
        url = verification_email_url(
            self.settings.app_url,
            token,
            intent=intent,
            plan=plan,
        )
        safe_name = html.escape(name or 'there')
        content = f"""<p>Hi {safe_name},</p><p>Confirm your email and open your Ask Crump workspace.</p>
<p><a href="{html.escape(url)}" style="display:inline-block;background:#c9b892;color:#101419;text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700">Verify &amp; open Ask Crump</a></p>
<p style="color:#9aa4ad">This secure link expires in 24 hours. After verification, the same link can open your workspace for 15 minutes. If you did not create this account, ignore this message.</p>"""
        return await self._send(
            email,
            f'Verify your {self.settings.app_name} account',
            self._layout('Verify your email', content),
            idempotency_key=self._idempotency_key('verify', email, token),
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
