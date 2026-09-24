"""Durable private-Storage cleanup after an account is removed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from .db import SupabaseDB
from .file_service import FileService, FileServiceError

logger = logging.getLogger("askcrump.account_deletion")


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


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    if raw.endswith('Z'):
        raw = f'{raw[:-1]}+00:00'
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class AccountDeletionService:
    """Claim, purge, and safely retire one account deletion obligation."""

    def __init__(self, db: SupabaseDB, files: FileService) -> None:
        self.db = db
        self.files = files

    async def process_next(self) -> dict[str, Any]:
        claimed = _one_row(
            await self.db.rpc(
                'claim_account_storage_deletion_job',
                {},
            )
        )
        if not claimed:
            return {'handled': False, 'status': 'idle'}

        job_id = str(claimed.get('job_id') or '')
        lease_token = str(claimed.get('lease_token') or '')
        if not job_id or not lease_token:
            logger.error('Account Storage cleanup claim was missing its fenced lease.')
            return {'handled': True, 'status': 'invalid_claim'}

        try:
            purge = await self.files.purge_owner_prefix(
                user_id=str(claimed.get('user_id') or ''),
                bucket=str(claimed.get('bucket') or ''),
                owner_prefix=str(claimed.get('owner_prefix') or ''),
            )
            if purge.get('empty') is not True:
                raise FileServiceError(
                    'Private file cleanup could not verify the account prefix.',
                    503,
                    'STORAGE_PREFIX_NOT_EMPTY',
                )

            now = datetime.now(timezone.utc)
            final_sweep_after = _parse_timestamp(claimed.get('final_sweep_after'))
            empty_observed_at = _parse_timestamp(claimed.get('empty_observed_at'))
            deleted_count = max(0, int(purge.get('deletedCount') or 0))
            second_empty_observation = bool(
                final_sweep_after
                and now >= final_sweep_after
                and deleted_count == 0
                and empty_observed_at
                and empty_observed_at <= now - timedelta(minutes=5)
            )
            if second_empty_observation:
                completed = _scalar_bool(
                    await self.db.rpc(
                        'complete_account_storage_deletion_job',
                        {
                            'p_job_id': job_id,
                            'p_lease_token': lease_token,
                        },
                    )
                )
                if not completed:
                    released = await self.db.rpc(
                        'release_account_storage_deletion_job',
                        {
                            'p_job_id': job_id,
                            'p_lease_token': lease_token,
                            'p_objects_deleted': 0,
                            'p_error': None,
                        },
                    )
                    if isinstance(released, list) and released:
                        released = released[0]
                    if isinstance(released, dict) and len(released) == 1:
                        released = next(iter(released.values()))
                    return {
                        'handled': True,
                        'status': str(released or 'lease_lost'),
                        'deletedObjects': deleted_count,
                    }
                return {
                    'handled': True,
                    'status': 'completed',
                    'deletedObjects': deleted_count,
                }

            released = await self.db.rpc(
                'release_account_storage_deletion_job',
                {
                    'p_job_id': job_id,
                    'p_lease_token': lease_token,
                    'p_objects_deleted': deleted_count,
                    'p_error': None,
                },
            )
            if isinstance(released, list) and released:
                released = released[0]
            if isinstance(released, dict) and len(released) == 1:
                released = next(iter(released.values()))
            return {
                'handled': True,
                'status': str(released or 'released'),
                'deletedObjects': deleted_count,
            }
        except Exception as exc:
            error_code = exc.code if isinstance(exc, FileServiceError) else type(exc).__name__
            logger.warning('Account Storage cleanup will retry after error_code=%s', error_code)
            try:
                await self.db.rpc(
                    'release_account_storage_deletion_job',
                    {
                        'p_job_id': job_id,
                        'p_lease_token': lease_token,
                        'p_objects_deleted': 0,
                        'p_error': str(error_code)[:300],
                    },
                )
                status = 'retry_scheduled'
            except Exception:
                # The lease expires, so a failed release cannot strand the job.
                logger.exception('Account Storage cleanup retry release was not confirmed.')
                status = 'lease_expiry_recovery'
            return {
                'handled': True,
                'status': status,
                'errorCode': str(error_code),
            }
