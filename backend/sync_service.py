from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from urllib.parse import urlparse

from .db import SupabaseDB, eq, gt
from .security import iso_now, normalize_chat_id


ALLOWED_SETTINGS = {
    'assistant_name',
    'work_mode',
    'work_start',
    'work_end',
    'preferences',
}
MAX_MESSAGES_PER_CHAT = 1000
MAX_MESSAGE_CHARS = 100_000
MAX_CHAT_TEXT_CHARS = 1_500_000
MAX_IMAGE_DATA_URI_CHARS = 2_500_000
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def parse_datetime(value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(value, (int, float)):
        # Frontend timestamps are normally milliseconds.
        if value > 10_000_000_000:
            value = value / 1000
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return fallback or datetime.now(timezone.utc)


def safe_client_time(value: Any) -> str:
    now = datetime.now(timezone.utc)
    parsed = parse_datetime(value, now)
    # Prevent a bad device clock from permanently winning last-write-wins.
    if parsed > now + timedelta(minutes=5):
        parsed = now
    if parsed < datetime(2000, 1, 1, tzinfo=timezone.utc):
        parsed = now
    return parsed.isoformat()


def safe_int(value: Any, default: int = 1, minimum: int = 1, maximum: int = 9_223_372_036_854_775_807) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        number = default
    return max(minimum, min(maximum, number))


def clean_text(value: Any, maximum: int) -> str:
    return CONTROL_CHARS.sub('', str(value or '')).strip()[:maximum]


def safe_image_url(value: Any) -> str | None:
    url = str(value or '').strip()
    if not url:
        return None
    if url.startswith('data:image/'):
        return url[:MAX_IMAGE_DATA_URI_CHARS] if len(url) <= MAX_IMAGE_DATA_URI_CHARS else None
    parsed = urlparse(url)
    if parsed.scheme == 'https' and parsed.netloc:
        return url[:4000]
    return None


def sanitize_message(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    role = str(item.get('role') or '').lower()
    if role not in {'user', 'assistant'}:
        return None
    content = clean_text(item.get('content'), MAX_MESSAGE_CHARS)
    image_url = safe_image_url(item.get('imageUrl') or item.get('image_url'))
    if not content and not image_url:
        return None

    message: dict[str, Any] = {
        'role': role,
        'content': content,
        'timestamp': safe_client_time(item.get('timestamp')),
    }
    message_id = clean_text(item.get('id'), 100)
    if message_id:
        message['id'] = message_id
    if image_url:
        message['imageUrl'] = image_url
        image_prompt = clean_text(item.get('imagePrompt') or item.get('image_prompt'), 4000)
        if image_prompt:
            message['imagePrompt'] = image_prompt

    delivery_status = clean_text(item.get('deliveryStatus') or item.get('delivery_status'), 30).lower()
    if role == 'user' and delivery_status in {'sending', 'queued', 'delivered', 'seen', 'failed'}:
        message['deliveryStatus'] = delivery_status
    reply_status = clean_text(item.get('replyStatus') or item.get('reply_status'), 30).lower()
    if role == 'user' and reply_status in {'pending', 'processing', 'replied', 'failed'}:
        message['replyStatus'] = reply_status
    for source, target in (
        ('deliveryUpdatedAt', 'deliveryUpdatedAt'),
        ('deliveredAt', 'deliveredAt'),
        ('seenAt', 'seenAt'),
    ):
        if item.get(source):
            message[target] = safe_client_time(item.get(source))
    for source, target in (
        ('inReplyTo', 'inReplyTo'),
        ('checkInId', 'checkInId'),
    ):
        value = clean_text(item.get(source), 100)
        if value:
            message[target] = value
    origin = clean_text(item.get('origin'), 30).lower()
    if origin in {'reply', 'check_in', 'welcome'}:
        message['origin'] = origin
    reply_error = clean_text(item.get('replyError') or item.get('reply_error'), 500)
    if role == 'user' and reply_error:
        message['replyError'] = reply_error

    files = item.get('files')
    if isinstance(files, list):
        safe_files = []
        for file in files[:4]:
            if not isinstance(file, dict):
                continue
            name = clean_text(file.get('name'), 255)
            media_type = clean_text(file.get('type'), 100).lower()
            if name or media_type:
                safe_files.append({'name': name, 'type': media_type})
        if safe_files:
            message['files'] = safe_files
    return message


def sanitize_messages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    total_chars = 0
    # Keep the most recent valid messages while maintaining chronological order.
    for item in reversed(value[-MAX_MESSAGES_PER_CHAT:]):
        message = sanitize_message(item)
        if not message:
            continue
        size = len(json.dumps(message, ensure_ascii=False, separators=(',', ':')))
        if total_chars + size > MAX_CHAT_TEXT_CHARS:
            break
        result.append(message)
        total_chars += size
    result.reverse()
    return result


def sanitize_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    if 'assistant_name' in value:
        result['assistant_name'] = clean_text(value.get('assistant_name'), 80) or 'Crump'
    for field in ('work_mode',):
        if field in value:
            result[field] = bool(value.get(field))
    for field, default in (('work_start', 9), ('work_end', 17)):
        if field in value:
            result[field] = safe_int(value.get(field), default=default, minimum=0, maximum=23)
    preferences = value.get('preferences')
    if isinstance(preferences, dict):
        try:
            encoded = json.dumps(preferences, ensure_ascii=False, separators=(',', ':'))
            if len(encoded.encode('utf-8')) <= 32_000:
                result['preferences'] = preferences
        except (TypeError, ValueError):
            pass
    return result


def serialize_chat(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': row.get('chat_id'),
        'chat_id': row.get('chat_id'),
        'title': row.get('title') or 'New conversation',
        'messages': row.get('messages') or [],
        'createdAt': row.get('created_at'),
        'created_at': row.get('created_at'),
        'updatedAt': row.get('updated_at'),
        'updated_at': row.get('updated_at'),
        'deletedAt': row.get('deleted_at'),
        'deleted_at': row.get('deleted_at'),
        'revision': safe_int(row.get('revision')),
    }


async def pull_sync(db: SupabaseDB, user_id: str, since: str | None = None) -> dict[str, Any]:
    filters = {'user_id': eq(user_id)}
    if since:
        since_dt = parse_datetime(since, datetime(1970, 1, 1, tzinfo=timezone.utc))
        now = datetime.now(timezone.utc)
        if since_dt > now:
            since_dt = now
        filters['updated_at'] = gt(since_dt.isoformat())

    chats = await db.select(
        'user_chats',
        columns='chat_id,title,messages,created_at,updated_at,deleted_at,revision',
        filters=filters,
        order='updated_at.asc',
        limit=1000,
    )
    settings = await db.select_one('user_settings', filters={'user_id': eq(user_id)})
    return {
        'chats': [serialize_chat(chat) for chat in chats],
        'settings': settings,
    }


async def push_sync(db: SupabaseDB, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    incoming = payload.get('chats') or []
    deleted = payload.get('deletedChats') or payload.get('deleted_chats') or []
    if not isinstance(incoming, list):
        incoming = []
    if not isinstance(deleted, list):
        deleted = []
    accepted: list[str] = []
    ignored: list[str] = []

    normalized: list[dict[str, Any]] = []
    for item in incoming[:500]:
        if not isinstance(item, dict):
            continue
        chat_id = normalize_chat_id(str(item.get('chat_id') or item.get('id') or ''))
        updated_at = safe_client_time(item.get('updated_at') or item.get('updatedAt'))
        created_at = safe_client_time(item.get('created_at') or item.get('createdAt') or updated_at)
        deleted_value = item.get('deleted_at') or item.get('deletedAt')
        normalized.append({
            'user_id': user_id,
            'chat_id': chat_id,
            'title': clean_text(item.get('title'), 300) or 'New conversation',
            'messages': sanitize_messages(item.get('messages')),
            'created_at': created_at,
            'updated_at': updated_at,
            'deleted_at': safe_client_time(deleted_value) if deleted_value else None,
            'revision': safe_int(item.get('revision')),
        })

    for item in deleted[:500]:
        if isinstance(item, str):
            item = {'id': item}
        if not isinstance(item, dict):
            continue
        chat_id = normalize_chat_id(str(item.get('chat_id') or item.get('id') or ''))
        deleted_at = safe_client_time(item.get('deleted_at') or item.get('deletedAt'))
        normalized.append({
            'user_id': user_id,
            'chat_id': chat_id,
            'title': 'Deleted conversation',
            'messages': [],
            'created_at': deleted_at,
            'updated_at': deleted_at,
            'deleted_at': deleted_at,
            'revision': safe_int(item.get('revision')),
        })

    # The database function performs compare-and-apply atomically, preventing two
    # devices from racing between a SELECT and a later UPSERT.
    for chat in normalized:
        result = await db.rpc('apply_chat_sync', {
            'p_user_id': user_id,
            'p_chat_id': chat['chat_id'],
            'p_title': chat['title'],
            'p_messages': chat['messages'],
            'p_created_at': chat['created_at'],
            'p_updated_at': chat['updated_at'],
            'p_deleted_at': chat['deleted_at'],
            'p_revision': chat['revision'],
        })
        row = result[0] if isinstance(result, list) and result else (result or {})
        if row.get('accepted'):
            accepted.append(chat['chat_id'])
        else:
            ignored.append(chat['chat_id'])

    settings = sanitize_settings(payload.get('settings'))
    if settings:
        settings.update({'user_id': user_id, 'updated_at': iso_now()})
        await db.upsert('user_settings', settings, on_conflict='user_id')

    return {'accepted': accepted, 'ignored': ignored}
