import asyncio
from types import SimpleNamespace

import pytest

from backend.file_service import FileService, FileServiceError


class DummyDB:
    pass


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
