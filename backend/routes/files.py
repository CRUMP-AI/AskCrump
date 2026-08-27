"""Authenticated private file endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth_service import authenticate_request
from ..db import eq
from ..file_service import FileServiceError
from ..product_analytics import artifact_type_for_file, record_product_event
from ..runtime import db, files, settings
from ..security import normalize_chat_id
from ..usage_service import tier_name

router = APIRouter(prefix='/api/files', tags=['files'])

LISTABLE_KINDS = {
    'upload',
    'generated_image',
    'generated_document',
    'generated_video',
    'manuscript_export',
    'project_asset',
}


def failure(exc: FileServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={'success': False, 'error': exc.message, 'code': exc.code},
    )


@router.get('')
async def list_files(request: Request, kind: str = '', limit: int = 100):
    """Return the signed-in account's durable private-file library."""
    auth = await authenticate_request(request, db, settings)
    normalized_kind = str(kind or '').strip().lower()
    if normalized_kind and normalized_kind not in LISTABLE_KINDS:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Invalid file kind.', 'code': 'INVALID_FILE_KIND'},
        )
    filters = {
        'user_id': eq(auth.user['id']),
        'status': eq('ready'),
        'deleted_at': 'is.null',
    }
    if normalized_kind:
        filters['kind'] = eq(normalized_kind)
    rows = await db.select(
        'user_files',
        filters=filters,
        order='created_at.desc',
        limit=max(1, min(int(limit or 100), 200)),
    )
    return {'success': True, 'files': [files.public_file(row) for row in rows]}


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
        if bool(download) and str(row.get('kind') or '').lower() in {
            'generated_document',
            'manuscript_export',
        }:
            artifact_event_id = str(row.get('message_id') or normalized)
            await record_product_event(
                db,
                user_id=auth.user['id'],
                event_name='ArtifactDownloaded',
                event_key=f'artifact-downloaded:{artifact_event_id}',
                request=request,
                plan=tier_name(auth.user),
                artifact_type=artifact_type_for_file(row),
            )
        return RedirectResponse(url=url, status_code=302)
    except FileServiceError as exc:
        return failure(exc)


@router.get('/{file_id}/signed')
async def signed(file_id: str, request: Request):
    """Return a short-lived direct URL for an owned private file.

    Native media saving needs the storage URL itself because the operating-system
    Photos API cannot follow Ask Crump's authenticated application redirect.
    """
    auth = await authenticate_request(request, db, settings)
    try:
        normalized = normalize_chat_id(file_id)
        row = await files.get_owned(user_id=auth.user['id'], file_id=normalized)
        expires_in = 1200
        url = await files.signed_url(row=row, expires_in=expires_in, download=False)
        if not url:
            raise FileServiceError('Could not prepare the file.', 503, 'SIGNED_URL_FAILED')
        return JSONResponse(
            content={
                'success': True,
                'url': url,
                'expiresIn': expires_in,
                'name': row.get('file_name') or 'File',
                'mimeType': row.get('mime_type') or 'application/octet-stream',
            },
            headers={'Cache-Control': 'private, no-store'},
        )
    except FileServiceError as exc:
        return failure(exc)


@router.get('/{file_id}/playback')
async def playback(file_id: str, request: Request):
    """Return a short-lived direct URL for inline playback of an owned video.

    Safari is unreliable when a media element has to follow an authenticated
    application redirect. The browser requests this JSON endpoint with the
    user's session first, then streams the video directly from private storage
    with a time-limited signature.
    """
    auth = await authenticate_request(request, db, settings)
    try:
        normalized = normalize_chat_id(file_id)
        row = await files.get_owned(user_id=auth.user['id'], file_id=normalized)
        mime_type = str(row.get('mime_type') or '').lower()
        if row.get('kind') != 'generated_video' and not mime_type.startswith('video/'):
            raise FileServiceError('That file is not a playable video.', 415, 'NOT_PLAYABLE_VIDEO')
        expires_in = 1200
        url = await files.signed_url(row=row, expires_in=expires_in, download=False)
        if not url:
            raise FileServiceError('Could not prepare video playback.', 503, 'SIGNED_URL_FAILED')
        return JSONResponse(
            content={
                'success': True,
                'url': url,
                'expiresIn': expires_in,
                'mimeType': mime_type or 'video/mp4',
            },
            headers={'Cache-Control': 'private, no-store'},
        )
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
