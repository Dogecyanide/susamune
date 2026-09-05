#!/usr/bin/env python3
"""Validate and summarize Moonshine .bin/.core reports or copied report text."""
from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path
import re
import struct
import zlib

EXCEPTIONS = ("System reset", "Machine check", "DSI", "ISI", "External interrupt",
              "Alignment", "Program", "Floating point unavailable", "Decrementer",
              "System call", "Trace", "Performance monitor", "IABR", "Reserved", "Thermal")
EVENTS = {1: "app init", 2: "context", 3: "setup enter", 4: "setup return",
          5: "stage ready", 6: "practice", 7: "replay", 8: "savestate",
          9: "ghost", 10: "storage", 11: "draw"}
REGIONS = {0x474D534A: "JP", 0x474D5345: "US", 0x474D5350: "PAL"}


def word(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def decode_binary(data: bytes) -> dict:
    if len(data) < 32:
        raise ValueError("Report is truncated")
    magic, version, size = struct.unpack_from(">IHH", data)
    core = magic == 0x53434352
    if magic not in (0x53435248, 0x53434352) or version != 1:
        raise ValueError("Unknown report format/version")
    if size != (512 if core else 2048) or len(data) != size:
        raise ValueError("Report length does not match its format")
    if word(data, 8) != 3:
        raise ValueError("Report was not completely published")
    checksum = zlib.crc32(data[:16] + bytes(4) + data[20:]) & 0xFFFFFFFF
    if checksum != word(data, 16):
        raise ValueError("Report checksum mismatch")
    result = dict(kind="core" if core else "full", verified=True,
                  generation=word(data, 12), checksum=checksum,
                  game_id=word(data, 20), mod_crc32=word(data, 24))
    if core:
        valid = word(data, 228)
        if valid > 1 or data[295] != 0:
            raise ValueError("Invalid core context/build field")
        result.update(exception=word(data, 28), pc=word(data, 176),
                      lr=word(data, 164), sp=word(data, 36),
                      dsisr=word(data, 184), dar=word(data, 188),
                      scene=word(data, 196), app_context=word(data, 192),
                      context_valid=bool(valid),
                      build=data[232:296].split(b"\0", 1)[0].decode("ascii", "replace"))
        result["breadcrumbs"] = [dict(event=word(data, 216), arg0=word(data, 220),
                                      arg1=word(data, 224))]
    else:
        count, sequence = word(data, 292), word(data, 288)
        limits = ((word(data, 876), 512), (word(data, 1396), 64),
                  (word(data, 1468), 64),
                  (struct.unpack_from(">H", data, 1540)[0], 320),
                  (struct.unpack_from(">H", data, 1868)[0], 128))
        if count > 16 or any(actual > maximum for actual, maximum in limits):
            raise ValueError("Report contains an out-of-bounds memory window or event count")
        result.update(exception=struct.unpack_from(">H", data, 44)[0],
                      pc=word(data, 208), lr=word(data, 196), sp=word(data, 68),
                      dsisr=word(data, 48), dar=word(data, 52),
                      scene=word(data, 244), app_context=word(data, 236))
        result["breadcrumbs"] = []
        for index in range(count):
            offset = 296 + ((sequence - count + index) % 16) * 20
            event, high, low, arg0, arg1 = struct.unpack_from(">5I", data, offset)
            result["breadcrumbs"].append(dict(event=event, time_base=(high << 32) | low,
                                              arg0=arg0, arg1=arg1))
        result["backtrace"] = []
        for index in range(32):
            sp, lr = struct.unpack_from(">II", data, 616 + 8 * index)
            if sp == 0:
                break
            result["backtrace"].append(dict(sp=sp, lr=lr))
    return result


def decode_text(text: str) -> dict:
    result = dict(kind="text", verified=False)
    patterns = {
        "pc": r"(?:\bPC\s+|\bsrr0=)([0-9A-Fa-f]{8})",
        "lr": r"(?:\bLR\s+|\blr=)([0-9A-Fa-f]{8})",
        "sp": r"(?:\bSP\s+|\br01=)([0-9A-Fa-f]{8})",
        "dar": r"(?:\bDAR\s+|\bdar=)([0-9A-Fa-f]{8})",
        "dsisr": r"(?:\bDSISR\s+|\bdsisr=)([0-9A-Fa-f]{8})",
        "mod_crc32": r"(?:\bMOD\s+|\bmod_crc32=)([0-9A-Fa-f]{8})",
        "game_id": r"\bgame_id=([0-9A-Fa-f]{8})",
        "scene": r"\bSCENE\s+([0-9A-Fa-f]{8})",
    }
    for key, pattern in patterns.items():
        found = re.search(pattern, text)
        if found:
            result[key] = int(found[1], 16)
    found = re.search(r"(?:\bEXCEPTION\s+|\bexception=)(\d+)", text)
    if found:
        result["exception"] = int(found[1])
    found = re.search(r"REPORT ([0-9A-Fa-f]{8})-([0-9A-Fa-f]{8})", text)
    if found:
        result.update(generation=int(found[1], 16), checksum=int(found[2], 16))
    if "pc" not in result:
        raise ValueError("No recognizable PC/SRR0 in copied report text")
    for region, game_id in (("JP/GMSJ", 0x474D534A), ("US/GMSE", 0x474D5345),
                            ("PAL/GMSP", 0x474D5350)):
        if region in text:
            result.setdefault("game_id", game_id)
    return result


def symbolize(result: dict, manifest: dict) -> None:
    def number(value):
        return int(value, 0) if isinstance(value, str) else int(value)
    if number(manifest["game_id"]) != result.get("game_id") or \
            number(manifest["mod_crc32"]) != result.get("mod_crc32"):
        raise ValueError("Symbol manifest does not match this game's mod CRC")
    symbols = sorted(manifest["symbols"], key=lambda item: number(item["address"]))
    addresses = [number(item["address"]) for item in symbols]
    result["symbols"] = {}
    for key in ("pc", "lr"):
        if key not in result:
            continue
        address = result[key]
        index = bisect.bisect_right(addresses, address) - 1
        if index >= 0 and address - addresses[index] < number(symbols[index]["size"]):
            result["symbols"][key] = f'{symbols[index]["name"]}+0x{address-addresses[index]:X}'


def render(result: dict) -> str:
    lines = [result.get("build", "Moonshine crash report")]
    if "generation" in result:
        lines.append(f'REPORT {result["generation"]:08X}-{result["checksum"]:08X}')
    lines.append("Binary checksum verified" if result["verified"] else
                 "Copied text; binary checksum cannot be verified")
    lines.append(f'{REGIONS.get(result.get("game_id"), "Unknown region")}  '
                 f'MOD {result.get("mod_crc32", 0):08X}')
    exception = result.get("exception", 0xFFFFFFFF)
    lines.append(f'Exception {exception}: {EXCEPTIONS[exception] if exception < len(EXCEPTIONS) else "unknown"}')
    for key in ("pc", "lr", "sp", "dar", "dsisr", "scene"):
        if key in result:
            suffix = result.get("symbols", {}).get(key, "")
            lines.append(f'{key.upper():5} {result[key]:08X} {suffix}'.rstrip())
    for event in result.get("breadcrumbs", []):
        lines.append(f'{EVENTS.get(event["event"], "event " + str(event["event"]))}: '
                     f'{event["arg0"]:08X} {event["arg1"]:08X}')
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--symbols", type=Path, help="CRC-bound release symbol manifest JSON")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        data = args.report.read_bytes()
        if len(data) > 256 * 1024:
            raise ValueError("Report exceeds 256 KiB")
        result = decode_binary(data) if data[:4] in (b"SCRH", b"SCCR") else \
            decode_text(data.decode("utf-8-sig"))
        if args.symbols:
            symbolize(result, json.loads(args.symbols.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Unable to decode report: {error}\n")
    print(json.dumps(result, indent=2) if args.json else render(result))


if __name__ == "__main__":
    main()
