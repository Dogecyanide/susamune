"""Deterministic V4 boot transport; runtime savestate encoding is unchanged."""
from pathlib import Path
from collections import deque
import re
import struct
import zlib

from lz4.block import compress as compress_lz4

ROOT = Path(__file__).resolve().parents[1]


def shared_define(name, header="mod_bin.h"):
    source = (ROOT / "include/susamune" / header).read_text()
    match = re.search(r"^#define\s+" + re.escape(name) + r"\s+(0x[0-9a-fA-F]+|[0-9]+)u?\b", source, re.M)
    if not match:
        raise ValueError(f"Missing shared constant {name}")
    return int(match[1], 0)


MAGIC, VERSION, HEADER, DESCRIPTOR = shared_define("SUSAMUNE_MOD_MAGIC"), shared_define("SUSAMUNE_MOD_VERSION_V4"), 64, 32
RAW, QUICK, XIP = range(3)
GAMES = {name: shared_define("SUSAMUNE_MOD_GAME_ID_" + name.upper()) for name in ("jp", "us", "pal")}
BASES = {game: shared_define("SUSAMUNE_MOD_BASE_" + name.upper()) for name, game in GAMES.items()}
CAPS = ((0, shared_define("SUSAMUNE_MOD_MEM1_WORKING_CAP_SIZE")),
        (shared_define("SUSAMUNE_MOD_UPPER_OFFSET"), shared_define("SUSAMUNE_MOD_UPPER_SIZE")))
ARENA = shared_define("SUSAMUNE_MOD_REGION_SIZE") + shared_define("SUSAMUNE_DEBUG_STACK_SIZE")
STAGE = shared_define("SUSAMUNE_MEM2_MODBIN_PPC_BASE", "mem2_map.h")
CEILING = shared_define("SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE", "mem2_map.h")
JP_CEILING = CEILING
BLOCK = 0x20000


def align32(value):
    return (value + 31) & ~31


def stage(flags):
    if type(flags) is not int or flags not in (0, 1):
        raise ValueError("invalid environment")
    return shared_define("SUSAMUNE_MOD_DOLPHIN_STAGING_PPC_BASE") if flags else STAGE


def _extension(output, length):
    while length >= 255:
        output.append(255)
        length -= 255
    output.append(length)


def _lz4(raw, depth=1, lazy=False):
    output, positions = bytearray(), {}
    anchor = cursor = 0

    def remember(offset):
        key = raw[offset:offset + 4]
        if key not in positions:
            positions[key] = deque(maxlen=depth)
        positions[key].append(offset)

    def match(offset):
        key = raw[offset:offset + 4]
        previous, length = None, 3
        for candidate in reversed(positions.get(key, ())):
            if offset - candidate > 65535:
                break
            if length >= 4 and raw[candidate + length] != raw[offset + length]:
                continue
            amount = 4
            while offset + amount < len(raw) - 5 and raw[candidate + amount] == raw[offset + amount]:
                amount += 1
            if amount > length:
                previous, length = candidate, amount
        return previous, length

    # The last match starts at least 12 bytes before the end; five final literals remain.
    while cursor <= len(raw) - 12:
        previous, length = match(cursor)
        remember(cursor)
        if previous is None:
            cursor += 1
            continue
        # One literal may expose a substantially longer overlapping match.
        if lazy and cursor < len(raw) - 12 and match(cursor + 1)[1] > length + 1:
            cursor += 1
            continue
        literals = cursor - anchor
        output.append((min(literals, 15) << 4) | min(length - 4, 15))
        if literals >= 15:
            _extension(output, literals - 15)
        output.extend(raw[anchor:cursor])
        output.extend(struct.pack("<H", cursor - previous))
        if length >= 19:
            _extension(output, length - 19)
        end = cursor + length
        for offset in range(cursor + 1, end):
            remember(offset)
        cursor = anchor = end
    literals = len(raw) - anchor
    output.append(min(literals, 15) << 4)
    if literals >= 15:
        _extension(output, literals - 15)
    output.extend(raw[anchor:])
    return bytes(output)


def encode_quick(raw):
    raw = bytes(raw)
    if not raw:
        raise ValueError("Quick requires nonempty initialized data")
    output = bytearray(struct.pack(">2I", 0x4D534C34, BLOCK))
    for start in range(0, len(raw), BLOCK):
        block = raw[start:start + BLOCK]
        # A longer local match can hurt later choices; retain the smaller stream.
        encoded = min((_lz4(block), _lz4(block, 4), _lz4(block, 32),
                       _lz4(block, 512, lazy=True),
                       compress_lz4(block, mode="high_compression", compression=12,
                                    store_size=False)), key=len)
        plain = len(encoded) >= len(block)
        payload = block if plain else encoded
        output.extend(struct.pack(">2I", len(block), len(payload) | (0x80000000 if plain else 0)))
        output.extend(payload)
    result = bytes(output)
    if decode_quick(result, len(raw)) != raw:
        raise ValueError("Boot compression failed its round trip")
    return result


def decode_quick(packed, expected):
    if len(packed) < 8 or packed[:8] != struct.pack(">2I", 0x4D534C34, BLOCK):
        raise ValueError("Invalid Quick header")
    cursor, result = 8, bytearray()
    while len(result) < expected:
        if len(packed) - cursor < 8:
            raise ValueError("Truncated Quick block")
        raw, size = struct.unpack_from(">2I", packed, cursor)
        cursor += 8
        plain, size = bool(size & 0x80000000), size & 0x7FFFFFFF
        if (raw != min(BLOCK, expected - len(result)) or not size or
                (size != raw if plain else size >= raw) or size > len(packed) - cursor):
            raise ValueError("Invalid Quick block lengths")
        payload = packed[cursor:cursor + size]
        cursor += size
        if plain:
            result.extend(payload)
            continue
        block, at = bytearray(), 0

        def length(initial):
            nonlocal at
            count = initial
            if initial == 15:
                while True:
                    if at == len(payload):
                        raise ValueError("Truncated LZ4 length")
                    extra = payload[at]
                    at += 1
                    count += extra
                    if extra != 255:
                        break
            return count

        while at < size:
            token = payload[at]
            at += 1
            literals = length(token >> 4)
            if literals > size - at or literals > raw - len(block):
                raise ValueError("LZ4 literals overrun")
            block.extend(payload[at:at + literals])
            at += literals
            if at == size:
                break
            if size - at < 2 or raw - len(block) < 12:
                raise ValueError("Invalid LZ4 match start")
            distance = int.from_bytes(payload[at:at + 2], "little")
            at += 2
            match = length(token & 15) + 4
            if not 0 < distance <= len(block) or match > raw - len(block) - 5:
                raise ValueError("Invalid LZ4 match")
            for _ in range(match):
                block.append(block[-distance])
        if len(block) != raw:
            raise ValueError("Wrong decoded LZ4 length")
        result.extend(block)
    if cursor != len(packed):
        raise ValueError("Trailing Quick data")
    return bytes(result)


def build_mod_v4(game, segments, writes, *, flags=0, cold=None, cold_vma=None, menu_code=None, menu_vma=None):
    source = stage(flags)
    if game not in BASES or len(segments) != 2:
        raise ValueError("unsupported game or segment count")
    if menu_code is not None and cold is None:
        raise ValueError("Menu extension requires the established cold image")
    count = 4 if menu_code is not None else 3 if cold is not None else 2
    body = bytearray(count * DESCRIPTOR)
    descriptors = [None] * count
    hot_memory = 0

    def append(index, target, raw_size, memory, payload, kind):
        offset = len(body)
        body.extend(payload)
        body.extend(bytes(align32(len(body)) - len(body)))
        descriptors[index] = (target, raw_size, memory, offset, len(payload), kind, zlib.crc32(payload), 0)

    if cold is not None:
        cold = bytes(cold)
        expected = source + HEADER + count * DESCRIPTOR
        if not cold or len(cold) & 31 or cold_vma != expected:
            raise ValueError("cold image must be aligned and linked at its exact in-file VMA")
        append(2, expected, len(cold), len(cold), cold, XIP)
    elif cold_vma is not None:
        raise ValueError("cold VMA without image")
    for index, (segment, (offset, cap)) in enumerate(zip(segments, CAPS)):
        raw, memory = bytes(segment["raw"]), segment["memory_size"]
        if (segment["offset"] != offset or type(memory) is not int or
                not len(raw) <= memory <= cap or (len(raw) | memory) & 3):
            raise ValueError("hot segment exceeds its permitted MEM1 span")
        hot_memory += memory
        packed = segment.get("quick")
        if packed is None:
            append(index, offset, len(raw), memory, raw, RAW)
        else:
            packed = bytes(packed)
            if not raw or decode_quick(packed, len(raw)) != raw:
                raise ValueError("Quick payload differs from the initialized image")
            append(index, offset, len(raw), memory, packed, QUICK)
    if menu_code is not None:
        raw = bytes(menu_code)
        expected = shared_define("SUSAMUNE_MENU_CODE_" + ("DOLPHIN" if flags else "CONSOLE") +
                                 "_PPC_BASE", "mem2_map.h")
        if not raw or len(raw) & 31 or len(raw) > shared_define("SUSAMUNE_MENU_CODE_SIZE", "mem2_map.h") or menu_vma != expected:
            raise ValueError("Menu code exceeds its fixed presentation span")
        packed = encode_quick(raw)
        if decode_quick(packed, len(raw)) != raw:
            raise ValueError("Menu code compression differs")
        append(3, expected, len(raw), len(raw), packed, QUICK)
    elif menu_vma is not None:
        raise ValueError("Menu destination without image")
    code_size = len(body)
    for address, value in writes:
        if type(address) is not int or address & 3 or not 0x80000000 <= address < BASES[game]:
            raise ValueError("hook outside retail MEM1")
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("invalid hook value")
        body.extend(struct.pack(">2I", address, value))
    body.extend(bytes(align32(len(body)) - len(body)))
    for i, descriptor in enumerate(descriptors):
        struct.pack_into(">8I", body, i * DESCRIPTOR, *descriptor)
    header = bytearray(struct.pack(">16I", MAGIC, VERSION, game, BASES[game], code_size,
                                  len(writes), ARENA, hot_memory, count,
                                  zlib.crc32(body), 0, flags, 0, 0, 0, 0))
    struct.pack_into(">I", header, 40, zlib.crc32(header))
    result = bytes(header + body)
    if len(result) > (JP_CEILING if game == GAMES["jp"] else CEILING):
        raise ValueError("container exceeds reset-safe regional ceiling")
    return result
