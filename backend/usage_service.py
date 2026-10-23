from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .db import SupabaseDB, eq, gt, gte


FREE_TEXT_MESSAGE_LIMIT = 5
FREE_TEXT_WINDOW_SECONDS = 24 * 60 * 60


class UsageLimitError(RuntimeError):
    def __init__(self, used: int, limit: int, usage_type: str, credit_balance: int = 0) -> None:
        super().__init__('Usage limit reached')
        self.used = used
        self.limit = limit
        self.usage_type = usage_type
        self.credit_balance = max(0, int(credit_balance or 0))


def _future_timestamp(value: Any) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def tier_name(user: dict[str, Any]) -> str:
    """Return the effective usage tier, not merely the last stored paid label.

    Stripe and RevenueCat webhooks persist both tier and lifecycle state. Paid
    allowances are granted only for currently entitled states. A cancellation
    that remains valid until period end is honored only while that period is in
    the future; terminal/inactive states always fall back to free. Founder and
    staff QA access is stored separately so it cannot be confused with revenue.
    """
    # Guest state is the dominant trust boundary. A stale or malformed guest
    # row must never escape the shared five-message preview because it also
    # happens to carry paid-looking billing or internal-access fields.
    if bool(user.get('is_guest')):
        return 'free'

    internal_tier = str(user.get('internal_tier') or '').lower()
    if internal_tier in {'professional', 'enterprise'}:
        return internal_tier

    tier = str(user.get('subscription_tier') or user.get('tier') or 'free').lower()
    if tier not in {'professional', 'enterprise'}:
        return 'free'

    status = str(user.get('subscription_status') or 'inactive').lower()
    if status in {'active', 'trialing'}:
        return tier
    if status in {'canceling', 'billing_issue'} and _future_timestamp(
        user.get('subscription_current_period_end')
    ):
        return tier
    return 'free'


def has_internal_access(user: dict[str, Any]) -> bool:
    """Return whether this account has a server-managed staff/founder entitlement.

    Internal access is deliberately separate from Stripe/RevenueCat state. It
    removes Ask Crump's own test quotas without claiming a paid subscription or
    hiding the provider usage that the account owner still funds.
    """
    return not bool(user.get('is_guest')) and str(user.get('internal_tier') or '').lower() in {
        'professional',
        'enterprise',
    }


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


def rolling_window_start_iso(*, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current.astimezone(timezone.utc) - timedelta(seconds=FREE_TEXT_WINDOW_SECONDS)).isoformat()


def _next_free_message_at(
    rows: list[dict[str, Any]],
    *,
    limit: int = FREE_TEXT_MESSAGE_LIMIT,
) -> str | None:
    timestamps: list[datetime] = []
    for row in rows:
        raw = row.get('created_at')
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        timestamps.append(parsed.astimezone(timezone.utc))
    if len(timestamps) < limit:
        return None
    timestamps.sort()
    # If legacy or recently-downgraded activity leaves more than ``limit``
    # events in the rolling window, expiring the oldest event is not enough to
    # create a slot. The first true slot opens when only ``limit - 1`` events
    # remain: the (used - limit + 1)th oldest event must expire.
    boundary_index = len(timestamps) - limit
    return (
        timestamps[boundary_index] + timedelta(seconds=FREE_TEXT_WINDOW_SECONDS)
    ).isoformat()


async def credit_status(db: SupabaseDB, user_id: str) -> dict[str, int]:
    row = await db.select_one(
        'credit_accounts',
        columns='balance,lifetime_granted,lifetime_spent',
        filters={'user_id': eq(user_id)},
    )
    if not row:
        return {'balance': 0, 'lifetimeGranted': 0, 'lifetimeSpent': 0}
    return {
        'balance': max(0, int(row.get('balance') or 0)),
        'lifetimeGranted': max(0, int(row.get('lifetime_granted') or 0)),
        'lifetimeSpent': max(0, int(row.get('lifetime_spent') or 0)),
    }


async def current_usage(
    db: SupabaseDB,
    user: dict[str, Any],
    settings: Settings,
    usage_type: str = 'messages',
) -> dict[str, Any]:
    internal_access = has_internal_access(user)
    tier = tier_name(user)
    free_text = tier == 'free' and usage_type == 'messages'
    rows = await db.select(
        'usage_events',
        columns='id,created_at',
        filters={
            'user_id': eq(user['id']),
            'event_type': eq(usage_type),
            'created_at': (
                gt(rolling_window_start_iso())
                if free_text
                else gte(day_start_iso())
            ),
        },
        order='created_at.asc',
        limit=10000,
    )
    used = len(rows)
    limit = (
        FREE_TEXT_MESSAGE_LIMIT
        if free_text
        else -1
        if internal_access
        else limit_for(settings, tier, usage_type)
    )
    credits = await credit_status(db, user['id'])
    next_available_at = (
        _next_free_message_at(rows)
        if free_text and used >= FREE_TEXT_MESSAGE_LIMIT
        else None
    )
    free_allowance = (
        {
            'limit': FREE_TEXT_MESSAGE_LIMIT,
            'used': used,
            'remaining': max(0, FREE_TEXT_MESSAGE_LIMIT - used),
            'windowKind': 'rolling_24h',
            'windowSeconds': FREE_TEXT_WINDOW_SECONDS,
            'nextAvailableAt': next_available_at,
        }
        if free_text
        else None
    )
    return {
        'tier': tier,
        'used': used,
        'limit': limit,
        'remaining': max(0, limit - used) if limit >= 0 else -1,
        'credits': credits,
        'internalAccess': internal_access,
        'accessSource': 'internal' if internal_access else 'billing',
        'freeMessageAllowance': free_allowance,
        'messageWindowKind': 'rolling_24h' if free_text else 'utc_day',
        'nextAvailableAt': next_available_at,
    }


async def consume_usage(
    db: SupabaseDB,
    user: dict[str, Any],
    settings: Settings,
    usage_type: str = 'messages',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tier = tier_name(user)
    if has_internal_access(user):
        credits = await credit_status(db, user['id'])
        return {
            'eventId': None,
            'tier': tier,
            'used': 0,
            'limit': -1,
            'remaining': -1,
            'paymentSource': 'internal',
            'creditBalance': credits['balance'],
            'creditsSpent': 0,
            'internalAccess': True,
        }
    limit = limit_for(settings, tier, usage_type)
    details = metadata or {}

    result = await db.rpc(
        'consume_usage_event',
        {
            'p_user_id': user['id'],
            'p_event_type': usage_type,
            'p_limit': limit,
            'p_metadata': details,
        },
    )
    row = result[0] if isinstance(result, list) and result else (result or {})
    used = int(row.get('used') or 0)

    if row.get('allowed'):
        credits = await credit_status(db, user['id'])
        return {
            'eventId': row.get('event_id'),
            'tier': tier,
            'used': used,
            'limit': limit,
            'remaining': max(0, limit - used) if limit >= 0 else -1,
            'paymentSource': 'included',
            'creditBalance': credits['balance'],
        }

    # This compatibility helper is allowance-only. Paid message overflow is
    # handled by FeatureService, which issues and verifies the exact quote
    # before it can call the confirmed-spend RPC.
    credits = await credit_status(db, user['id'])
    raise UsageLimitError(used, limit, usage_type, credits['balance'])


async def refund_usage(db: SupabaseDB, user_id: str, event_id: str | None) -> None:
    if not event_id:
        return
    value = str(event_id)
    if value.startswith('credit:'):
        ledger_id = value.split(':', 1)[1].strip()
        if ledger_id:
            await db.rpc(
                'refund_credit_spend',
                {
                    'p_user_id': user_id,
                    'p_ledger_id': ledger_id,
                    'p_metadata': {'reason': 'request_failed'},
                },
            )
        return
    await db.delete('usage_events', filters={'id': eq(value), 'user_id': eq(user_id)})
