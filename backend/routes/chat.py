"""Message acknowledgement and AI response endpoints."""
from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..ai_service import AIServiceError
from ..auth_service import authenticate_request
from ..checkin_service import mark_check_in_responded
from ..db import eq
from ..file_service import FileServiceError
from ..runtime import ai, artifacts, db, files, intelligence, media, settings
from ..schemas import ChatAckRequest
from ..security import iso_now, normalize_chat_id
from ..usage_service import UsageLimitError, consume_usage, refund_usage

router = APIRouter(prefix='/api/chat', tags=['chat'])


@router.post('/ack')
async def chat_ack(payload: ChatAckRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    chat_id = normalize_chat_id(payload.chatId)
    message_id = normalize_chat_id(payload.messageId)
    now = iso_now()
    activity = ai.activity_for(payload.message, payload.fileTypes)
    await db.upsert(
        'message_receipts',
        {
            'user_id': auth.user['id'],
            'chat_id': chat_id,
            'message_id': message_id,
            'delivered_at': now,
            'seen_at': now,
            'activity': activity,
            'updated_at': now,
        },
        on_conflict='user_id,message_id',
    )
    return {
        'success': True,
        'chatId': chat_id,
        'messageId': message_id,
        'deliveredAt': now,
        'seenAt': now,
        'activity': activity,
    }


def _file_ids(payload: dict) -> list[str]:
    values = payload.get('fileRefs') or []
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        value = item.get('id') if isinstance(item, dict) else item
        if value:
            result.append(str(value))
    return result


def _history_file_ids(payload: dict, limit: int = 6) -> list[str]:
    result: list[str] = []
    history = payload.get('history') or []
    if not isinstance(history, list):
        return result
    for item in reversed(history[-24:]):
        if not isinstance(item, dict):
            continue
        values = item.get('fileRefs') or []
        if not isinstance(values, list):
            continue
        for value in reversed(values):
            file_id = value.get('id') if isinstance(value, dict) else value
            if file_id and str(file_id) not in result:
                result.append(str(file_id))
                if len(result) >= limit:
                    return result
    return result


@router.post('')
async def chat(request: Request):
    started = time.perf_counter()
    request_id = request.headers.get('X-Request-ID') or str(uuid4())
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    request_payload = dict(payload) if isinstance(payload, dict) else {}
    original_message = str(request_payload.get('message') or '')

    raw_chat_id = str(request_payload.get('chatId') or '').strip()
    raw_message_id = str(request_payload.get('messageId') or '').strip()
    chat_id = normalize_chat_id(raw_chat_id) if raw_chat_id else None
    message_id = normalize_chat_id(raw_message_id) if raw_message_id else None
    prepared = None
    verifier_used = False

    if chat_id and message_id:
        claim_result = await db.rpc(
            'claim_chat_job',
            {'p_user_id': auth.user['id'], 'p_chat_id': chat_id, 'p_message_id': message_id},
        )
        claim = claim_result[0] if isinstance(claim_result, list) and claim_result else (claim_result or {})
        state = claim.get('job_state') or 'claimed'
        if state == 'completed' and isinstance(claim.get('response_data'), dict):
            return {'success': True, **claim['response_data'], 'cached': True}
        if state == 'busy':
            return JSONResponse(
                status_code=409,
                content={
                    'success': False,
                    'error': 'Crump is already replying to this message.',
                    'message': 'Crump is already replying to this message.',
                    'code': 'REPLY_IN_PROGRESS',
                    'shouldRetry': True,
                    'retryAfter': 3,
                },
            )

    try:
        usage = await consume_usage(
            db,
            auth.user,
            settings,
            'messages',
            {'route': 'chat', 'messageId': message_id},
        )
    except UsageLimitError as exc:
        if message_id:
            await db.update(
                'chat_jobs',
                {'status': 'failed', 'error_code': 'USAGE_LIMIT', 'updated_at': iso_now()},
                filters={'user_id': eq(auth.user['id']), 'message_id': eq(message_id)},
            )
        return JSONResponse(
            status_code=403,
            content={
                'success': False,
                'error': 'Daily message limit reached.',
                'code': 'USAGE_LIMIT',
                'upgradeRequired': True,
                'usage': {'used': exc.used, 'limit': exc.limit, 'remaining': 0},
            },
        )

    try:
        current_file_rows = await files.resolve_many(user_id=auth.user['id'], file_ids=_file_ids(request_payload), limit=10)
        file_rows = current_file_rows
        if not file_rows and media.needs_prior_files(str(request_payload.get('message') or '')):
            file_rows = await files.resolve_many(
                user_id=auth.user['id'],
                file_ids=_history_file_ids(request_payload),
                limit=6,
            )
    except FileServiceError as exc:
        await refund_usage(db, auth.user['id'], usage.get('eventId'))
        return JSONResponse(status_code=exc.status_code, content={'success': False, 'error': exc.message, 'message': exc.message, 'code': exc.code})

    user_settings = await db.select_one('user_settings', filters={'user_id': eq(auth.user['id'])}) or {}
    request_payload['assistantName'] = user_settings.get('assistant_name') or 'Crump'
    request_payload['workMode'] = 'work' if user_settings.get('work_mode') else 'companion'
    request_payload['user'] = {
        'id': auth.user['id'],
        'email': auth.user.get('email'),
        'name': auth.user.get('full_name') or str(auth.user.get('email') or '').split('@')[0] or 'the user',
    }

    # Metadata-only marker lets the 4.4 orchestration recognize a document task.
    if file_rows and not str(request_payload.get('message') or '').strip():
        request_payload['message'] = 'Analyze the attached files carefully.'

    if file_rows:
        request_payload['fileData'] = [
            {'type': row.get('mime_type'), 'name': row.get('file_name')} for row in file_rows
        ]

    requested_artifact = artifacts.detect_request(str(request_payload.get('message') or ''), request_payload.get('artifactFormat'))
    prepared = await intelligence.prepare(auth.user['id'], request_payload)
    request_payload = prepared.payload
    if requested_artifact:
        artifact_note = {
            'source': 'artifact_request',
            'content': (
                f'The user explicitly requested a downloadable {requested_artifact.upper()} artifact. '
                'Write complete, polished source content suitable for direct packaging. Avoid meta commentary about creating the file.'
            ),
        }
        current_context = request_payload.get('relevantContext')
        if isinstance(current_context, list):
            request_payload['relevantContext'] = [*current_context, artifact_note]
        elif current_context:
            request_payload['relevantContext'] = [current_context, artifact_note]
        else:
            request_payload['relevantContext'] = [artifact_note]

    # Office/text files are converted into bounded context server-side. Images and
    # PDFs use the high-detail vision path below when available.
    if file_rows:
        extracted = await media.extract_nonvisual(file_rows)
        if extracted:
            current = request_payload.get('relevantContext')
            if isinstance(current, list):
                current = [*current, {'source': 'uploaded_files', 'content': extracted}]
            elif current:
                current = [current, {'source': 'uploaded_files', 'content': extracted}]
            else:
                current = [{'source': 'uploaded_files', 'content': extracted}]
            request_payload['relevantContext'] = current

    await mark_check_in_responded(
        db,
        auth.user['id'],
        str(request_payload.get('replyToCheckInId') or '') or None,
    )

    try:
        result = None
        if (
            media.is_image_request(str(request_payload.get('message') or ''), str(request_payload.get('creativeTool') or '') or None)
            or media.is_edit_request(str(request_payload.get('message') or ''), file_rows)
        ):
            result = await media.generate_or_edit_image(
                user_id=auth.user['id'],
                payload=request_payload,
                file_rows=file_rows,
                chat_id=chat_id,
                message_id=message_id,
            )
        elif file_rows and media.has_visual_files(file_rows):
            result = await media.understand(payload=request_payload, file_rows=file_rows)

        if result is None:
            # Small image/PDF fallback keeps the proven Anthropic path available if
            # the richer visual route is temporarily unavailable.
            request_payload['fileData'] = await media.legacy_inline_files(file_rows) if file_rows else request_payload.get('fileData')
            result = await ai.chat(request_payload)
    except AIServiceError as exc:
        await refund_usage(db, auth.user['id'], usage.get('eventId'))
        if message_id:
            await db.update(
                'chat_jobs',
                {'status': 'failed', 'error_code': exc.code, 'updated_at': iso_now()},
                filters={'user_id': eq(auth.user['id']), 'message_id': eq(message_id)},
            )
        await intelligence.record_trace(
            user_id=auth.user['id'], request_id=request_id, chat_id=chat_id,
            message_id=message_id, prepared=prepared, model=None,
            latency_ms=int((time.perf_counter() - started) * 1000), status='error',
            error_code=exc.code, verifier_used=False,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                'success': False, 'error': exc.message, 'message': exc.message, 'code': exc.code,
                'shouldRetry': exc.retryable, 'retryAfter': exc.retry_after,
            },
        )

    result = dict(result or {})
    result, verifier_used = await intelligence.verify_answer(
        prepared=prepared,
        question=str(request_payload.get('message') or ''),
        result=result,
    )

    artifact_format = requested_artifact
    if artifact_format:
        try:
            result['artifact'] = await artifacts.create(
                user_id=auth.user['id'],
                markdown=str(result.get('response') or ''),
                format_name=artifact_format,
                chat_id=chat_id,
                message_id=message_id,
                title=str(request_payload.get('artifactTitle') or '').strip() or None,
            )
        except Exception:
            result['artifactError'] = 'Crump wrote the content, but the downloadable file could not be packaged yet.'

    # The API, not an individual browser tab, owns persistence of the AI reply.
    if chat_id and message_id:
        reply_time = iso_now()
        public_files = [files.public_file(row) for row in current_file_rows]
        user_message = {
            'id': message_id,
            'role': 'user',
            'content': original_message[:100_000],
            'timestamp': reply_time,  # DB preserves an existing user's original timestamp.
            'deliveryStatus': 'seen',
            'replyStatus': 'replied',
            'deliveryUpdatedAt': reply_time,
            'seenAt': reply_time,
        }
        if public_files:
            user_message['files'] = public_files
        request_meta = {
            key: request_payload.get(key)
            for key in ('creativeTool', 'imageAspect', 'imageQuality', 'imageUseReference', 'artifactFormat', 'needsSearch', 'taskType')
            if request_payload.get(key) is not None
        }
        if request_meta:
            user_message['requestMeta'] = request_meta
        assistant_message = {
            'id': str(uuid4()),
            'role': 'assistant',
            'content': str(result.get('response') or '')[:100_000],
            'timestamp': reply_time,
            'origin': 'reply',
            'inReplyTo': message_id,
        }
        if result.get('imageUrl'):
            assistant_message['imageUrl'] = result['imageUrl']
            assistant_message['imagePrompt'] = str(result.get('imagePrompt') or '')[:4_000]
        if result.get('imageFile'):
            assistant_message['imageFile'] = result['imageFile']
        if result.get('artifact'):
            assistant_message['artifact'] = result['artifact']

        try:
            persisted = await db.rpc(
                'persist_chat_reply',
                {
                    'p_user_id': auth.user['id'],
                    'p_chat_id': chat_id,
                    'p_title': None,
                    'p_user_message': user_message,
                    'p_assistant_message': assistant_message,
                },
            )
            result['assistantMessage'] = assistant_message
            if isinstance(persisted, list) and persisted:
                result['conversationRevision'] = persisted[0].get('resulting_revision')
                result['conversationUpdatedAt'] = persisted[0].get('resulting_updated_at')
        except Exception:
            await refund_usage(db, auth.user['id'], usage.get('eventId'))
            await db.update(
                'chat_jobs',
                {'status': 'failed', 'error_code': 'CHAT_PERSISTENCE', 'updated_at': iso_now()},
                filters={'user_id': eq(auth.user['id']), 'message_id': eq(message_id)},
            )
            await intelligence.record_trace(
                user_id=auth.user['id'], request_id=request_id, chat_id=chat_id,
                message_id=message_id, prepared=prepared, model=result.get('model'),
                latency_ms=int((time.perf_counter() - started) * 1000), status='persistence_error',
                error_code='CHAT_PERSISTENCE', verifier_used=verifier_used,
            )
            return JSONResponse(
                status_code=503,
                content={
                    'success': False,
                    'error': 'Crump generated a reply but could not save the shared conversation.',
                    'message': 'Crump generated a reply but could not save the shared conversation. Please retry.',
                    'code': 'CHAT_PERSISTENCE', 'shouldRetry': True, 'retryAfter': 2,
                },
            )

    memories_saved = await intelligence.learn_explicit(
        user_id=auth.user['id'], chat_id=chat_id, message_id=message_id,
        message=original_message, enabled=prepared.auto_learn,
    )
    result['intelligence'] = {
        'mode': prepared.effective_mode,
        'requestedMode': prepared.requested_mode,
        'route': prepared.route,
        'plannerUsed': prepared.planner_used,
        'verifierUsed': verifier_used,
        'memoryCount': prepared.memory_count,
        'memoriesSaved': memories_saved,
        'privateChat': prepared.private_chat,
    }

    if message_id:
        await db.update(
            'chat_jobs',
            {'status': 'completed', 'response_data': result, 'error_code': None, 'updated_at': iso_now()},
            filters={'user_id': eq(auth.user['id']), 'message_id': eq(message_id)},
        )

    await intelligence.record_trace(
        user_id=auth.user['id'], request_id=request_id, chat_id=chat_id,
        message_id=message_id, prepared=prepared, model=result.get('model'),
        latency_ms=int((time.perf_counter() - started) * 1000), status='success',
        verifier_used=verifier_used,
    )
    return {'success': True, **result, 'dailyUsage': usage}
