"""Authenticated private file endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth_service import authenticate_request
from ..db import eq
from ..file_service import FileServiceError
from ..runtime import db, files, settings
from ..security import normalize_chat_id

router = APIRouter(prefix='/api/files', tags=['files'])


def failure(exc: FileServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={'success': False, 'error': exc.message, 'code': exc.code},
    )


@router.post('/sign-upload')
async def sign_upload(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Invalid upload request.'},
        )
    try:
        result = await files.create_upload(
            user_id=auth.user['id'],
            filename=str(payload.get('name') or ''),
            mime_type=str(payload.get('type') or ''),
            size_bytes=int(payload.get('size') or 0),
            chat_id=str(payload.get('chatId') or '') or None,
            message_id=str(payload.get('messageId') or '') or None,
        )
        return {'success': True, **result}
    except FileServiceError as exc:
        return failure(exc)


@router.post('/{file_id}/complete')
async def complete(file_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        normalized = normalize_chat_id(file_id)
        item = await files.complete_upload(user_id=auth.user['id'], file_id=normalized)
        return {'success': True, 'file': item}
    except FileServiceError as exc:
        return failure(exc)


@router.get('/chat/{chat_id}')
async def chat_files(chat_id: str, request: Request):
    """Return ready private-file references for one owned conversation.

    This is primarily a 5.2 compatibility bridge for messages synchronized by
    5.0/5.1, whose file arrays retained names/types but lost durable file IDs.
    The response never exposes storage paths or service-role credentials.
    """
    auth = await authenticate_request(request, db, settings)
    normalized_chat = normalize_chat_id(chat_id)
    rows = await db.select(
        'user_files',
        filters={
            'user_id': eq(auth.user['id']),
            'chat_id': eq(normalized_chat),
            'status': eq('ready'),
            'deleted_at': 'is.null',
        },
        order='created_at.asc',
        limit=100,
    )
    return {'success': True, 'files': [files.public_file(row) for row in rows]}


@router.get('/{file_id}/content')
async def content(file_id: str, request: Request, download: int = 0):
    auth = await authenticate_request(request, db, settings)
    try:
        normalized = normalize_chat_id(file_id)
        row = await files.get_owned(user_id=auth.user['id'], file_id=normalized)
        url = await files.signed_url(row=row, expires_in=600, download=bool(download))
        if not url:
            raise FileServiceError('Could not open the file.', 503, 'SIGNED_URL_FAILED')
        return RedirectResponse(url=url, status_code=302)
    except FileServiceError as exc:
        return failure(exc)


@router.delete('/{file_id}')
async def delete(file_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        await files.soft_delete(
            user_id=auth.user['id'],
            file_id=normalize_chat_id(file_id),
        )
        return {'success': True}
    except FileServiceError as exc:
        return failure(exc)
