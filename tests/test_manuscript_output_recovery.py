from pathlib import Path

import pytest

from backend.file_service import FileServiceError
from backend.routes import manuscripts as manuscript_routes


ROOT = Path(__file__).resolve().parents[1]


class PublicRuns:
    @staticmethod
    def public_run(row):
        if not row:
            return None
        return {
            "id": row["id"],
            "status": row["status"],
            "outputFileId": row.get("output_file_id"),
        }


class PublicFiles:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def get_owned(self, *, user_id, file_id):
        self.calls.append({"user_id": user_id, "file_id": file_id})
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    @staticmethod
    def public_file(row):
        return {"id": row["id"], "url": f"/api/files/{row['id']}/content"}


def completed_run():
    return {
        "id": "run-1",
        "status": "completed",
        "output_file_id": "file-1",
    }


@pytest.mark.asyncio
async def test_completed_manuscript_returns_owner_scoped_saved_export(monkeypatch):
    file_service = PublicFiles({"id": "file-1"})
    monkeypatch.setattr(manuscript_routes, "manuscripts", PublicRuns())
    monkeypatch.setattr(manuscript_routes, "files", file_service)

    payload = await manuscript_routes._public_run("owner-1", completed_run())

    assert payload["outputFile"] == {
        "id": "file-1",
        "url": "/api/files/file-1/content",
    }
    assert "outputFileRecovery" not in payload
    assert file_service.calls == [{"user_id": "owner-1", "file_id": "file-1"}]


@pytest.mark.asyncio
async def test_missing_manuscript_export_is_truthful_and_does_not_offer_an_automatic_retry(monkeypatch):
    file_service = PublicFiles(FileServiceError("sensitive missing detail", 404, "FILE_NOT_FOUND"))
    monkeypatch.setattr(manuscript_routes, "manuscripts", PublicRuns())
    monkeypatch.setattr(manuscript_routes, "files", file_service)

    payload = await manuscript_routes._public_run("owner-1", completed_run())

    assert payload["status"] == "completed"
    assert payload["outputFileRecovery"] == {
        "status": "missing",
        "code": "MANUSCRIPT_OUTPUT_FILE_NOT_FOUND",
        "message": "This export is no longer available in Files. Your manuscript remains saved; create a new export only when you choose.",
        "shouldRetry": False,
    }
    assert "sensitive" not in str(payload)


@pytest.mark.asyncio
async def test_temporary_manuscript_export_lookup_failure_offers_content_free_retry(monkeypatch):
    file_service = PublicFiles(RuntimeError("database host and secret detail"))
    monkeypatch.setattr(manuscript_routes, "manuscripts", PublicRuns())
    monkeypatch.setattr(manuscript_routes, "files", file_service)

    payload = await manuscript_routes._public_run("owner-1", completed_run())

    recovery = payload["outputFileRecovery"]
    assert payload["status"] == "completed"
    assert recovery["status"] == "unavailable"
    assert recovery["code"] == "MANUSCRIPT_OUTPUT_LOOKUP_UNAVAILABLE"
    assert recovery["shouldRetry"] is True
    assert "without rerunning or charging" in recovery["message"]
    assert "database host" not in str(payload)


def test_manuscript_output_retry_only_refetches_the_existing_run():
    source = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    start = source.index("async function retryManuscriptOutputLookup()")
    end = source.index("\n  function scheduleManuscriptPoll()", start)
    retry = source[start:end]

    assert 'id="crump53RetryManuscriptOutput"' in source
    assert "await api(`/api/manuscripts/${manuscriptId}/run`)" in retry
    assert "method: 'POST'" not in retry
    assert "/runs`" not in retry
    assert "outputFileRecovery?.shouldRetry" in retry
