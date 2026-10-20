"""Apply the matching bundled BPS to a clean ISO without replacing any file."""
from __future__ import annotations

import argparse
import mmap
from pathlib import Path
import struct
import zlib


def apply(source: Path, patch_path: Path, output: Path) -> None:
    patch = patch_path.read_bytes()
    if len(patch) < 19 or patch[:4] != b"BPS1":
        raise ValueError("Not a BPS patch")
    if zlib.crc32(patch[:-4]) & 0xFFFFFFFF != struct.unpack_from("<I", patch, len(patch) - 4)[0]:
        raise ValueError("The patch checksum is invalid; extract the package again")
    cursor, end = 4, len(patch) - 12

    def number():
        nonlocal cursor
        value, shift = 0, 1
        for _ in range(10):
            if cursor >= end:
                raise ValueError("Truncated BPS number")
            byte = patch[cursor]
            cursor += 1
            value += (byte & 127) * shift
            if byte & 128:
                return value
            shift <<= 7
            value += shift
        raise ValueError("BPS number exceeds supported bounds")

    source_size, target_size, metadata_size = number(), number(), number()
    if not source_size or not 0 < target_size <= 0x100000000:
        raise ValueError("Unsupported ISO size")
    cursor += metadata_size
    if cursor > end:
        raise ValueError("Truncated BPS metadata")
    expected_source, expected_target = struct.unpack_from("<II", patch, end)
    created = False
    try:
        with source.open("rb") as stream:
            if source.stat().st_size != source_size:
                raise ValueError("The source must be the matching clean, full-size ISO")
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as original:
                if zlib.crc32(original) & 0xFFFFFFFF != expected_source:
                    raise ValueError("Source checksum differs: use the clean ISO for this region")
                with output.open("x+b") as destination:
                    created = True
                    destination.truncate(target_size)
                    with mmap.mmap(destination.fileno(), target_size) as target:
                        written = source_relative = target_relative = 0

                        def copy(buffer, offset, length):
                            nonlocal written
                            if offset < 0 or offset + length > len(buffer):
                                raise ValueError("BPS copy exceeds its source")
                            while length:
                                chunk = min(length, 1024 * 1024)
                                target[written:written + chunk] = buffer[offset:offset + chunk]
                                written += chunk
                                offset += chunk
                                length -= chunk

                        while cursor < end:
                            action = number()
                            kind, length = action & 3, (action >> 2) + 1
                            if written + length > target_size:
                                raise ValueError("BPS action exceeds the output size")
                            if kind == 0:
                                copy(original, written, length)
                            elif kind == 1:
                                if cursor + length > end:
                                    raise ValueError("Truncated BPS literal")
                                copy(patch, cursor, length)
                                cursor += length
                            else:
                                delta = number()
                                delta = -(delta >> 1) if delta & 1 else delta >> 1
                                if kind == 2:
                                    source_relative += delta
                                    copy(original, source_relative, length)
                                    source_relative += length
                                else:
                                    target_relative += delta
                                    if not 0 <= target_relative < written:
                                        raise ValueError("BPS target copy references unwritten data")
                                    while length:
                                        chunk = min(length, written - target_relative, 1024 * 1024)
                                        copy(target, target_relative, chunk)
                                        target_relative += chunk
                                        length -= chunk
                        if cursor != end or written != target_size:
                            raise ValueError("BPS output is incomplete")
                        if zlib.crc32(target) & 0xFFFFFFFF != expected_target:
                            raise ValueError("Patched ISO checksum failed")
                        target.flush()
    except BaseException:
        if created:
            output.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    args = parser.parse_args()
    with args.iso.open("rb") as stream:
        game = stream.read(6)
    region = {b"GMSJ01": "jp", b"GMSE01": "us", b"GMSP01": "pal"}.get(game)
    if region is None:
        raise ValueError("Expected a clean JP, US or PAL Super Mario Sunshine ISO")
    folder = Path(__file__).resolve().parent
    patch = folder / "patches" / ("moonshine_" + region + ".bps")
    output = args.iso.with_name(args.iso.stem + " - Moonshine PR13.iso")
    print("Checking the clean ISO, then creating a separate patched copy...")
    apply(args.iso, patch, output)
    print("Ready:", output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
