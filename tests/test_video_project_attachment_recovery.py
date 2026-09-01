from pathlib import Path

import pytest

from backend.project_service import ProjectNotFoundError
from backend.routes import media as media_routes


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
PROJECT_ID = "00000000-0000-0000-0000-000000000002"
FILE_ID = "00000000-0000-0000-0000-000000000003"
JOB_ID = "00000000-0000-0000-0000-000000000004"


class ReadyVideo:
    def __init__(self):
        self.row = {
            "id": JOB_ID,
            "status": "ready",
            "project_id": PROJECT_ID,
            "file_id": FILE_ID,
        }

    async def poll(self, **_kwargs):
        return dict(self.row)

    async def public_job(self, **kwargs):
        row = kwargs["row"]
        return {
            "id": row["id"],
            "status": row["status"],
            "file": {"id": row["file_id"], "url": "https://files.example/video.mp4"},
        }

    @staticmethod
    def refund_eligible(_row):
        return False


async def authenticate(*_args, **_kwargs):
    return type("Auth", (), {"user": {"id": USER_ID}})()


@pytest.mark.asyncio
async def test_ready_video_returns_truthful_project_attachment_receipt(monkeypatch):
    calls = []

    class Projects:
        async def attach_file(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(media_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(media_routes, "video", ReadyVideo())
    monkeypatch.setattr(media_routes, "projects", Projects())

    payload = await media_routes.video_status(JOB_ID, object())

    assert calls == [{
        "user_id": USER_ID,
        "project_id": PROJECT_ID,
        "file_id": FILE_ID,
        "role": "generated_video",
    }]
    assert payload["job"]["projectAttachment"] == {
        "status": "attached",
        "projectId": PROJECT_ID,
        "role": "generated_video",
        "shouldRetry": False,
    }


@pytest.mark.asyncio
async def test_ready_video_keeps_file_success_and_returns_content_free_retry_receipt(monkeypatch):
    class Projects:
        async def attach_file(self, **_kwargs):
            raise RuntimeError("database diagnostic SECRET_VALUE")

    monkeypatch.setattr(media_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(media_routes, "video", ReadyVideo())
    monkeypatch.setattr(media_routes, "projects", Projects())

    payload = await media_routes.video_status(JOB_ID, object())

    assert payload["success"] is True
    assert payload["job"]["file"]["id"] == FILE_ID
    assert payload["job"]["projectAttachment"] == {
        "status": "failed",
        "projectId": PROJECT_ID,
        "role": "generated_video",
        "shouldRetry": True,
        "message": "The video is safe in Files, but its Project link needs a retry.",
    }
    assert "SECRET_VALUE" not in str(payload)


@pytest.mark.asyncio
async def test_ready_video_marks_an_unavailable_project_as_non_retryable(monkeypatch):
    class Projects:
        async def attach_file(self, **_kwargs):
            raise ProjectNotFoundError("private diagnostic")

    monkeypatch.setattr(media_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(media_routes, "video", ReadyVideo())
    monkeypatch.setattr(media_routes, "projects", Projects())

    payload = await media_routes.video_status(JOB_ID, object())

    assert payload["job"]["projectAttachment"] == {
        "status": "missing",
        "projectId": PROJECT_ID,
        "role": "generated_video",
        "shouldRetry": False,
        "message": "The video is safe in Files, but its original Project is no longer available.",
    }
    assert "private diagnostic" not in str(payload)


def test_video_project_retry_reuses_only_the_owner_scoped_attachment_endpoint():
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    retry = product.split("async function retryVideoProjectAttachment(job)", 1)[1].split(
        "function renderReadyVideo(job", 1
    )[0]

    assert "Retry Project save" in product
    assert "Safe in Files · Project link needs retry" in product
    assert "body: {fileId, role: 'generated_video'}" in retry
    assert "/api/projects/${encodeURIComponent(projectId)}/files" in retry
    assert "/continue" not in retry
    assert "credits" not in retry.lower()
