from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .db import SupabaseDB, eq, gte


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
    return str(user.get('internal_tier') or '').lower() in {'professional', 'enterprise'}


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
    limit = -1 if internal_access else limit_for(settings, tier, usage_type)
    credits = await credit_status(db, user['id'])
    return {
        'tier': tier,
        'used': used,
        'limit': limit,
        'remaining': max(0, limit - used) if limit >= 0 else -1,
        'credits': credits,
        'internalAccess': internal_access,
        'accessSource': 'internal' if internal_access else 'billing',
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

    # Once the included allowance is exhausted, one durable Crump Credit buys
    # one request. This stays intentionally simple and predictable for users.
    credit_result = await db.rpc(
        'spend_credits',
        {
            'p_user_id': user['id'],
            'p_amount': 1,
            'p_reason': f'{usage_type}_overflow',
            'p_metadata': details,
        },
    )
    credit_row = (
        credit_result[0]
        if isinstance(credit_result, list) and credit_result
        else (credit_result or {})
    )
    credit_balance = max(0, int(credit_row.get('balance') or 0))
    if not credit_row.get('allowed'):
        raise UsageLimitError(used, limit, usage_type, credit_balance)

    ledger_id = credit_row.get('ledger_id')
    return {
        # Keep backward compatibility with callers that refund by eventId.
        # refund_usage recognizes the "credit:" prefix and restores the spend.
        'eventId': f'credit:{ledger_id}' if ledger_id else None,
        'tier': tier,
        'used': used,
        'limit': limit,
        'remaining': 0,
        'paymentSource': 'credits',
        'creditBalance': credit_balance,
        'creditsSpent': 1,
    }


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
