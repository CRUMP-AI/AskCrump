"""Synthetic AAB fixtures for the Android 16 KB static store gate."""

from __future__ import annotations

import importlib.util
import struct
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify-android-page-size.py"
SPEC = importlib.util.spec_from_file_location("verify_android_page_size", SCRIPT)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def field(number: int, value: int | bytes) -> bytes:
    if isinstance(value, int):
        assert 0 <= value < 128
        return bytes((number << 3, value))
    assert len(value) < 128
    return bytes((number << 3 | 2, len(value))) + value


def config(*, enabled: int = 1, alignment: int = 2) -> bytes:
    native = field(1, enabled) + field(2, alignment)
    return field(2, field(2, native))


def elf64(*, alignment: int = 16384, offset: int = 0, address: int = 16384) -> bytes:
    raw = bytearray(120)
    raw[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<Q", raw, 32, 64)  # e_phoff
    struct.pack_into("<HH", raw, 54, 56, 1)  # e_phentsize, e_phnum
    struct.pack_into(
        "<IIQQQQQQ", raw, 64, 1, 5, offset, address, 0, 120, 120, alignment
    )
    return bytes(raw)


def elf32(*, alignment: int = 16384) -> bytes:
    raw = bytearray(84)
    raw[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<I", raw, 28, 52)  # e_phoff
    struct.pack_into("<HH", raw, 42, 32, 1)  # e_phentsize, e_phnum
    struct.pack_into("<IIIIIIII", raw, 52, 1, 0, 16384, 0, 84, 84, 5, alignment)
    return bytes(raw)


def bundle(path: Path, libraries: dict[str, bytes], *, bundle_config: bytes | None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        if bundle_config is not None:
            archive.writestr("BundleConfig.pb", bundle_config)
        for name, content in libraries.items():
            archive.writestr(name, content)
    return path


def test_aligned_base_and_dynamic_feature_libraries_pass(tmp_path: Path) -> None:
    path = bundle(
        tmp_path / "good.aab",
        {
            "base/lib/arm64-v8a/libbase.so": elf64(),
            "camera/lib/arm64-v8a/libcamera.so": elf64(alignment=65536),
        },
        bundle_config=config(),
    )
    assert verifier.verify_aab(path) == (2, 2, "PAGE_ALIGNMENT_16K")


def test_no_native_libraries_need_no_alignment_setting(tmp_path: Path) -> None:
    path = bundle(tmp_path / "java-only.aab", {}, bundle_config=None)
    assert verifier.verify_aab(path) == (0, 0, "no packaged native libraries")


@pytest.mark.parametrize("alignment", [0, 1])
def test_4k_or_unspecified_bundle_alignment_fails(
    tmp_path: Path, alignment: int
) -> None:
    path = bundle(
        tmp_path / "four-k.aab",
        {"base/lib/arm64-v8a/libtest.so": elf64()},
        bundle_config=config(alignment=alignment),
    )
    with pytest.raises(ValueError, match="PAGE_ALIGNMENT_16K"):
        verifier.verify_aab(path)


def test_missing_bundle_config_fails_closed(tmp_path: Path) -> None:
    path = bundle(
        tmp_path / "no-config.aab",
        {"base/lib/arm64-v8a/libtest.so": elf64()},
        bundle_config=None,
    )
    with pytest.raises(KeyError, match="BundleConfig.pb"):
        verifier.verify_aab(path)


def test_compressed_library_path_requires_separate_review(tmp_path: Path) -> None:
    path = bundle(
        tmp_path / "compressed.aab",
        {"base/lib/arm64-v8a/libtest.so": elf64()},
        bundle_config=config(enabled=0),
    )
    with pytest.raises(ValueError, match="compressed-library path"):
        verifier.verify_aab(path)


@pytest.mark.parametrize(
    "library",
    [
        elf64(alignment=4096),
        elf64(alignment=16384, offset=4096),
        b"not-an-ELF",
    ],
)
def test_misaligned_or_invalid_elf_fails(tmp_path: Path, library: bytes) -> None:
    path = bundle(
        tmp_path / "bad-elf.aab",
        {"base/lib/arm64-v8a/libtest.so": library},
        bundle_config=config(),
    )
    with pytest.raises(ValueError, match="libtest.so"):
        verifier.verify_aab(path)


def test_64k_bundle_alignment_is_at_least_16k(tmp_path: Path) -> None:
    path = bundle(
        tmp_path / "64k.aab",
        {"base/lib/arm64-v8a/libtest.so": elf64(alignment=65536)},
        bundle_config=config(alignment=3),
    )
    assert verifier.verify_aab(path) == (1, 1, "PAGE_ALIGNMENT_64K")


def test_32_bit_shared_library_is_checked_too(tmp_path: Path) -> None:
    path = bundle(
        tmp_path / "32bit.aab",
        {"base/lib/armeabi-v7a/libtest.so": elf32()},
        bundle_config=config(),
    )
    assert verifier.verify_aab(path) == (1, 1, "PAGE_ALIGNMENT_16K")


def test_truncated_config_fails_closed(tmp_path: Path) -> None:
    path = bundle(
        tmp_path / "broken-config.aab",
        {"base/lib/arm64-v8a/libtest.so": elf64()},
        bundle_config=b"\x12\x05\x12",
    )
    with pytest.raises(ValueError, match="truncated protobuf"):
        verifier.verify_aab(path)
