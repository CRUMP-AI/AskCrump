from __future__ import annotations

import logging

from backend.routes.media import _video_error
from backend.video_service import VideoServiceError


def test_video_rejection_log_is_categorical_and_content_free(caplog) -> None:
    private_message = "Private prompt mentioning family-photo.png and account details"
    error = VideoServiceError(
        private_message,
        "INVALID_VIDEO_PROMPT",
        status_code=400,
        retryable=False,
    )

    with caplog.at_level(logging.WARNING, logger="askcrump.media"):
        response = _video_error(error, stage="generation")

    assert response.status_code == 400
    assert [record.getMessage() for record in caplog.records] == [
        "Video request rejected stage=generation status=400 "
        "code=INVALID_VIDEO_PROMPT retryable=False"
    ]
    assert private_message not in caplog.text


def test_video_rejection_log_fails_closed_for_unstructured_tokens(caplog) -> None:
    error = VideoServiceError(
        "Private provider diagnostic",
        "private prompt and filename.png",
        status_code=503,
        retryable=True,
    )

    with caplog.at_level(logging.ERROR, logger="askcrump.media"):
        response = _video_error(error, stage="private-stage")

    assert response.status_code == 503
    assert [record.getMessage() for record in caplog.records] == [
        "Video request rejected stage=unknown status=503 code=VIDEO_ERROR retryable=True"
    ]
    assert "Private provider diagnostic" not in caplog.text
    assert "private prompt and filename.png" not in caplog.text
