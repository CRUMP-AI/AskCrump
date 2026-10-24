"""Durable, content-minimized password-reset email dispatch."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from typing import Any
from uuid import UUID

from .config import Settings
from .db import DatabaseError, SupabaseDB
from .email_service import EmailDeliveryError, EmailService
from .password_reset_tokens import create_password_reset_alias
from .security import expiry_iso, new_uuid, normalize_email, random_token, token_hash


logger = logging.getLogger('askcrump.password_reset_email_queue')

_HEX_64 = re.compile(r'^[0-9a-f]{64}$')
_KEY_ID = re.compile(r'^[A-Za-z0-9_-]{1,16}$')
_NONCE = re.compile(r'^[A-Za-z0-9_-]{16,64}$')
_TEMPLATE_VERSION = 'password-reset-v1'


class PasswordResetEmailQueueUnavailable(RuntimeError):
    """The resend request could not be durably accepted."""


def _first_row(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return dict(value) if isinstance(value, dict) else None


def _signing_keys(settings: Settings) -> dict[str, str]:
    # Rotation invariant: retain an old key until every queued job using its ID
    # is terminal and every alias it signed has passed its stored reset expiry.
    configured = dict(settings.verification_link_signing_keys or ())
    if configured:
        return configured
    if settings.environment.lower() in {'production', 'preview'}:
        raise PasswordResetEmailQueueUnavailable(
            'Password-reset signing keys are unavailable.'
        )
    return {'local': 'ask-crump-local-verification-alias-tests-key-000000000000'}


def _recipient_fingerprint(signing_secret: str, email: str) -> str:
    key = hashlib.sha256(
        b'ask-crump-password-reset-recipient-v1\x00' + signing_secret.encode('utf-8')
    ).digest()
    return hmac.new(key, normalize_email(email).encode('utf-8'), hashlib.sha256).hexdigest()


class PasswordResetEmailQueueService:
    """Queue resends and process at most one provider request per worker turn."""

    def __init__(self, settings: Settings, db: SupabaseDB, email_service: EmailService) -> None:
        self.settings = settings
        self.db = db
        self.email_service = email_service

    async def enqueue(
        self,
        *,
        email: str,
    ) -> None:
        normalized_email = normalize_email(email)
        signing_keys = _signing_keys(self.settings)
        key_id, signing_secret = next(iter(signing_keys.items()))
        job_id = new_uuid()
        payload = {
            'p_job_id': job_id,
            'p_normalized_email': normalized_email,
            'p_recipient_fingerprint': _recipient_fingerprint(
                signing_secret,
                normalized_email,
            ),
            'p_replacement_token_hash': token_hash(random_token(40)),
            'p_replacement_expires_at': expiry_iso(hours=1),
            'p_alias_key_id': key_id,
            'p_alias_nonce': secrets.token_urlsafe(18),
            'p_template_version': _TEMPLATE_VERSION,
            'p_app_name': self.settings.app_name,
            'p_app_url': self.settings.app_url,
            'p_support_email': self.settings.support_email,
            'p_from_email': self.settings.from_email,
        }
        try:
            result = await self.db.rpc(
                'enqueue_password_reset_email_job_v1',
                payload,
                retry_transient=True,
            )
        except DatabaseError as exc:
            raise PasswordResetEmailQueueUnavailable(
                'Password reset email queue is unavailable.'
            ) from exc
        row = _first_row(result)
        if (
            not row
            or row.get('accepted') is not True
            or str(row.get('job_id') or '') != job_id
        ):
            raise PasswordResetEmailQueueUnavailable(
                'Password reset email queue did not confirm acceptance.'
            )

    async def _complete(self, job_id: str, lease_token: str, outcome: str) -> str:
        result = await self.db.rpc(
            'complete_password_reset_email_job_v1',
            {
                'p_job_id': job_id,
                'p_lease_token': lease_token,
                'p_outcome': outcome,
            },
        )
        row = _first_row(result)
        if row:
            return str(next(iter(row.values()), ''))
        return str(result or '')

    async def _release(
        self,
        job_id: str,
        lease_token: str,
        *,
        failure_code: str,
        retryable: bool,
        retry_after_seconds: int = 0,
    ) -> str:
        result = await self.db.rpc(
            'release_password_reset_email_job_v1',
            {
                'p_job_id': job_id,
                'p_lease_token': lease_token,
                'p_failure_code': failure_code,
                'p_retryable': retryable,
                'p_retry_after_seconds': max(0, min(3600, retry_after_seconds)),
            },
        )
        row = _first_row(result)
        if row:
            return str(next(iter(row.values()), ''))
        return str(result or '')

    @staticmethod
    def _delivery_failure(exc: EmailDeliveryError) -> tuple[str, bool]:
        if exc.provider_code == 'concurrent_idempotent_requests':
            return 'PROVIDER_UNAVAILABLE', True
        if exc.status_code == 429:
            return 'PROVIDER_THROTTLED', True
        if exc.status_code in {408} or (
            exc.status_code is not None and exc.status_code >= 500
        ):
            return 'PROVIDER_UNAVAILABLE', True
        if exc.status_code is None:
            return 'PROVIDER_TRANSPORT', bool(exc.retryable)
        return 'PROVIDER_REJECTED', False

    async def process_next(self) -> dict[str, Any]:
        claim_token = new_uuid()
        claim_result = await self.db.rpc(
            'claim_password_reset_email_job_v1',
            {'p_claim_token': claim_token, 'p_lease_seconds': 120},
            retry_transient=True,
        )
        claim = _first_row(claim_result)
        if not claim:
            return {'handled': False, 'status': 'idle'}

        job_id = str(claim.get('job_id') or '')
        lease_token = str(claim.get('lease_token') or '')
        if lease_token != claim_token or not job_id:
            logger.error('Password reset email claim failed integrity validation.')
            return {'handled': True, 'status': 'claim_invalid'}

        try:
            stage_result = await self.db.rpc(
                'stage_password_reset_email_job_v1',
                {'p_job_id': job_id, 'p_lease_token': lease_token},
                retry_transient=True,
            )
            stage = _first_row(stage_result)
            if not stage:
                return {'handled': True, 'status': 'lease_lost'}
            disposition = str(stage.get('disposition') or '')
            if disposition == 'lease_lost':
                return {'handled': True, 'status': 'lease_lost'}
            if disposition == 'suppress':
                outcome = await self._complete(job_id, lease_token, 'suppressed')
                return {'handled': True, 'status': outcome or 'suppressed'}
            if disposition != 'deliver':
                await self._release(
                    job_id,
                    lease_token,
                    failure_code='JOB_INTEGRITY_INVALID',
                    retryable=False,
                )
                return {'handled': True, 'status': 'failed_permanent'}

            recipient = normalize_email(str(stage.get('recipient_email') or ''))
            recipient_fingerprint = str(stage.get('recipient_fingerprint') or '')
            anchor = str(stage.get('password_reset_token_hash') or '').lower()
            key_id = str(stage.get('alias_key_id') or '')
            nonce = str(stage.get('alias_nonce') or '')
            user_id = str(stage.get('user_id') or '')
            template_version = str(stage.get('template_version') or '')
            try:
                canonical_user_id = str(UUID(user_id))
            except (TypeError, ValueError):
                canonical_user_id = ''
            if (
                not recipient
                or not _HEX_64.fullmatch(recipient_fingerprint)
                or not _HEX_64.fullmatch(anchor)
                or not _KEY_ID.fullmatch(key_id)
                or not _NONCE.fullmatch(nonce)
                or canonical_user_id != user_id
                or template_version != _TEMPLATE_VERSION
                or not str(stage.get('app_name') or '')
                or not str(stage.get('app_url') or '')
                or not str(stage.get('support_email') or '')
                or not str(stage.get('from_email') or '')
            ):
                await self._release(
                    job_id,
                    lease_token,
                    failure_code='JOB_INTEGRITY_INVALID',
                    retryable=False,
                )
                return {'handled': True, 'status': 'failed_permanent'}

            try:
                signing_secret = _signing_keys(self.settings).get(key_id)
            except PasswordResetEmailQueueUnavailable:
                signing_secret = None
            if not signing_secret:
                await self._release(
                    job_id,
                    lease_token,
                    failure_code='SIGNING_KEY_UNAVAILABLE',
                    retryable=True,
                )
                return {'handled': True, 'status': 'retry_scheduled'}
            if not hmac.compare_digest(
                recipient_fingerprint,
                _recipient_fingerprint(signing_secret, recipient),
            ):
                await self._release(
                    job_id,
                    lease_token,
                    failure_code='JOB_INTEGRITY_INVALID',
                    retryable=False,
                )
                return {'handled': True, 'status': 'failed_permanent'}

            try:
                alias = create_password_reset_alias(
                    signing_secret,
                    key_id=key_id,
                    user_id=user_id,
                    password_reset_token_hash=anchor,
                    expires_at=stage.get('password_reset_expires'),
                    nonce=nonce,
                )
                sent = await self.email_service.send_password_reset(
                    recipient,
                    None,
                    alias,
                    idempotency_key=f'ask-crump-reset-job-{job_id}',
                    provider_attempts=1,
                    template_version=template_version,
                    app_name=str(stage.get('app_name') or ''),
                    app_url=str(stage.get('app_url') or ''),
                    support_email=str(stage.get('support_email') or ''),
                    from_email=str(stage.get('from_email') or ''),
                )
            except ValueError:
                outcome = await self._release(
                    job_id,
                    lease_token,
                    failure_code='JOB_INTEGRITY_INVALID',
                    retryable=False,
                )
                return {'handled': True, 'status': outcome or 'failed_permanent'}
            if not sent:
                outcome = await self._release(
                    job_id,
                    lease_token,
                    failure_code='EMAIL_NOT_CONFIGURED',
                    retryable=False,
                )
                return {'handled': True, 'status': outcome or 'failed_permanent'}
            outcome = await self._complete(job_id, lease_token, 'provider_accepted')
            return {'handled': True, 'status': outcome or 'provider_accepted'}
        except EmailDeliveryError as exc:
            failure_code, retryable = self._delivery_failure(exc)
            try:
                outcome = await self._release(
                    job_id,
                    lease_token,
                    failure_code=failure_code,
                    retryable=retryable,
                    retry_after_seconds=exc.retry_after_seconds,
                )
            except DatabaseError:
                logger.warning('Password reset email release outcome is uncertain.')
                outcome = 'lease_recovery_pending'
            return {'handled': True, 'status': outcome}
        except DatabaseError:
            # An uncertain completion is never followed by an explicit release:
            # the lease expires, and the exact alias/body/provider key replay.
            logger.warning('Password reset email worker outcome is uncertain.')
            return {'handled': True, 'status': 'lease_recovery_pending'}
        except Exception:
            logger.exception('Password reset email worker failed without customer content.')
            try:
                outcome = await self._release(
                    job_id,
                    lease_token,
                    failure_code='WORKER_UNEXPECTED',
                    retryable=True,
                )
            except DatabaseError:
                outcome = 'lease_recovery_pending'
            return {'handled': True, 'status': outcome}
