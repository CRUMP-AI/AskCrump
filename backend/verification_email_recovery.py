"""Fenced, one-shot recovery for transient verification-email failures."""
from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import uuid4

from .config import Settings
from .db import SupabaseDB, eq
from .email_service import EmailDeliveryError, EmailService
from .security import expiry_iso, random_token, token_hash


logger = logging.getLogger('askcrump.verification_email_recovery')


def provider_email_hash(provider_message_id: str) -> str:
    """Discard a raw provider identity at the application boundary."""
    return hashlib.sha256(
        f'resend-email:{provider_message_id}'.encode('utf-8')
    ).hexdigest()


def _one_row(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _scalar_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, list) and value:
        return _scalar_bool(value[0])
    if isinstance(value, dict) and len(value) == 1:
        return _scalar_bool(next(iter(value.values())))
    return False


class VerificationEmailRecoveryWorker:
    """Claim at most one due recovery and send at most one logical retry."""

    def __init__(
        self,
        settings: Settings,
        db: SupabaseDB,
        email_service: EmailService,
    ) -> None:
        self.settings = settings
        self.db = db
        self.email_service = email_service

    def configured(self) -> bool:
        return bool(
            self.settings.verification_email_recovery_enabled
            and self.settings.resend_api_key
            and self.settings.resend_webhook_secret
            and self.settings.cron_secret
            and self.settings.environment in {
                'production', 'preview', 'development', 'test',
            }
        )

    async def _fail_dispatch(
        self,
        claim: dict[str, Any],
        *,
        recovery_token_hash: str,
    ) -> bool:
        return _scalar_bool(
            await self.db.rpc(
                'fail_verification_email_recovery',
                {
                    'p_provider_email_hash': claim['provider_email_hash'],
                    'p_claim_token': claim['claim_token'],
                    'p_environment': self.settings.environment,
                    'p_recovery_token_hash': recovery_token_hash,
                },
                retry_transient=True,
                timeout=3.0,
            )
        )

    async def process_next(self) -> dict[str, Any]:
        if not self.configured():
            return {'handled': False, 'status': 'disabled'}

        claim_token = str(uuid4())
        claim = _one_row(
            await self.db.rpc(
                'claim_verification_email_recovery',
                {
                    'p_claim_token': claim_token,
                    'p_environment': self.settings.environment,
                },
                retry_transient=True,
                timeout=3.0,
            )
        )
        if not claim:
            return {'handled': False, 'status': 'idle'}

        # The raw address stays in the existing users table and process memory;
        # it is never copied into the private attempt ledger or logs.
        user = await self.db.select_one(
            'users',
            columns='id,email,full_name,is_verified',
            filters={'id': eq(claim.get('user_id'))},
        )
        if not user or user.get('is_verified'):
            return {'handled': True, 'status': 'superseded'}
        recipient = str(user.get('email') or '').strip()
        if not recipient:
            return {'handled': True, 'status': 'superseded'}

        raw_token = random_token(40)
        fresh_token_hash = token_hash(raw_token)
        fresh_expiry = expiry_iso(hours=24)
        prepared = _scalar_bool(
            await self.db.rpc(
                'prepare_verification_email_recovery',
                {
                    'p_provider_email_hash': claim['provider_email_hash'],
                    'p_claim_token': claim['claim_token'],
                    'p_previous_token_hash': claim.get('previous_token_hash'),
                    'p_previous_token_expires_at': claim.get(
                        'previous_token_expires_at'
                    ),
                    'p_new_token_hash': fresh_token_hash,
                    'p_new_token_expires_at': fresh_expiry,
                    'p_environment': self.settings.environment,
                },
                retry_transient=True,
                timeout=3.0,
            )
        )
        if not prepared:
            return {'handled': True, 'status': 'superseded'}

        # This database commit is the deterministic linearization point. Any
        # delivered, terminal, or verified event committed before it wins and
        # prevents external I/O. Once it succeeds, the provider request wins;
        # the short HTTP boundary itself cannot be made atomic with Postgres.
        authorized = _scalar_bool(
            await self.db.rpc(
                'authorize_verification_email_recovery_dispatch',
                {
                    'p_provider_email_hash': claim['provider_email_hash'],
                    'p_claim_token': claim['claim_token'],
                    'p_environment': self.settings.environment,
                    'p_previous_token_hash': claim.get('previous_token_hash'),
                    'p_previous_token_expires_at': claim.get(
                        'previous_token_expires_at'
                    ),
                    'p_recovery_token_hash': fresh_token_hash,
                },
                retry_transient=True,
                timeout=3.0,
            )
        )
        if not authorized:
            return {'handled': True, 'status': 'superseded'}

        try:
            receipt = await self.email_service.send_verification_receipt(
                recipient,
                user.get('full_name'),
                raw_token,
            )
            if not receipt.accepted or not receipt.provider_message_id:
                await self._fail_dispatch(
                    claim,
                    recovery_token_hash=fresh_token_hash,
                )
                return {'handled': True, 'status': 'send_failed'}
        except EmailDeliveryError as exc:
            try:
                await self._fail_dispatch(
                    claim,
                    recovery_token_hash=fresh_token_hash,
                )
                status = 'send_failed'
            except Exception:
                # The fenced lease expires and the attempt_count=1 row can never
                # be claimed again, so an outage cannot duplicate mail. The
                # original delivered token remains authoritative throughout.
                logger.exception(
                    'Verification email recovery rollback was not confirmed '
                    'error_type=%s',
                    type(exc).__name__,
                )
                status = 'rollback_unconfirmed'
            return {'handled': True, 'status': status}
        except Exception as exc:
            try:
                await self._fail_dispatch(
                    claim,
                    recovery_token_hash=fresh_token_hash,
                )
                status = 'send_failed'
            except Exception:
                logger.exception(
                    'Verification email recovery rollback was not confirmed '
                    'error_type=%s',
                    type(exc).__name__,
                )
                status = 'rollback_unconfirmed'
            return {'handled': True, 'status': status}

        completed = _scalar_bool(
            await self.db.rpc(
                'complete_verification_email_recovery',
                {
                    'p_provider_email_hash': claim['provider_email_hash'],
                    'p_claim_token': claim['claim_token'],
                    'p_retry_provider_email_hash': provider_email_hash(
                        receipt.provider_message_id
                    ),
                    'p_environment': self.settings.environment,
                    'p_recovery_token_hash': fresh_token_hash,
                    'p_recovery_token_expires_at': fresh_expiry,
                },
                retry_transient=True,
                timeout=3.0,
            )
        )
        return {
            'handled': True,
            'status': 'retry_sent' if completed else 'completion_unconfirmed',
        }
