"""Read immutable saved slots from an owned, unchanged PAL lifecycle fixture."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
import zlib

from timewarp_cross_level_measure import Capture, ROOT, digest
from test_state_codec import reference_quick_frame


class Slots(Capture):
    symbol_file, image_file = "symbols.txt", "input.iso"

    def __init__(self, dolphin, folder, fixture):
        super().__init__(dolphin, folder, fixture)
        self.scope = json.loads((fixture / "scope.json").read_text())
        if self.scope["region"] != "pal":
            raise ValueError("This reader is pinned to the PAL lifecycle fixture")
        self.pad_address = int(self.scope["control"], 0)
        self.callbox = int(self.scope["callbox"], 0)

    def matches_mem1(self, base):
        patch = int(self.scope["private_patch"], 0)
        expected = struct.pack(">I", int(self.scope["after"], 0))
        return self.host_read(base + patch - 0x80000000, 4, False) == expected

    def validate_fixture(self):
        words = [int(word, 0) for word in self.scope["words"]]
        expected = struct.pack(">" + "I" * len(words), *words)
        if self.read(int(self.scope["stub"], 0), len(expected)) != expected:
            raise RuntimeError("Existing input/call adapter differs from its receipt")

    def state(self):
        app = self.read(self.symbols["gpApplication"], 0x48)
        director = struct.unpack(">I", self.read(self.symbols["gpMarDirector"], 4))[0]
        area, episode = app[14:16]
        return {"context": app[8], "scene": area << 8 | episode, "area": area,
                "episode": episode, "flags": 0, "director": hex(director),
                "state": self.read(director + 0x64, 1)[0] if director else 0,
                "stage_setup": self.read(director + 0x260, 1)[0] if director else 0}

    def frozen(self):
        pass

    def call(self, name, *args):
        # Only existing high-level entry/selection APIs are admitted.
        if name not in ("start__5ILingFiUl", "selectSaveSlot__16SavestateManagerFUl",
                        "selectLoadSlot__16SavestateManagerFUl"):
            raise ValueError("Call outside the bounded capture setup")
        if self.read(self.callbox, 4) != bytes(4) or len(args) > 3:
            raise RuntimeError("Existing callbox is busy")
        self.write(self.callbox + 4, struct.pack(">4I", *(list(args) + [0] * (3 - len(args)) + [0xFFFFFFFF])))
        self.write(self.callbox, struct.pack(">I", self.symbols[name]))
        deadline = time.monotonic() + 10
        while self.read(self.callbox, 4) != bytes(4):
            self.alive(deadline)
            time.sleep(0.02)
        return struct.unpack(">I", self.read(self.callbox + 16, 4))[0]

    def save(self, path, label, area, episode=0, slot=0, trigger=True):
        if not 0 <= slot < 3:
            raise ValueError("Invalid slot")
        manager = struct.unpack(">I", self.read(self.symbols["gSavestateMgr"], 4))[0]
        checksum_address = self.symbols["sPackedChecksums__0"] + slot * 4
        metadata_address = 0x712D2F00 + slot * 6936
        if trigger:
            if self.call("selectSaveSlot__16SavestateManagerFUl", manager, slot) != 1:
                raise RuntimeError("Production slot selection refused")
            before = self.read(checksum_address, 4)
            self.feed(1, duration=0.08)
            deadline = time.monotonic() + 60
            while self.read(checksum_address, 4) == before:
                self.alive(deadline)
                time.sleep(0.04)
            time.sleep(0.2)
        state = self.state()
        metadata = self.read(metadata_address, 6936)
        if struct.unpack_from(">3I", metadata) != (0x53555341, 17, 3):
            raise RuntimeError("StoredState version/region differs from the pinned fixture")
        if metadata[20:22] != bytes((area, episode)) or state["scene"] != (area << 8 | episode):
            raise RuntimeError("Stored header and live scene do not match requested area")
        pool = self.read(self.symbols["sPool__0"], 28)
        offset, size = struct.unpack_from(">II", pool, slot * 8)
        memory = struct.unpack(">4I", self.read(self.symbols["sPoolMemory__0"], 16))
        expected_crc = self.read(checksum_address, 4)
        generation, raw_size, packed_size, adler, parent, tag = struct.unpack_from(">6I", metadata, 6912)
        if not generation or size != packed_size or not 0 < raw_size <= 0x1800000:
            raise RuntimeError("StoredState length/generation differs from pool")
        chunks, left, at = [], size, offset
        for bank, capacity in zip(memory[:2], memory[2:]):
            if at >= capacity:
                at -= capacity
                continue
            length = min(left, capacity - at)
            chunks.append(self.read(bank + at, length))
            left -= length
            at = 0
            if not left:
                break
        packed = b"".join(chunks)
        if left or zlib.crc32(packed) != struct.unpack(">I", expected_crc)[0]:
            raise RuntimeError("Captured immutable packed stream failed CRC")
        if (self.read(metadata_address, 6936) != metadata or
                self.read(self.symbols["sPool__0"], 28) != pool or
                self.read(checksum_address, 4) != expected_crc):
            raise RuntimeError("Saved slot changed while reading")
        codec = "Quick" if packed[:4] == b"MSL4" else "Deflate"
        raw = reference_quick_frame(packed, raw_size) if codec == "Quick" else zlib.decompress(packed)
        if len(raw) != raw_size or zlib.adler32(raw) != adler:
            raise RuntimeError("Decoded saved stream failed size/checksum")
        count = struct.unpack_from(">I", metadata, 24)[0]
        spans = [struct.unpack_from(">III", metadata, 40 + i * 12) for i in range(count)]
        app = next(row for row in spans if row[0] == self.symbols["gpApplication"])
        frozen_scene = raw[app[2] + 14:app[2] + 16]
        if frozen_scene != bytes((area, episode)):
            raise RuntimeError("Decoded saved TApplication scene differs from header")
        position_address = struct.unpack('>I', self.read(self.symbols['gpMarioPos'], 4))[0]
        position_span = next(row for row in spans if row[0] <= position_address and
                             position_address + 12 <= row[0] + row[1])
        position_offset = position_span[2] + position_address - position_span[0]
        position = struct.unpack_from('>3f', raw, position_offset)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.with_suffix(".packed").write_bytes(packed)
        path.with_suffix(".metadata").write_bytes(metadata)
        row = {"label": label, "path": str(path), "game_id": "GMSP01", "region": "PAL",
               "snapshot_version": 17, "area": area, "episode": episode, "parent_episode": parent,
               "slot": slot + 1, "save_triggered": trigger,
               "mario_position": position,
               "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
               "metadata_path": str(path.with_suffix(".metadata")),
               "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
               "packed_bytes": size, "packed_sha256": hashlib.sha256(packed).hexdigest(),
               "captured_codec": codec, "generation": generation,
               "scene_evidence": {"live": state, "stored_header": metadata[20:22].hex(),
                                  "decoded_application": frozen_scene.hex()},
               "crc32_checked": True, "adler32_checked": True, "slot_unchanged_during_read": True}
        path.with_suffix(".json").write_text(json.dumps(row, indent=2) + "\n")
        self.rows.append(row)
        print(json.dumps({"captured": label, "raw_bytes": len(raw), "packed_bytes": size}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "build/cross-level/lifecycle")
    args = parser.parse_args()
    folder, fixture = args.out.resolve(), args.fixture.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()) or folder.is_relative_to(fixture):
        parser.error("Outputs must be private to this task's build directory")
    receipt = {"scope": "Same historical PAL Snapshot17 build; production saved streams read immutably. Not current release or Wii restore validation.",
               "source_receipt": json.loads((fixture / "source-receipt.json").read_text()),
               "fixture_sha256": {name: digest(fixture / name) for name in
                                  ("symbols.txt", "scope.json", "source-receipt.json")}}
    timer_before = digest(ROOT / "src/qft_timer.cpp")
    game = Slots(args.dolphin, folder, fixture)
    receipt["runtime"] = game.evidence
    try:
        with game:
            deadline = time.monotonic() + 70
            while game.state()["scene"] != 0xF00 or game.state()["state"] != 4:
                game.alive(deadline)
                game.feed(0x1000)
            time.sleep(3)
            game.call("start__5ILingFiUl", 132, 0)
            game.wait(lambda state: state["scene"] == 0x102 and state["state"] == 4, skip_movie=True)
            for index, (label, area) in enumerate((("Bianco 1", 2), ("Ricco 1", 3), ("Gelato 1", 4))):
                game.warp(index, area)
                game.save(folder / "mixed" / f"slot{index + 1}.raw", label, area)
            same = folder / "same-level"
            same.mkdir(exist_ok=True)
            for suffix in (".raw", ".packed", ".metadata"):
                shutil.copyfile(folder / "mixed" / ("slot3" + suffix), same / ("slot1" + suffix))
            first = dict(game.rows[-1], path=str(same / "slot1.raw"),
                         metadata_path=str(same / "slot1.metadata"))
            (same / "slot1.json").write_text(json.dumps(first, indent=2) + "\n")
            for index in (2, 3):
                game.feed(x=70 if index == 2 else -70, y=30, duration=0.5)
                game.save(same / f"slot{index}.raw", f"Gelato 1 position {index}", 4)
            receipt["completed"] = True
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        receipt["captures"] = game.rows
        receipt["timer_source_unchanged"] = digest(ROOT / "src/qft_timer.cpp") == timer_before
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
