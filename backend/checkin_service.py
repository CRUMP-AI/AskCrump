from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ai_service import AIService
from .db import SupabaseDB, eq, lte, lt
from .push_service import PushService
from .security import iso_now, new_uuid
from .usage_service import tier_name

FREQUENCY_HOURS = {
    'occasional': 72,
    'balanced': 36,
    'active': 18,
}
DEFAULT_PREFERENCES: dict[str, Any] = {
    'enabled': False,
    'frequency': 'balanced',
    'quiet_start': 21,
    'quiet_end': 8,
    'timezone': 'America/New_York',
    'notifications_enabled': False,
    'haptics_enabled': True,
    'allow_followups': True,
    'allow_reminders': True,
    'allow_goals': True,
    'allow_encouragement': False,
}


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def sanitize_preferences(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    frequency = str(source.get('frequency') or DEFAULT_PREFERENCES['frequency']).lower()
    if frequency not in FREQUENCY_HOURS:
        frequency = 'balanced'
    timezone_name = str(source.get('timezone') or DEFAULT_PREFERENCES['timezone'])[:100]
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = DEFAULT_PREFERENCES['timezone']

    def hour(name: str, default: int) -> int:
        try:
            return max(0, min(23, int(source.get(name, default))))
        except (TypeError, ValueError):
            return default

    return {
        'enabled': _bool(source.get('enabled'), False),
        'frequency': frequency,
        'quiet_start': hour('quiet_start', 21),
        'quiet_end': hour('quiet_end', 8),
        'timezone': timezone_name,
        'notifications_enabled': _bool(source.get('notifications_enabled'), False),
        'haptics_enabled': _bool(source.get('haptics_enabled'), True),
        'allow_followups': _bool(source.get('allow_followups'), True),
        'allow_reminders': _bool(source.get('allow_reminders'), True),
        'allow_goals': _bool(source.get('allow_goals'), True),
        'allow_encouragement': _bool(source.get('allow_encouragement'), False),
    }


def serialize_preferences(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    return sanitize_preferences(row)


def next_eligible_at(preferences: dict[str, Any], ignored_count: int = 0) -> str:
    base = FREQUENCY_HOURS.get(str(preferences.get('frequency')), 36)
    penalty = min(4.0, 1.0 + max(0, ignored_count) * 0.75)
    jitter = random.uniform(0.9, 1.15)
    return (datetime.now(timezone.utc) + timedelta(hours=base * penalty * jitter)).isoformat()


def in_quiet_hours(preferences: dict[str, Any], now: datetime | None = None) -> bool:
    timezone_name = str(preferences.get('timezone') or 'UTC')
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    start = int(preferences.get('quiet_start', 21))
    end = int(preferences.get('quiet_end', 8))
    if start == end:
        return False
    if start < end:
        return start <= local.hour < end
    return local.hour >= start or local.hour < end


def allowed_categories(preferences: dict[str, Any]) -> list[str]:
    mapping = {
        'allow_followups': 'follow-ups',
        'allow_reminders': 'reminders',
        'allow_goals': 'goals',
        'allow_encouragement': 'encouragement',
    }
    return [label for key, label in mapping.items() if preferences.get(key)]


async def get_preferences(db: SupabaseDB, user_id: str) -> dict[str, Any]:
    row = await db.select_one('check_in_preferences', filters={'user_id': eq(user_id)})
    return serialize_preferences(row)


async def save_preferences(db: SupabaseDB, user_id: str, value: Any) -> dict[str, Any]:
    preferences = sanitize_preferences(value)
    now = iso_now()
    existing = await db.select_one('check_in_preferences', columns='ignored_count,next_eligible_at', filters={'user_id': eq(user_id)})
    ignored_count = int((existing or {}).get('ignored_count') or 0)
    payload = {
        'user_id': user_id,
        **preferences,
        'updated_at': now,
        'next_eligible_at': (existing or {}).get('next_eligible_at') or next_eligible_at(preferences, ignored_count),
    }
    await db.upsert('check_in_preferences', payload, on_conflict='user_id')
    return preferences


async def mark_check_in_responded(db: SupabaseDB, user_id: str, check_in_id: str | None) -> None:
    if not check_in_id:
        return
    now = iso_now()
    await db.update(
        'check_in_events',
        {'status': 'responded', 'responded_at': now, 'updated_at': now},
        filters={'id': eq(check_in_id), 'user_id': eq(user_id), 'status': eq('sent')},
    )
    preferences = await get_preferences(db, user_id)
    await db.update(
        'check_in_preferences',
        {'ignored_count': 0, 'next_eligible_at': next_eligible_at(preferences, 0), 'updated_at': now},
        filters={'user_id': eq(user_id)},
    )


async def _recent_unanswered(db: SupabaseDB, user_id: str) -> dict[str, Any] | None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return await db.select_one(
        'check_in_events',
        filters={'user_id': eq(user_id), 'status': eq('sent'), 'sent_at': f'gte.{cutoff}'},
    )


async def _age_out_unanswered(db: SupabaseDB, user_id: str) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    stale = await db.select(
        'check_in_events',
        columns='id',
        filters={'user_id': eq(user_id), 'status': eq('sent'), 'sent_at': lt(cutoff)},
        limit=20,
    )
    if stale:
        for row in stale:
            await db.update('check_in_events', {'status': 'ignored', 'updated_at': iso_now()}, filters={'id': eq(row['id'])})
    return len(stale)


async def _candidate_chat(db: SupabaseDB, user_id: str) -> dict[str, Any] | None:
    chats = await db.select(
        'user_chats',
        columns='chat_id,title,messages,updated_at,revision,deleted_at',
        filters={'user_id': eq(user_id), 'deleted_at': 'is.null'},
        order='updated_at.desc',
        limit=12,
    )
    now = datetime.now(timezone.utc)
    for chat in chats:
        try:
            updated = datetime.fromisoformat(str(chat.get('updated_at')).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            continue
        age = now - updated
        if age < timedelta(hours=8) or age > timedelta(days=21):
            continue
        messages = chat.get('messages') or []
        if not isinstance(messages, list) or len(messages) < 2:
            continue
        return chat
    return None


async def run_check_ins(
    db: SupabaseDB,
    ai: AIService,
    push: PushService,
    *,
    batch_size: int,
) -> dict[str, Any]:
    now = iso_now()
    rows = await db.select(
        'check_in_preferences',
        columns='*',
        filters={'enabled': eq(True), 'next_eligible_at': lte(now)},
        order='next_eligible_at.asc',
        limit=batch_size,
    )
    summary = {'eligible': len(rows), 'sent': 0, 'skipped': 0, 'quiet': 0, 'unanswered': 0, 'pushDelivered': 0}

    for row in rows:
        user_id = str(row.get('user_id') or '')
        if not user_id:
            continue
        preferences = serialize_preferences(row)
        if in_quiet_hours(preferences):
            summary['quiet'] += 1
            continue

        aged = await _age_out_unanswered(db, user_id)
        ignored_count = int(row.get('ignored_count') or 0) + aged
        if await _recent_unanswered(db, user_id):
            summary['unanswered'] += 1
            continue

        chat = await _candidate_chat(db, user_id)
        if not chat:
            await db.update(
                'check_in_preferences',
                {'next_eligible_at': next_eligible_at(preferences, ignored_count), 'ignored_count': ignored_count, 'updated_at': iso_now()},
                filters={'user_id': eq(user_id)},
            )
            summary['skipped'] += 1
            continue

        categories = allowed_categories(preferences)
        if not categories:
            await db.update(
                'check_in_preferences',
                {'next_eligible_at': next_eligible_at(preferences, ignored_count), 'ignored_count': ignored_count, 'updated_at': iso_now()},
                filters={'user_id': eq(user_id)},
            )
            summary['skipped'] += 1
            continue

        user = await db.select_one(
            'users',
            columns=(
                'id,email,full_name,subscription_tier,subscription_status,'
                'subscription_current_period_end,internal_tier'
            ),
            filters={'id': eq(user_id)},
        ) or {}
        user_settings = await db.select_one('user_settings', columns='assistant_name', filters={'user_id': eq(user_id)}) or {}
        content = await ai.generate_check_in(
            assistant_name=str(user_settings.get('assistant_name') or 'Crump'),
            user_name=str(user.get('full_name') or str(user.get('email') or '').split('@')[0] or 'the user'),
            conversation=chat.get('messages') or [],
            categories=categories,
            user_tier=tier_name(user),
            user_id=user_id,
        )
        if not content:
            await db.update(
                'check_in_preferences',
                {'next_eligible_at': next_eligible_at(preferences, ignored_count), 'ignored_count': ignored_count, 'updated_at': iso_now()},
                filters={'user_id': eq(user_id)},
            )
            summary['skipped'] += 1
            continue

        check_in_id = new_uuid()
        message_id = new_uuid()
        timestamp = iso_now()
        message = {
            'id': message_id,
            'role': 'assistant',
            'content': content,
            'timestamp': timestamp,
            'origin': 'check_in',
            'checkInId': check_in_id,
        }
        append_result = await db.rpc('append_check_in_message', {
            'p_user_id': user_id,
            'p_chat_id': chat['chat_id'],
            'p_message': message,
        })
        append_row = append_result[0] if isinstance(append_result, list) and append_result else (append_result or {})
        if not append_row.get('appended'):
            summary['skipped'] += 1
            continue

        await db.insert('check_in_events', {
            'id': check_in_id,
            'user_id': user_id,
            'chat_id': chat['chat_id'],
            'message_id': message_id,
            'reason': 'contextual_follow_up',
            'content': content,
            'status': 'sent',
            'sent_at': timestamp,
            'created_at': timestamp,
            'updated_at': timestamp,
        })
        await db.update(
            'check_in_preferences',
            {
                'last_check_in_at': timestamp,
                'next_eligible_at': next_eligible_at(preferences, ignored_count),
                'ignored_count': ignored_count,
                'updated_at': timestamp,
            },
            filters={'user_id': eq(user_id)},
        )
        if preferences.get('notifications_enabled'):
            push_result = await push.send_user(
                db,
                user_id,
                title=str(user_settings.get('assistant_name') or 'Crump'),
                body=content,
                data={
                    'type': 'check_in',
                    'chatId': chat['chat_id'],
                    'checkInId': check_in_id,
                },
            )
            summary['pushDelivered'] += push_result.delivered
        summary['sent'] += 1
    return summary
