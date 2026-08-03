from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .db import SupabaseDB, eq, gte


class UsageLimitError(RuntimeError):
    def __init__(self, used: int, limit: int, usage_type: str) -> None:
        super().__init__('Usage limit reached')
        self.used = used
        self.limit = limit
        self.usage_type = usage_type


def tier_name(user: dict[str, Any]) -> str:
    tier = str(user.get('subscription_tier') or user.get('tier') or 'free').lower()
    return tier if tier in {'free', 'professional', 'enterprise'} else 'free'


def limit_for(settings: Settings, tier: str, usage_type: str) -> int:
    if usage_type != 'messages':
        usage_type = 'messages'
    return {
        'free': settings.free_daily_messages,
        'professional': settings.professional_daily_messages,
        'enterprise': settings.enterprise_daily_messages,
    }.get(tier, settings.free_daily_messages)


def day_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


async def current_usage(db: SupabaseDB, user: dict[str, Any], settings: Settings, usage_type: str = 'messages') -> dict[str, Any]:
    rows = await db.select(
        'usage_events',
        columns='id',
        filters={
            'user_id': eq(user['id']),
            'event_type': eq(usage_type),
            'created_at': gte(day_start_iso()),
        },
        limit=10000,
    )
    used = len(rows)
    tier = tier_name(user)
    limit = limit_for(settings, tier, usage_type)
    return {
        'tier': tier,
        'used': used,
        'limit': limit,
        'remaining': max(0, limit - used) if limit >= 0 else -1,
    }


async def consume_usage(
    db: SupabaseDB,
    user: dict[str, Any],
    settings: Settings,
    usage_type: str = 'messages',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tier = tier_name(user)
    limit = limit_for(settings, tier, usage_type)
    result = await db.rpc('consume_usage_event', {
        'p_user_id': user['id'],
        'p_event_type': usage_type,
        'p_limit': limit,
        'p_metadata': metadata or {},
    })
    row = result[0] if isinstance(result, list) and result else (result or {})
    used = int(row.get('used') or 0)
    if not row.get('allowed'):
        raise UsageLimitError(used, limit, usage_type)
    return {
        'eventId': row.get('event_id'),
        'tier': tier,
        'used': used,
        'limit': limit,
        'remaining': max(0, limit - used) if limit >= 0 else -1,
    }


async def refund_usage(db: SupabaseDB, user_id: str, event_id: str | None) -> None:
    if not event_id:
        return
    await db.delete('usage_events', filters={'id': eq(event_id), 'user_id': eq(user_id)})
