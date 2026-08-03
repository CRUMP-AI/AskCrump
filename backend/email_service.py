from __future__ import annotations

import html
import httpx

from .config import Settings


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _send(self, to: str, subject: str, body_html: str) -> bool:
        if not self.settings.resend_api_key:
            # Account creation still succeeds in local/test environments.
            return False
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                'https://api.resend.com/emails',
                headers={
                    'Authorization': f'Bearer {self.settings.resend_api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'from': self.settings.from_email,
                    'to': [to],
                    'subject': subject,
                    'html': body_html,
                },
            )
        response.raise_for_status()
        return True

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

    async def send_verification(self, email: str, name: str | None, token: str) -> bool:
        url = f"{self.settings.app_url}/api/auth/verify-email?token={token}"
        safe_name = html.escape(name or 'there')
        content = f"""<p>Hi {safe_name},</p><p>Confirm your email to finish creating your account.</p>
<p><a href="{html.escape(url)}" style="display:inline-block;background:#c9b892;color:#101419;text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700">Verify email</a></p>
<p style="color:#9aa4ad">This link expires in 24 hours. If you did not create this account, ignore this message.</p>"""
        return await self._send(email, f'Verify your {self.settings.app_name} account', self._layout('Verify your email', content))

    async def send_password_reset(self, email: str, name: str | None, token: str) -> bool:
        url = f"{self.settings.app_url}/app?token={token}"
        safe_name = html.escape(name or 'there')
        content = f"""<p>Hi {safe_name},</p><p>Use the button below to choose a new password.</p>
<p><a href="{html.escape(url)}" style="display:inline-block;background:#c9b892;color:#101419;text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700">Reset password</a></p>
<p style="color:#9aa4ad">This link expires in one hour. If you did not request it, your password has not changed.</p>"""
        return await self._send(email, f'Reset your {self.settings.app_name} password', self._layout('Reset your password', content))
