#!/usr/bin/env python3
"""Fail-closed static 16 KB page-size checks for a generated Android App Bundle.

This checks bundletool's native-library packaging request and every bundled
shared library's ELF LOAD segments. It is not a replacement for a 16 KB
device/emulator run or Play Console validation.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zipfile
from pathlib import Path

PAGE_SIZE = 16 * 1024
MAX_LIBRARY_BYTES = 256 * 1024 * 1024


def protobuf_fields(raw: bytes) -> list[tuple[int, int, int | bytes]]:
    """Read the wire types used by BundleConfig without an external dependency."""

    def varint(position: int) -> tuple[int, int]:
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(raw):
                raise ValueError("truncated protobuf varint")
            byte = raw[position]
            position += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value, position
        raise ValueError("protobuf varint exceeds 64 bits")

    output: list[tuple[int, int, int | bytes]] = []
    position = 0
    while position < len(raw):
        tag, position = varint(position)
        field, wire_type = tag >> 3, tag & 7
        if field == 0:
            raise ValueError("invalid protobuf field number")
        if wire_type == 0:
            value, position = varint(position)
        elif wire_type == 2:
            length, position = varint(position)
            end = position + length
            if end > len(raw):
                raise ValueError("truncated protobuf field")
            value = raw[position:end]
            position = end
        elif wire_type == 1:
            end = position + 8
            if end > len(raw):
                raise ValueError("truncated protobuf fixed64")
            value = raw[position:end]
            position = end
        elif wire_type == 5:
            end = position + 4
            if end > len(raw):
                raise ValueError("truncated protobuf fixed32")
            value = raw[position:end]
            position = end
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
        output.append((field, wire_type, value))
    return output


def only_field(raw: bytes, number: int, wire_type: int) -> int | bytes:
    matching = [
        value
        for field, actual_type, value in protobuf_fields(raw)
        if field == number and actual_type == wire_type
    ]
    if len(matching) != 1:
        raise ValueError(f"BundleConfig field {number} must occur exactly once")
    return matching[0]


def verify_bundle_config(raw: bytes) -> str:
    # config.proto: BundleConfig.optimizations(2) →
    # Optimizations.uncompress_native_libraries(2) →
    # UncompressNativeLibraries.enabled(1), alignment(2).
    optimizations = only_field(raw, 2, 2)
    assert isinstance(optimizations, bytes)
    native = only_field(optimizations, 2, 2)
    assert isinstance(native, bytes)
    enabled = only_field(native, 1, 0)
    alignment = only_field(native, 2, 0)
    if enabled != 1:
        raise ValueError(
            "native-library packaging is not explicitly uncompressed; "
            "review the compressed-library path before release"
        )
    if alignment not in (2, 3):
        raise ValueError(
            "bundle does not request PAGE_ALIGNMENT_16K or PAGE_ALIGNMENT_64K "
            "for uncompressed native libraries"
        )
    return "PAGE_ALIGNMENT_16K" if alignment == 2 else "PAGE_ALIGNMENT_64K"


def verify_elf(name: str, raw: bytes) -> int:
    if len(raw) < 64 or raw[:4] != b"\x7fELF":
        raise ValueError(f"{name}: not a complete ELF shared library")
    elf_class, byte_order = raw[4], raw[5]
    if elf_class not in (1, 2) or byte_order not in (1, 2):
        raise ValueError(f"{name}: unsupported ELF class or byte order")
    endian = "<" if byte_order == 1 else ">"
    if elf_class == 1:
        phoff = struct.unpack_from(endian + "I", raw, 28)[0]
        phentsize, phnum = struct.unpack_from(endian + "HH", raw, 42)
        minimum = 32
        fmt = endian + "IIIIIIII"
    else:
        phoff = struct.unpack_from(endian + "Q", raw, 32)[0]
        phentsize, phnum = struct.unpack_from(endian + "HH", raw, 54)
        minimum = 56
        fmt = endian + "IIQQQQQQ"
    if phnum in (0, 0xFFFF) or phentsize < minimum:
        raise ValueError(f"{name}: missing or unsupported ELF program headers")
    if phoff + phentsize * phnum > len(raw):
        raise ValueError(f"{name}: truncated ELF program headers")
    load_count = 0
    for index in range(phnum):
        fields = struct.unpack_from(fmt, raw, phoff + index * phentsize)
        if fields[0] != 1:  # PT_LOAD
            continue
        load_count += 1
        if elf_class == 1:
            _, p_offset, p_vaddr, _, _, _, _, p_align = fields
        else:
            _, _, p_offset, p_vaddr, _, _, _, p_align = fields
        if (
            p_align < PAGE_SIZE
            or p_align & (p_align - 1)
            or (p_vaddr - p_offset) % PAGE_SIZE
        ):
            raise ValueError(
                f"{name}: PT_LOAD[{index}] is not 16 KB ELF-aligned "
                f"(p_align={p_align})"
            )
    if not load_count:
        raise ValueError(f"{name}: no PT_LOAD segments to verify")
    return load_count


def verify_aab(path: Path) -> tuple[int, int, str]:
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        # Dynamic feature module names are arbitrary, not literally "feature".
        libraries = sorted(
            name for name in names
            if len(name.split("/")) == 4
            and name.split("/")[1] == "lib"
            and name.endswith(".so")
        )
        if not libraries:
            return 0, 0, "no packaged native libraries"
        alignment = verify_bundle_config(bundle.read("BundleConfig.pb"))
        segments = 0
        for name in libraries:
            info = bundle.getinfo(name)
            if info.file_size > MAX_LIBRARY_BYTES:
                raise ValueError(f"{name}: library exceeds verifier size limit")
            segments += verify_elf(name, bundle.read(name))
        return len(libraries), segments, alignment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="generated release .aab")
    args = parser.parse_args()
    try:
        libraries, segments, alignment = verify_aab(args.bundle)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as error:
        print(f"Android 16 KB page-size verification failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Android 16 KB static check passed: {libraries} native libraries, "
        f"{segments} PT_LOAD segments; {alignment}."
    )
    print("Still required: 16 KB device/emulator test and Play Console review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
