"""Private file storage for Ask Crump 5.0.

The browser never receives the Supabase service-role key. Uploads use short-lived
signed upload URLs and downloads use short-lived signed read URLs. Metadata is
owned by the authenticated Ask Crump account in ``user_files``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import mimetypes
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx

from .config import Settings
from .db import SupabaseDB, eq
from .security import normalize_chat_id


ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif',
    'video/mp4', 'video/webm',
    'application/pdf', 'application/epub+zip',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain', 'text/markdown', 'text/csv', 'text/tab-separated-values',
    'application/json', 'text/html', 'application/rtf',
}
EXTENSION_MIME = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
    '.gif': 'image/gif', '.heic': 'image/heic', '.heif': 'image/heif', '.pdf': 'application/pdf',
    '.mp4': 'video/mp4', '.webm': 'video/webm', '.epub': 'application/epub+zip',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.txt': 'text/plain', '.md': 'text/markdown', '.csv': 'text/csv', '.tsv': 'text/tab-separated-values',
    '.json': 'application/json', '.html': 'text/html', '.htm': 'text/html', '.rtf': 'application/rtf',
}


@dataclass(slots=True)
class FileServiceError(RuntimeError):
    message: str
    status_code: int = 400
    code: str = 'FILE_ERROR'

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class FileService:
    def __init__(self, settings: Settings, db: SupabaseDB) -> None:
        self.settings = settings
        self.db = db
        self.bucket = settings.storage_bucket

    @property
    def storage_url(self) -> str:
        return f"{self.settings.supabase_url}/storage/v1"

    @property
    def headers(self) -> dict[str, str]:
        key = self.settings.supabase_service_key
        return {'apikey': key, 'Authorization': f'Bearer {key}'}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def clean_filename(value: str) -> str:
        name = str(value or 'file').split('/')[-1].split('\\')[-1]
        name = re.sub(r'[\x00-\x1f\x7f]+', '', name).strip()
        name = re.sub(r'[^A-Za-z0-9._()\- ]+', '_', name)
        name = re.sub(r'\s+', ' ', name).strip(' .')
        return (name or 'file')[:180]

    @staticmethod
    def _extension(name: str) -> str:
        lowered = name.lower()
        for extension in sorted(EXTENSION_MIME, key=len, reverse=True):
            if lowered.endswith(extension):
                return extension
        return ''

    def normalized_mime(self, filename: str, incoming: str | None) -> str:
        raw = str(incoming or '').split(';', 1)[0].strip().lower()
        ext = self._extension(filename)
        if raw in {'', 'application/octet-stream'}:
            raw = EXTENSION_MIME.get(ext) or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        if raw not in ALLOWED_MIME_TYPES:
            raise FileServiceError('That file type is not supported yet.', 415, 'UNSUPPORTED_FILE_TYPE')
        return raw

    def validate_upload(self, *, filename: str, mime_type: str | None, size_bytes: int) -> tuple[str, str]:
        name = self.clean_filename(filename)
        mime = self.normalized_mime(name, mime_type)
        size = int(size_bytes or 0)
        if size <= 0:
            raise FileServiceError('The file is empty.', 400, 'EMPTY_FILE')
        type_limit = self.settings.max_upload_bytes
        if mime.startswith('image/'):
            type_limit = min(type_limit, 25 * 1024 * 1024)
        elif mime.startswith('video/'):
            type_limit = min(type_limit, 90 * 1024 * 1024)
        elif mime == 'application/pdf':
            type_limit = min(type_limit, 50 * 1024 * 1024)
        elif mime in {
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }:
            type_limit = min(type_limit, 30 * 1024 * 1024)
        else:
            type_limit = min(type_limit, 20 * 1024 * 1024)
        if size > type_limit:
            mb = max(1, type_limit // (1024 * 1024))
            raise FileServiceError(f'This file type must be {mb} MB or smaller.', 413, 'FILE_TOO_LARGE')
        return name, mime

    def _path(self, user_id: str, file_id: str, filename: str) -> str:
        suffix = self._extension(filename) or ''
        return f"{user_id}/{file_id}{suffix}"

    async def _storage_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                f"{self.storage_url}/{path.lstrip('/')}",
                headers={**self.headers, 'Content-Type': 'application/json'},
                json=payload,
            )
        if response.status_code >= 400:
            raise FileServiceError('Private file storage is temporarily unavailable.', 503, 'STORAGE_ERROR')
        if not response.content:
            return {}
        return response.json()

    async def create_upload(
        self,
        *,
        user_id: str,
        filename: str,
        mime_type: str | None,
        size_bytes: int,
        chat_id: str | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        name, mime = self.validate_upload(filename=filename, mime_type=mime_type, size_bytes=size_bytes)
        file_id = str(uuid4())
        storage_path = self._path(user_id, file_id, name)
        row = {
            'id': file_id,
            'user_id': user_id,
            'chat_id': normalize_chat_id(chat_id) if chat_id else None,
            'message_id': normalize_chat_id(message_id) if message_id else None,
            'storage_path': storage_path,
            'file_name': name,
            'mime_type': mime,
            'size_bytes': int(size_bytes),
            'kind': 'upload',
            'status': 'pending',
            'metadata': {},
            'updated_at': self._now(),
        }
        await self.db.insert('user_files', row)

        encoded = quote(storage_path, safe='/')
        signed = await self._storage_json('POST', f'object/upload/sign/{self.bucket}/{encoded}', payload={})
        upload_url = str(signed.get('url') or signed.get('signedURL') or '')
        token = str(signed.get('token') or '')
        if upload_url and upload_url.startswith('/'):
            upload_url = f"{self.storage_url}{upload_url}"
        if not upload_url:
            await self.db.update('user_files', {'status': 'failed', 'updated_at': self._now()}, filters={'id': eq(file_id), 'user_id': eq(user_id)})
            raise FileServiceError('Could not prepare the upload.', 503, 'UPLOAD_SIGNING_FAILED')
        direct_storage = self.settings.supabase_url.replace('.supabase.co', '.storage.supabase.co')
        return {
            'file': self.public_file(row),
            'uploadUrl': upload_url,
            'uploadToken': token or None,
            'uploadPath': storage_path,
            'uploadBucket': self.bucket,
            'resumableUrl': f'{direct_storage}/storage/v1/upload/resumable',
        }

    async def complete_upload(self, *, user_id: str, file_id: str) -> dict[str, Any]:
        row = await self.get_owned(user_id=user_id, file_id=file_id, include_pending=True)
        encoded = quote(row['storage_path'], safe='/')
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.storage_url}/object/info/{self.bucket}/{encoded}",
                headers=self.headers,
            )
        if response.status_code >= 400:
            raise FileServiceError('The upload has not finished yet.', 409, 'UPLOAD_INCOMPLETE')
        info = response.json() if response.content else {}
        actual_size = int((info.get('metadata') or {}).get('size') or info.get('size') or row.get('size_bytes') or 0)
        updates = {'status': 'ready', 'updated_at': self._now()}
        if actual_size:
            updates['size_bytes'] = actual_size
        updated = await self.db.update('user_files', updates, filters={'id': eq(file_id), 'user_id': eq(user_id)})
        return self.public_file((updated or [row])[0])

    async def get_owned(self, *, user_id: str, file_id: str, include_pending: bool = False) -> dict[str, Any]:
        row = await self.db.select_one('user_files', filters={'id': eq(file_id), 'user_id': eq(user_id), 'deleted_at': 'is.null'})
        if not row or (not include_pending and row.get('status') != 'ready'):
            raise FileServiceError('File not found.', 404, 'FILE_NOT_FOUND')
        return row

    async def resolve_many(self, *, user_id: str, file_ids: list[str], limit: int = 10) -> list[dict[str, Any]]:
        unique: list[str] = []
        for value in file_ids:
            try:
                normalized = normalize_chat_id(str(value))
            except Exception:
                continue
            if normalized not in unique:
                unique.append(normalized)
        if not unique:
            return []
        if len(unique) > limit:
            raise FileServiceError(f'Attach up to {limit} files to one message.', 400, 'TOO_MANY_FILES')
        rows = []
        for file_id in unique:
            rows.append(await self.get_owned(user_id=user_id, file_id=file_id))
        return rows

    async def signed_url(self, *, row: dict[str, Any], expires_in: int = 600, download: bool = False) -> str:
        encoded = quote(str(row['storage_path']), safe='/')
        payload: dict[str, Any] = {'expiresIn': max(30, min(3600, int(expires_in)))}
        data = await self._storage_json('POST', f'object/sign/{self.bucket}/{encoded}', payload=payload)
        url = str(data.get('signedURL') or data.get('signedUrl') or '')
        if url.startswith('/'):
            url = f"{self.settings.supabase_url}/storage/v1{url}"
        if download and url:
            # Supabase's signing endpoint signs the object URL, while the
            # browser-download instruction belongs on the returned URL. Sending
            # ``download`` in the signing JSON is silently ignored and leaves
            # Safari free to preview playable media instead of saving it.
            filename = quote(self.clean_filename(row.get('file_name') or 'download'), safe='')
            separator = '&' if '?' in url else '?'
            url = f'{url}{separator}download={filename}'
        return url

    async def download_bytes(self, *, row: dict[str, Any], max_bytes: int | None = None) -> bytes:
        encoded = quote(str(row['storage_path']), safe='/')
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0), follow_redirects=True) as client:
            response = await client.get(f"{self.storage_url}/object/{self.bucket}/{encoded}", headers=self.headers)
        if response.status_code >= 400:
            raise FileServiceError('Could not read the file.', 503, 'FILE_READ_FAILED')
        data = response.content
        limit = int(max_bytes or self.settings.max_upload_bytes)
        if len(data) > limit:
            raise FileServiceError('The file is too large to process in this operation.', 413, 'FILE_PROCESSING_LIMIT')
        return data

    async def store_bytes(
        self,
        *,
        user_id: str,
        data: bytes,
        filename: str,
        mime_type: str,
        kind: str,
        chat_id: str | None = None,
        message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        name = self.clean_filename(filename)
        mime = self.normalized_mime(name, mime_type)
        generated_limit = (
            self.settings.max_generated_video_bytes
            if kind == 'generated_video'
            else self.settings.max_upload_bytes
        )
        if len(data) > generated_limit:
            raise FileServiceError('Generated file exceeds the storage limit.', 413, 'GENERATED_FILE_TOO_LARGE')
        stable_file_id = normalize_chat_id(file_id) if file_id else None
        if stable_file_id:
            existing = await self.db.select_one(
                'user_files',
                filters={
                    'id': eq(stable_file_id),
                    'user_id': eq(user_id),
                    'deleted_at': 'is.null',
                },
            )
            if existing:
                return existing
        resolved_file_id = stable_file_id or str(uuid4())
        storage_path = self._path(user_id, resolved_file_id, name)
        encoded = quote(storage_path, safe='/')
        headers = {**self.headers, 'x-upsert': 'true' if stable_file_id else 'false'}
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            response = await client.post(
                f"{self.storage_url}/object/{self.bucket}/{encoded}",
                headers=headers,
                data={'cacheControl': '3600'},
                files={'file': (name, data, mime)},
            )
        if response.status_code >= 400:
            raise FileServiceError('Could not save the generated file.', 503, 'STORAGE_WRITE_FAILED')
        row = {
            'id': resolved_file_id,
            'user_id': user_id,
            'chat_id': normalize_chat_id(chat_id) if chat_id else None,
            'message_id': normalize_chat_id(message_id) if message_id else None,
            'storage_path': storage_path,
            'file_name': name,
            'mime_type': mime,
            'size_bytes': len(data),
            'kind': kind,
            'status': 'ready',
            'metadata': metadata or {},
            'updated_at': self._now(),
        }
        if stable_file_id:
            row['deleted_at'] = None
            stored = await self.db.upsert('user_files', row, on_conflict='id')
        else:
            stored = await self.db.insert('user_files', row)
        return stored[0] if isinstance(stored, list) and stored else row

    async def soft_delete(self, *, user_id: str, file_id: str) -> None:
        await self.get_owned(user_id=user_id, file_id=file_id, include_pending=True)
        await self.db.update('user_files', {'deleted_at': self._now(), 'updated_at': self._now()}, filters={'id': eq(file_id), 'user_id': eq(user_id)})

    async def restore_soft_deleted(self, *, user_id: str, file_id: str) -> dict[str, Any]:
        """Restore one owner-checked soft-deleted private file."""
        row = await self.db.select_one(
            'user_files',
            filters={'id': eq(file_id), 'user_id': eq(user_id)},
        )
        if not row:
            raise FileServiceError('File not found.', 404, 'FILE_NOT_FOUND')
        if row.get('deleted_at') is None:
            return row
        updated = await self.db.update(
            'user_files',
            {'deleted_at': None, 'updated_at': self._now()},
            filters={'id': eq(file_id), 'user_id': eq(user_id)},
        )
        return (updated or [{**row, 'deleted_at': None}])[0]

    async def hard_delete(self, *, user_id: str, file_id: str) -> None:
        """Permanently remove an owned file through Storage API, then its metadata row."""
        row = await self.db.select_one(
            'user_files',
            filters={'id': eq(file_id), 'user_id': eq(user_id)},
        )
        if not row:
            raise FileServiceError('File not found.', 404, 'FILE_NOT_FOUND')
        storage_path = str(row.get('storage_path') or '').strip()
        if storage_path:
            await self._storage_json(
                'DELETE',
                f'object/{self.bucket}',
                payload={'prefixes': [storage_path]},
                timeout=60.0,
            )
        await self.db.delete(
            'user_files',
            filters={'id': eq(file_id), 'user_id': eq(user_id)},
        )

    @staticmethod
    def _account_storage_prefix(*, user_id: str, owner_prefix: str | None) -> str:
        """Return the one canonical UUID directory an account purge may touch."""
        try:
            raw_user_id = str(user_id)
            canonical_user_id = str(UUID(raw_user_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise FileServiceError(
                'Account file cleanup received an invalid owner identifier.',
                400,
                'INVALID_STORAGE_OWNER',
            ) from exc
        if raw_user_id != canonical_user_id:
            raise FileServiceError(
                'Account file cleanup requires a canonical owner identifier.',
                400,
                'INVALID_STORAGE_OWNER',
            )
        expected = f'{canonical_user_id}/'
        if owner_prefix is not None and str(owner_prefix) != expected:
            raise FileServiceError(
                'Account file cleanup prefix did not match the owner.',
                400,
                'STORAGE_PREFIX_MISMATCH',
            )
        return expected

    @staticmethod
    def _owned_storage_entry_path(
        *,
        directory: str,
        raw_name: Any,
        owner_prefix: str,
    ) -> str:
        """Resolve one Storage listing entry without permitting prefix escape."""
        name = str(raw_name or '').strip('/')
        if not name or '\\' in name or '\x00' in name:
            raise FileServiceError(
                'Private file cleanup returned an unsafe object path.',
                503,
                'STORAGE_PREFIX_ESCAPE',
            )
        candidate = name if name == directory or name.startswith(f'{directory}/') else f'{directory}/{name}'
        segments = candidate.split('/')
        if any(segment in {'', '.', '..'} for segment in segments):
            raise FileServiceError(
                'Private file cleanup returned an unsafe object path.',
                503,
                'STORAGE_PREFIX_ESCAPE',
            )
        if not candidate.startswith(owner_prefix):
            raise FileServiceError(
                'Private file cleanup returned an object outside the account prefix.',
                503,
                'STORAGE_PREFIX_ESCAPE',
            )
        return candidate

    async def purge_owner_prefix(
        self,
        *,
        user_id: str,
        owner_prefix: str | None = None,
        bucket: str | None = None,
    ) -> dict[str, Any]:
        """Recursively and permanently purge one account's exact Storage prefix.

        The Storage API lists one directory level at a time. Every deletion is
        followed by another offset-zero listing so pagination cannot skip rows
        that shifted after the previous batch. Database metadata is not used:
        this intentionally catches retired versions and untracked orphan files.
        """
        exact_prefix = self._account_storage_prefix(
            user_id=user_id,
            owner_prefix=owner_prefix,
        )
        resolved_bucket = str(bucket or self.bucket).strip()
        if resolved_bucket != self.bucket:
            raise FileServiceError(
                'Account file cleanup bucket did not match private storage.',
                400,
                'STORAGE_BUCKET_MISMATCH',
            )
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', resolved_bucket):
            raise FileServiceError(
                'Account file cleanup received an invalid storage bucket.',
                400,
                'INVALID_STORAGE_BUCKET',
            )

        root_directory = exact_prefix[:-1]
        bucket_path = quote(resolved_bucket, safe='')
        request_count = 0
        deleted_count = 0

        async def list_directory(directory: str) -> list[dict[str, Any]]:
            nonlocal request_count
            request_count += 1
            if request_count > 10000:
                raise FileServiceError(
                    'Private file cleanup exceeded its safe traversal limit.',
                    503,
                    'STORAGE_PURGE_LIMIT',
                )
            data = await self._storage_json(
                'POST',
                f'object/list/{bucket_path}',
                payload={
                    'prefix': directory,
                    'limit': 1000,
                    'offset': 0,
                    'sortBy': {'column': 'name', 'order': 'asc'},
                },
                timeout=60.0,
            )
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise FileServiceError(
                    'Private file storage returned an invalid directory listing.',
                    503,
                    'STORAGE_LIST_INVALID',
                )
            return data

        async def purge_directory(directory: str, *, depth: int) -> None:
            nonlocal deleted_count, request_count
            if depth > 64:
                raise FileServiceError(
                    'Private file cleanup exceeded its safe folder depth.',
                    503,
                    'STORAGE_PURGE_DEPTH',
                )
            prior_signature: tuple[tuple[str, bool], ...] | None = None
            stagnant_rounds = 0
            while True:
                entries = await list_directory(directory)
                if not entries:
                    return

                directories: set[str] = set()
                files: set[str] = set()
                for entry in entries:
                    object_path = self._owned_storage_entry_path(
                        directory=directory,
                        raw_name=entry.get('name'),
                        owner_prefix=exact_prefix,
                    )
                    is_directory = not entry.get('id') and entry.get('metadata') is None
                    if is_directory:
                        directories.add(object_path)
                    else:
                        files.add(object_path)

                signature = tuple(
                    sorted(
                        [(path, True) for path in directories]
                        + [(path, False) for path in files]
                    )
                )
                if signature == prior_signature:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0
                if stagnant_rounds >= 3:
                    raise FileServiceError(
                        'Private file cleanup could not make progress.',
                        503,
                        'STORAGE_PURGE_STALLED',
                    )
                prior_signature = signature

                for child in sorted(directories):
                    await purge_directory(child, depth=depth + 1)

                ordered_files = sorted(files)
                for start in range(0, len(ordered_files), 1000):
                    batch = ordered_files[start:start + 1000]
                    if not batch:
                        continue
                    request_count += 1
                    if request_count > 10000:
                        raise FileServiceError(
                            'Private file cleanup exceeded its safe request limit.',
                            503,
                            'STORAGE_PURGE_LIMIT',
                        )
                    await self._storage_json(
                        'DELETE',
                        f'object/{bucket_path}',
                        payload={'prefixes': batch},
                        timeout=60.0,
                    )
                    deleted_count += len(batch)

        await purge_directory(root_directory, depth=0)
        remaining = await list_directory(root_directory)
        if remaining:
            raise FileServiceError(
                'Private file cleanup could not verify an empty account prefix.',
                503,
                'STORAGE_PREFIX_NOT_EMPTY',
            )
        return {
            'deletedCount': deleted_count,
            'empty': True,
            'ownerPrefix': exact_prefix,
        }

    @staticmethod
    def public_file(row: dict[str, Any]) -> dict[str, Any]:
        file_id = str(row.get('id') or '')
        return {
            'id': file_id,
            'name': row.get('file_name') or 'File',
            'type': row.get('mime_type') or 'application/octet-stream',
            'size': int(row.get('size_bytes') or 0),
            'kind': row.get('kind') or 'upload',
            'status': row.get('status') or 'pending',
            'metadata': row.get('metadata') or {},
            'createdAt': row.get('created_at'),
            'updatedAt': row.get('updated_at'),
            'url': f'/api/files/{file_id}/content' if file_id else None,
        }
