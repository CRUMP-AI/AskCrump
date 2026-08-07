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
