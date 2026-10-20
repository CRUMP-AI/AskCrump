"""Delete-option coverage for saved videos.

Drives the real VideoService.delete_job with fake db/files collaborators:
a finished video deletes its media_jobs row and soft-deletes its saved
file; a still-generating job is refused (409) with nothing removed; an
unknown job is a 404.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.video_service import VideoService, VideoServiceError

USER_ID = "11111111-1111-5111-8111-111111111111"
JOB_ID = "22222222-2222-5222-8222-222222222222"
FILE_ID = "33333333-3333-5333-8333-333333333333"


class FakeDb:
    def __init__(self, row):
        self.row = row
        self.deleted = []

    async def select_one(self, table, *, filters):
        assert table == "media_jobs"
        return self.row

    async def delete(self, table, *, filters):
        self.deleted.append((table, filters))
        return [{"id": JOB_ID}]


class FakeFiles:
    def __init__(self):
        self.soft_deleted = []

    async def soft_delete(self, *, user_id, file_id):
        self.soft_deleted.append((user_id, file_id))
        return {"id": file_id, "deleted_at": "2026-10-20T00:00:00Z"}


def make_service(row):
    service = VideoService.__new__(VideoService)
    service.db = FakeDb(row)
    service.files = FakeFiles()
    return service


def test_ready_video_deletes_row_and_soft_deletes_file():
    row = {"id": JOB_ID, "status": "ready", "file_id": FILE_ID}
    service = make_service(row)

    result = asyncio.run(service.delete_job(user_id=USER_ID, job_id=JOB_ID))

    assert result == {"id": JOB_ID, "deleted": True}
    assert service.files.soft_deleted == [(USER_ID, FILE_ID)]
    assert len(service.db.deleted) == 1
    table, filters = service.db.deleted[0]
    assert table == "media_jobs"
    assert filters["id"] == f"eq.{JOB_ID}"
    assert filters["user_id"] == f"eq.{USER_ID}"
    assert filters["kind"] == "eq.video"


def test_failed_video_without_file_still_deletes_row():
    row = {"id": JOB_ID, "status": "failed", "file_id": None}
    service = make_service(row)

    result = asyncio.run(service.delete_job(user_id=USER_ID, job_id=JOB_ID))

    assert result["deleted"] is True
    assert service.files.soft_deleted == []
    assert len(service.db.deleted) == 1


@pytest.mark.parametrize("status", ["queued", "processing"])
def test_in_progress_video_is_refused_and_nothing_is_deleted(status):
    row = {"id": JOB_ID, "status": status, "file_id": FILE_ID}
    service = make_service(row)

    with pytest.raises(VideoServiceError) as excinfo:
        asyncio.run(service.delete_job(user_id=USER_ID, job_id=JOB_ID))

    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "VIDEO_DELETE_IN_PROGRESS"
    assert service.files.soft_deleted == []
    assert service.db.deleted == []


def test_unknown_video_is_404():
    service = make_service(None)

    with pytest.raises(VideoServiceError) as excinfo:
        asyncio.run(service.delete_job(user_id=USER_ID, job_id=JOB_ID))

    assert excinfo.value.status_code == 404
    assert service.db.deleted == []
