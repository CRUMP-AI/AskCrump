from __future__ import annotations

import warnings

import pytest

from backend import video_service as video_module
from backend.video_service import VideoService, VideoServiceError


class OversizedImage:
    size = (VideoService.REFERENCE_IMAGE_MAX_SOURCE_EDGE + 1, 1)
    n_frames = 1

    def __init__(self) -> None:
        self.seek_called = False
        self.load_called = False

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def seek(self, _frame: int) -> None:
        self.seek_called = True

    def load(self) -> None:
        self.load_called = True


def _fail_if_transposed(_source):
    raise AssertionError("Oversized or bomb-marked input reached EXIF transpose.")


def test_reference_decoder_rejects_oversized_dimensions_before_seek_transpose_or_load(
    monkeypatch,
) -> None:
    source = OversizedImage()
    monkeypatch.setattr(video_module.Image, "open", lambda _stream: source)
    monkeypatch.setattr(video_module.ImageOps, "exif_transpose", _fail_if_transposed)

    with pytest.raises(VideoServiceError) as caught:
        VideoService._prepare_reference_image(b"not-decoded")

    assert caught.value.code == "VIDEO_REFERENCE_IMAGE_TOO_LARGE"
    assert caught.value.status_code == 413
    assert source.seek_called is False
    assert source.load_called is False


def test_reference_decoder_promotes_decompression_bomb_warning_before_transpose_or_load(
    monkeypatch,
) -> None:
    transpose_called = False

    def bomb_warning(_stream):
        warnings.warn(
            "suspicious image dimensions",
            video_module.Image.DecompressionBombWarning,
            stacklevel=1,
        )
        raise AssertionError("Promoted decompression warning did not stop Image.open.")

    def transpose(_source):
        nonlocal transpose_called
        transpose_called = True
        raise AssertionError("Bomb-marked input reached EXIF transpose.")

    monkeypatch.setattr(video_module.Image, "open", bomb_warning)
    monkeypatch.setattr(video_module.ImageOps, "exif_transpose", transpose)

    with pytest.raises(VideoServiceError) as caught:
        VideoService._prepare_reference_image(b"warning")

    assert caught.value.code == "VIDEO_REFERENCE_IMAGE_TOO_LARGE"
    assert caught.value.status_code == 413
    assert isinstance(caught.value.__cause__, video_module.Image.DecompressionBombWarning)
    assert transpose_called is False


def test_reference_decoder_maps_decompression_bomb_error_before_transpose_or_load(
    monkeypatch,
) -> None:
    transpose_called = False

    def bomb_error(_stream):
        raise video_module.Image.DecompressionBombError("image is too large")

    def transpose(_source):
        nonlocal transpose_called
        transpose_called = True
        raise AssertionError("Bomb-marked input reached EXIF transpose.")

    monkeypatch.setattr(video_module.Image, "open", bomb_error)
    monkeypatch.setattr(video_module.ImageOps, "exif_transpose", transpose)

    with pytest.raises(VideoServiceError) as caught:
        VideoService._prepare_reference_image(b"error")

    assert caught.value.code == "VIDEO_REFERENCE_IMAGE_TOO_LARGE"
    assert caught.value.status_code == 413
    assert isinstance(caught.value.__cause__, video_module.Image.DecompressionBombError)
    assert transpose_called is False

