import asyncio
from types import SimpleNamespace

import pytest

import backend.file_service as file_service_module
from backend.file_service import FileService, FileServiceError


class DummyDB:
    pass


class OwnedFileDB:
    def __init__(self, rows, *, owner_active=True):
        self.rows = [dict(row) for row in rows]
        self.owner_active = owner_active
        self.delete_calls = []
        self.insert_calls = []

    @staticmethod
    def _matches(row, filters):
        for key, value in (filters or {}).items():
            expected = str(value).removeprefix('eq.')
            if str(row.get(key) or '') != expected:
                return False
        return True

    async def select(self, table, *, columns='*', filters=None, limit=None):
        if table == 'users':
            owner_id = str((filters or {}).get('id') or '').removeprefix('eq.')
            rows = [{'id': owner_id}] if self.owner_active else []
            return rows[:limit] if limit is not None else rows
        assert table == 'user_files'
        rows = [dict(row) for row in self.rows if self._matches(row, filters)]
        return rows[:limit] if limit is not None else rows

    async def select_one(self, table, *, columns='*', filters=None):
        rows = await self.select(table, columns=columns, filters=filters, limit=1)
        return rows[0] if rows else None

    async def delete(self, table, *, filters):
        assert table == 'user_files'
        deleted = [dict(row) for row in self.rows if self._matches(row, filters)]
        self.rows = [row for row in self.rows if not self._matches(row, filters)]
        self.delete_calls.append(dict(filters))
        return deleted

    async def insert(self, table, payload):
        self.insert_calls.append((table, dict(payload)))
        self.rows.append(dict(payload))
        return [dict(payload)]


def service():
    settings = SimpleNamespace(
        storage_bucket='crump-files',
        supabase_url='https://example.supabase.co',
        supabase_service_key='test',
        max_upload_bytes=50 * 1024 * 1024,
    )
    return FileService(settings, DummyDB())


def test_filename_sanitization_and_mime_inference():
    files = service()
    name, mime = files.validate_upload(filename='../quarterly report.pdf', mime_type='', size_bytes=100)
    assert name == 'quarterly report.pdf'
    assert mime == 'application/pdf'


def test_rejects_unsupported_extension():
    files = service()
    with pytest.raises(FileServiceError):
        files.validate_upload(filename='payload.exe', mime_type='application/octet-stream', size_bytes=100)


def test_signed_download_url_puts_filename_on_returned_url_not_signing_payload():
    files = service()
    captured = {}

    async def fake_storage_json(method, path, *, payload=None, timeout=30.0):
        captured.update(method=method, path=path, payload=payload, timeout=timeout)
        return {'signedURL': '/object/sign/crump-files/user/video.mp4?token=private-token'}

    files._storage_json = fake_storage_json
    url = asyncio.run(files.signed_url(
        row={'storage_path': 'user/video.mp4', 'file_name': 'Dog at the piano (final).mp4'},
        expires_in=600,
        download=True,
    ))

    assert captured['payload'] == {'expiresIn': 600}
    assert url == (
        'https://example.supabase.co/storage/v1/object/sign/crump-files/user/video.mp4'
        '?token=private-token&download=Dog%20at%20the%20piano%20%28final%29.mp4'
    )


def test_signed_inline_url_remains_previewable():
    files = service()

    async def fake_storage_json(method, path, *, payload=None, timeout=30.0):
        return {'signedUrl': 'https://storage.example/file?token=private-token'}

    files._storage_json = fake_storage_json
    url = asyncio.run(files.signed_url(
        row={'storage_path': 'user/video.mp4', 'file_name': 'Dog at the piano.mp4'},
        download=False,
    ))

    assert url == 'https://storage.example/file?token=private-token'


def test_hard_delete_all_owned_reconciles_paginated_storage_and_orphans():
    owner_id = 'owner-user'
    database = OwnedFileDB([
        {
            'id': 'owner-file-one',
            'user_id': owner_id,
            'storage_path': f'{owner_id}/owner-file-one.png',
        },
        {
            'id': 'owner-file-two',
            'user_id': owner_id,
            'storage_path': f'{owner_id}/owner-file-two.pptx',
            'deleted_at': '2026-09-01T00:00:00+00:00',
        },
        {
            'id': 'other-file',
            'user_id': 'other-user',
            'storage_path': 'other-user/other-file.png',
        },
    ])
    files = service()
    files.db = database
    files.STORAGE_PAGE_SIZE = 1
    storage_objects = {
        f'{owner_id}/owner-file-one.png',
        f'{owner_id}/owner-file-two.pptx',
        f'{owner_id}/orphan-without-metadata.png',
        f'{owner_id}/nested/orphan-video.mp4',
        'other-user/other-file.png',
    }
    storage_deletes = []

    async def fake_storage_json(method, path, *, payload=None, timeout=30.0):
        if path == 'object/list/crump-files':
            prefix = str(payload['prefix']).rstrip('/')
            children = {}
            for storage_path in storage_objects:
                if not storage_path.startswith(f'{prefix}/'):
                    continue
                remainder = storage_path[len(prefix) + 1:]
                name, separator, _rest = remainder.partition('/')
                children[name] = {'name': name, 'id': None if separator else f'id-{name}'}
            entries = [children[name] for name in sorted(children)]
            offset = int(payload['offset'])
            limit = int(payload['limit'])
            return entries[offset:offset + limit]
        assert method == 'DELETE'
        storage_deletes.append((method, path, payload, timeout))
        storage_objects.difference_update(payload['prefixes'])
        return [{'name': item} for item in payload['prefixes']]

    files._storage_json = fake_storage_json

    removed = asyncio.run(files.hard_delete_all_owned(user_id=owner_id, batch_size=2))

    assert removed == 4
    assert all(len(entry[2]['prefixes']) <= 2 for entry in storage_deletes)
    assert {
        path
        for entry in storage_deletes
        for path in entry[2]['prefixes']
    } == {
        f'{owner_id}/owner-file-one.png',
        f'{owner_id}/owner-file-two.pptx',
        f'{owner_id}/orphan-without-metadata.png',
        f'{owner_id}/nested/orphan-video.mp4',
    }
    assert storage_objects == {'other-user/other-file.png'}
    assert database.rows == [{
        'id': 'other-file',
        'user_id': 'other-user',
        'storage_path': 'other-user/other-file.png',
    }]


def test_file_writes_stop_when_account_deletion_is_fenced():
    database = OwnedFileDB([], owner_active=False)
    files = service()
    files.db = database

    with pytest.raises(FileServiceError) as failure:
        asyncio.run(files.create_upload(
            user_id='owner-user',
            filename='private.png',
            mime_type='image/png',
            size_bytes=100,
        ))

    assert failure.value.code == 'ACCOUNT_DELETION_IN_PROGRESS'
    assert database.insert_calls == []

    with pytest.raises(FileServiceError) as finalizer_failure:
        asyncio.run(files.store_bytes(
            user_id='owner-user',
            data=b'generated artifact',
            filename='artifact.txt',
            mime_type='text/plain',
            kind='generated_document',
        ))

    assert finalizer_failure.value.code == 'ACCOUNT_DELETION_IN_PROGRESS'
    assert database.insert_calls == []


def test_finalizer_removes_object_when_fence_starts_during_upload(monkeypatch):
    class RacingDB(OwnedFileDB):
        def __init__(self):
            super().__init__([])
            self.owner_checks = 0

        async def select(self, table, *, columns='*', filters=None, limit=None):
            if table == 'users':
                self.owner_checks += 1
                self.owner_active = self.owner_checks == 1
            return await super().select(
                table,
                columns=columns,
                filters=filters,
                limit=limit,
            )

    class Response:
        status_code = 200

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    database = RacingDB()
    files = service()
    files.db = database
    storage_deletes = []

    async def fake_storage_json(method, path, *, payload=None, timeout=30.0):
        storage_deletes.append((method, path, payload, timeout))
        return []

    files._storage_json = fake_storage_json
    monkeypatch.setattr(file_service_module.httpx, 'AsyncClient', Client)

    with pytest.raises(FileServiceError) as failure:
        asyncio.run(files.store_bytes(
            user_id='owner-user',
            data=b'generated artifact',
            filename='artifact.txt',
            mime_type='text/plain',
            kind='generated_document',
        ))

    assert failure.value.code == 'ACCOUNT_DELETION_IN_PROGRESS'
    assert database.insert_calls == []
    assert len(storage_deletes) == 1
    assert storage_deletes[0][0:2] == ('DELETE', 'object/crump-files')
    assert storage_deletes[0][2]['prefixes'][0].startswith('owner-user/')


def test_failed_compensating_delete_leaves_no_metadata_and_requires_durable_sweep(monkeypatch):
    class RacingDB(OwnedFileDB):
        def __init__(self):
            super().__init__([])
            self.owner_checks = 0

        async def select(self, table, *, columns='*', filters=None, limit=None):
            if table == 'users':
                self.owner_checks += 1
                self.owner_active = self.owner_checks == 1
            return await super().select(
                table,
                columns=columns,
                filters=filters,
                limit=limit,
            )

    class Response:
        status_code = 200

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    database = RacingDB()
    files = service()
    files.db = database

    async def failed_storage_delete(method, path, *, payload=None, timeout=30.0):
        assert method == 'DELETE'
        raise FileServiceError('storage unavailable', 503, 'STORAGE_ERROR')

    files._storage_json = failed_storage_delete
    monkeypatch.setattr(file_service_module.httpx, 'AsyncClient', Client)

    with pytest.raises(FileServiceError) as failure:
        asyncio.run(files.store_bytes(
            user_id='owner-user',
            data=b'generated artifact whose compensation fails',
            filename='artifact.txt',
            mime_type='text/plain',
            kind='generated_document',
        ))

    assert failure.value.code == 'ACCOUNT_DELETION_IN_PROGRESS'
    assert database.insert_calls == []
    # The physical orphan is intentionally handled by the durable owner-prefix
    # sweep; no metadata row can falsely advertise it as a completed file.
    assert database.rows == []


@pytest.mark.parametrize(
    'storage_path',
    [
        'other-user/other-file.png',
        'owner-user/../other-user/other-file.png',
        'owner-user\\other-file.png',
    ],
)
def test_hard_delete_refuses_untrusted_storage_path_without_deleting_anything(storage_path):
    database = OwnedFileDB([{
        'id': 'owner-file',
        'user_id': 'owner-user',
        'storage_path': storage_path,
    }])
    files = service()
    files.db = database
    storage_deletes = []

    async def fake_storage_json(method, path, *, payload=None, timeout=30.0):
        storage_deletes.append((method, path, payload, timeout))
        return {}

    files._storage_json = fake_storage_json

    with pytest.raises(FileServiceError) as failure:
        asyncio.run(files.hard_delete(user_id='owner-user', file_id='owner-file'))

    assert failure.value.code == 'FILE_OWNERSHIP_UNVERIFIED'
    assert storage_deletes == []
    assert database.delete_calls == []
    assert database.rows == [{
        'id': 'owner-file',
        'user_id': 'owner-user',
        'storage_path': storage_path,
    }]
