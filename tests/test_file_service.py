import asyncio
from types import SimpleNamespace

import pytest

from backend.file_service import FileService, FileServiceError


class DummyDB:
    pass


class ObjectOnlyDB:
    def __init__(self):
        self.deleted = []

    async def select_one(self, _table, *, filters):
        return None

    async def insert(self, *_args, **_kwargs):
        raise AssertionError("Object-only storage must not insert file metadata")

    async def upsert(self, *_args, **_kwargs):
        raise AssertionError("Object-only storage must not upsert file metadata")

    async def delete(self, table, *, filters):
        self.deleted.append((table, dict(filters)))
        return []


class UploadDB:
    def __init__(self, row):
        self.row = dict(row)
        self.updates = []

    async def select_one(self, _table, *, filters):
        return dict(self.row)

    async def update(self, _table, payload, *, filters):
        self.updates.append((dict(payload), dict(filters)))
        self.row.update(payload)
        return [dict(self.row)]


def service():
    settings = SimpleNamespace(
        storage_bucket='crump-files',
        supabase_url='https://example.supabase.co',
        supabase_service_key='test',
        max_upload_bytes=50 * 1024 * 1024,
        max_generated_video_bytes=100 * 1024 * 1024,
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


def test_public_file_fails_closed_for_malformed_legacy_metadata():
    public = FileService.public_file({
        'id': '00000000-0000-4000-8000-000000000001',
        'file_name': 'legacy.pdf',
        'mime_type': 'application/pdf',
        'size_bytes': 100,
        'status': 'ready',
        'metadata': ['unexpected'],
    })

    assert public['metadata'] == {}


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
        return {
            'signedUrl': (
                'https://example.supabase.co/storage/v1/object/sign/'
                'crump-files/user/video.mp4?token=private-token'
            )
        }

    files._storage_json = fake_storage_json
    url = asyncio.run(files.signed_url(
        row={'storage_path': 'user/video.mp4', 'file_name': 'Dog at the piano.mp4'},
        download=False,
    ))

    assert url == (
        'https://example.supabase.co/storage/v1/object/sign/'
        'crump-files/user/video.mp4?token=private-token'
    )


@pytest.mark.parametrize(
    ("metadata", "code"),
    [
        ({"size": 101, "mimetype": "image/png"}, "UPLOAD_SIZE_MISMATCH"),
        ({"size": 100, "mimetype": "image/jpeg"}, "UPLOAD_TYPE_MISMATCH"),
        ({"size": 26 * 1024 * 1024, "mimetype": "image/png"}, "FILE_TOO_LARGE"),
    ],
)
def test_complete_upload_revalidates_actual_storage_metadata(monkeypatch, metadata, code):
    row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "owner",
        "storage_path": "owner/file.png",
        "file_name": "file.png",
        "mime_type": "image/png",
        "size_bytes": 100,
        "status": "pending",
    }
    database = UploadDB(row)
    files = FileService(service().settings, database)

    class Response:
        status_code = 200
        content = b"{}"

        @staticmethod
        def json():
            return {"metadata": metadata}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("backend.file_service.httpx.AsyncClient", lambda **_kwargs: Client())

    with pytest.raises(FileServiceError) as error:
        asyncio.run(files.complete_upload(user_id="owner", file_id=row["id"]))

    assert error.value.code == code
    assert database.updates[-1][0]["status"] == "failed"


def test_download_bytes_streams_and_stops_before_buffering_past_limit(monkeypatch):
    files = service()

    class Response:
        status_code = 200
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aiter_bytes(self):
            yield b"1234"
            yield b"5678"

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("backend.file_service.httpx.AsyncClient", lambda **_kwargs: Client())

    with pytest.raises(FileServiceError) as error:
        asyncio.run(files.download_bytes(row={"storage_path": "owner/file.bin"}, max_bytes=6))

    assert error.value.code == "FILE_PROCESSING_LIMIT"


def test_generated_video_can_upload_object_without_publishing_metadata(monkeypatch):
    database = ObjectOnlyDB()
    files = FileService(service().settings, database)
    captured = {}

    class Response:
        status_code = 200

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, data, files):
            captured.update(url=url, headers=headers, data=data, files=files)
            return Response()

    monkeypatch.setattr("backend.file_service.httpx.AsyncClient", lambda **_kwargs: Client())
    file_id = "00000000-0000-4000-8000-000000000071"

    row = asyncio.run(
        files.store_bytes(
            user_id="owner",
            data=b"video-bytes",
            filename=f"crump-video-{file_id}.mp4",
            mime_type="video/mp4",
            kind="generated_video",
            metadata={"mediaJobId": file_id},
            file_id=file_id,
            persist_metadata=False,
        )
    )

    assert row["id"] == file_id
    assert row["storage_path"] == f"owner/{file_id}.mp4"
    assert row["metadata"] == {"mediaJobId": file_id}
    assert captured["headers"]["x-upsert"] == "true"
    assert database.deleted == []


def test_generated_video_cleanup_is_exactly_owner_and_kind_scoped():
    database = ObjectOnlyDB()
    files = FileService(service().settings, database)
    storage_calls = []

    async def fake_storage_json(method, path, *, payload=None, timeout=30.0):
        storage_calls.append((method, path, payload, timeout))
        return {}

    files._storage_json = fake_storage_json
    file_id = "00000000-0000-4000-8000-000000000072"

    asyncio.run(
        files.discard_generated_file(
            user_id="owner",
            file_id=file_id,
            filename=f"crump-video-{file_id}.mp4",
        )
    )

    assert storage_calls == [
        (
            "DELETE",
            "object/crump-files",
            {"prefixes": [f"owner/{file_id}.mp4"]},
            60.0,
        )
    ]
    assert database.deleted == [
        (
            "user_files",
            {
                "id": f"eq.{file_id}",
                "user_id": "eq.owner",
                "kind": "eq.generated_video",
            },
        )
    ]
def test_soft_delete_confirms_the_owner_row_is_inaccessible():
    file_id = '00000000-0000-4000-8000-000000000123'

    class DeleteDB:
        def __init__(self):
            self.row = {'id': file_id, 'user_id': 'owner-1', 'deleted_at': None}

        async def select_one(self, _table, **_kwargs):
            return dict(self.row) if self.row else None

        async def update(self, _table, payload, **_kwargs):
            self.row.update(payload)
            return [dict(self.row)]

    files = service()
    files.db = DeleteDB()
    deleted = asyncio.run(files.soft_delete(user_id='owner-1', file_id=file_id))

    assert deleted['deleted_at'] is not None


def test_soft_delete_fails_when_the_authoritative_row_remains_readable():
    file_id = '00000000-0000-4000-8000-000000000124'

    class StaleDeleteDB:
        async def select_one(self, _table, **_kwargs):
            return {'id': file_id, 'user_id': 'owner-1', 'deleted_at': None}

        async def update(self, _table, _payload, **_kwargs):
            return []

    files = service()
    files.db = StaleDeleteDB()

    with pytest.raises(FileServiceError) as caught:
        asyncio.run(files.soft_delete(user_id='owner-1', file_id=file_id))

    assert caught.value.code == 'FILE_DELETE_UNCONFIRMED'


@pytest.mark.parametrize(
    'signed_url',
    [
        'https://attacker.example/storage/v1/object/sign/crump-files/user/file.pdf?token=x',
        'https://example.supabase.co.attacker.example/storage/v1/object/sign/crump-files/user/file.pdf?token=x',
        'https://example.supabase.co@attacker.example/storage/v1/object/sign/crump-files/user/file.pdf?token=x',
        'http://example.supabase.co/storage/v1/object/sign/crump-files/user/file.pdf?token=x',
        'https://example.supabase.co:443/storage/v1/object/sign/crump-files/user/file.pdf?token=x',
        '//example.supabase.co/storage/v1/object/sign/crump-files/user/file.pdf?token=x',
        'https://example.supabase.co/storage/v1/object/public/crump-files/user/file.pdf?token=x',
        'https://example.supabase.co/storage/v1/object/sign/crump-files/user/file.pdf',
        'https://example.supabase.co/storage/v1/object/sign/crump-files/user/file.pdf?token=x#fragment',
        'https://example.supabase.co:bad/storage/v1/object/sign/crump-files/user/file.pdf?token=x',
        'https://example.supabase.co/storage/v1/object/sign/crump-files/user/other.pdf?token=x',
        'https://example.supabase.co/storage/v1/object/sign/crump-files/user/file.pdf/extra?token=x',
    ],
)
def test_signed_url_rejects_every_destination_outside_exact_private_storage(signed_url):
    files = service()

    async def fake_storage_json(method, path, *, payload=None, timeout=30.0):
        return {'signedURL': signed_url}

    files._storage_json = fake_storage_json
    with pytest.raises(FileServiceError) as caught:
        asyncio.run(files.signed_url(
            row={'storage_path': 'user/file.pdf', 'file_name': 'file.pdf'},
        ))

    assert caught.value.status_code == 503
    assert caught.value.code == 'SIGNED_URL_FAILED'
