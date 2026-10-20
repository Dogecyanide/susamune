"""Capture distinct levels in an owned historical PAL proof, without editing it.

Uses that fixture's existing warp wheel and frozen-span export mailbox.
Outputs are private measurement inputs, not portable states or restore proof.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time

from timewarp_state_measure import PpcQuick

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(data)
    return value.hexdigest()


class Capture(PpcQuick):
    def __init__(self, dolphin, folder, fixture):
        super().__init__(dolphin, folder)
        self.fixture = fixture
        self.symbols = {}
        for line in (fixture / getattr(self, "symbol_file", "pal-input-symbols.txt")).read_text().splitlines():
            words = line.split()
            if len(words) == 3:
                self.symbols[words[2]] = int(words[0], 16)
        self.proof = self.symbols.get("gRc1JpProof")
        self.capture = self.symbols.get("gCapacityProof")
        self.fake = None
        self.target = None
        self.rows = []

    def regions(self):
        class Info(C.Structure):
            _fields_ = [("base", C.c_void_p), ("allocation", C.c_void_p),
                        ("aprotect", C.c_ulong), ("size", C.c_size_t),
                        ("state", C.c_ulong), ("protect", C.c_ulong), ("kind", C.c_ulong)]
        address = 0
        while address < 0x7FFFFFFFFFFF:
            info = Info()
            if not self.kernel.VirtualQueryEx(self.handle, address, C.byref(info), C.sizeof(info)):
                break
            base = int(info.base or 0)
            if info.state == 0x1000 and info.protect & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80):
                yield base, info.size
            address = base + info.size

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        profile = Path(tempfile.mkdtemp(prefix="profile-", dir=self.folder))
        (profile / "Config").mkdir()
        (profile / "Config/Dolphin.ini").write_text(
            "[Core]\nHLE_BS2 = True\nCPUThread = False\nCPUCore = 1\nFastmem = False\n"
            "MMU = False\nEmulationSpeed = 1.0\nDefaultISO = \nEnableCheats = False\n"
            "SkipIdle = True\nTimingVariance = 40\nSyncOnSkipIdle = True\nSyncGPU = False\n"
            "SyncGpuMaxDistance = 200000\nSyncGpuMinDistance = -200000\nSyncGpuOverclock = 1.0\n"
            "FPRF = False\nAccurateNaNs = False\nSelectedLanguage = 0\nOverrideGCLang = False\n"
            "SlotA = 0\nSlotB = 0\nSIDevice0 = 6\nSIDevice1 = 0\nSIDevice2 = 0\nSIDevice3 = 0\n"
            "GFXBackend = D3D\nDSPHLE = True\n[Display]\nPAL60 = True\n"
            "[Interface]\nConfirmStop = False\nUsePanicHandlers = False\nPauseOnFocusLost = False\n"
            "[Analytics]\nEnabled = False\nPermissionAsked = True\n[DSP]\nBackend = No Audio Output\nVolume = 0\nEnableJIT = True\n",
            encoding="ascii")
        (profile / "Config/GCPadNew.ini").write_text("[GCPad1]\nDevice = \n", encoding="ascii")
        startup = subprocess.STARTUPINFO()
        startup.dwFlags, startup.wShowWindow = 1, 0
        image = self.fixture / getattr(self, "image_file", "pal_input.iso")
        self.process = subprocess.Popen([str(self.dolphin), "-b", "-u", str(profile),
                                         "-e", str(image)], startupinfo=startup)
        self.evidence.update({"owned_pid": self.process.pid, "profile": str(profile),
                              "source_iso": str(image), "source_iso_sha256": digest(image),
                              "dolphin_sha256": digest(self.dolphin)})
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [C.c_ulong, C.c_bool, C.c_ulong]
        self.kernel.OpenProcess.restype = C.c_void_p
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.kernel.ReadProcessMemory.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p,
                                                  C.c_size_t, C.c_void_p]
        self.kernel.WriteProcessMemory.argtypes = self.kernel.ReadProcessMemory.argtypes
        self.kernel.VirtualQueryEx.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t]
        self.kernel.VirtualQueryEx.restype = C.c_size_t
        self.handle = self.kernel.OpenProcess(0x438, False, self.process.pid)
        if not self.handle:
            raise OSError(C.get_last_error(), "Cannot open owned capture process")
        deadline = time.monotonic() + 25
        self.mem1 = None
        while self.mem1 is None:
            self.alive(deadline)
            for base, size in self.regions():
                if size >= 0x1800000 and self.host_read(base, 6, False) == b"GMSP01":
                    if self.matches_mem1(base):
                        self.mem1 = base
                        break
            time.sleep(0.1)
        self.validate_fixture()
        print(json.dumps({"started": self.evidence, "state": self.state()}), flush=True)

    def matches_mem1(self, base):
        return self.host_read(base + self.proof - 0x80000000, 4, False) == b"JP3P"

    def validate_fixture(self):
        if self.read(self.capture, 4) != b"CAPP":
            raise RuntimeError("Frozen capture mailbox does not match the source fixture")

    def alive(self, deadline):
        if self.process.poll() is not None or time.monotonic() >= deadline:
            raise TimeoutError("Owned capture process exited or operation timed out")

    def address(self, guest):
        if 0x70000000 <= guest < 0x72000000:
            if self.fake is None:
                for base, size in self.regions():
                    if size >= 0x2000000 and self.host_read(base + 0xFF5B80, 8, False) == bytes.fromhex("0408080808010802"):
                        self.fake = base
                        break
                if self.fake is None:
                    raise RuntimeError("Historical fixture's fake-VMEM marker not found")
            return self.fake + guest - 0x70000000
        return super().address(guest)

    def state(self):
        words = struct.unpack(">24I", self.read(self.proof, 96))
        if words[0] != 0x4A503350:
            raise RuntimeError("Proof mailbox identity changed")
        context = self.read(self.symbols["gpApplication"] + 8, 1)[0]
        director = struct.unpack(">I", self.read(self.symbols["gpMarDirector"], 4))[0]
        return {"request": words[1], "ack": words[2], "result": words[6],
                "frames": words[7], "scene": words[8], "area": words[8] >> 8,
                "episode": words[8] & 255, "state": words[9], "flags": words[10],
                "context": context, "director": hex(director),
                "stage_setup": self.read(director + 0x260, 1)[0] if director else 0,
                "generations": list(words[11:14]), "packed": list(words[14:17])}

    def feed(self, buttons=0, x=0, y=0, duration=0.18):
        pad = getattr(self, "pad_address", self.symbols["mPadStatus__10JUTGamePad"])
        data = struct.pack(">HbbbbBBBBbB", buttons, x, y, 0, 0, 0, 0, 0, 0, 0, 0)
        end = time.monotonic() + duration
        while time.monotonic() < end:
            self.write(pad, data)
            time.sleep(0.005)
        self.write(pad, bytes(12))
        time.sleep(0.2)

    def frozen(self):
        words = struct.unpack(">8I", self.read(self.capture, 32))
        magic, sequence, released, count, raw, slot, capacity, used = words
        if not sequence or sequence == released:
            return
        try:
            if magic != 0x43415050 or count > 64 or slot >= 3 or not self.target or raw > 0x1800000:
                raise RuntimeError("Invalid frozen-span request")
            state = self.state()
            spans, pieces, offset = [], [], 0
            for index in range(count):
                address, size = struct.unpack(">II", self.read(self.capture + 32 + index * 8, 8))
                if size > raw - offset or (size and not (
                    0x80000000 <= address <= 0x81800000 - size or
                    0x70000000 <= address <= 0x72000000 - size)):
                    raise RuntimeError("Frozen source span is out of bounds")
                pieces.append(self.read(address, size) if size else b"")
                spans.append({"address": hex(address), "size": size, "offset": offset})
                offset += size
            if offset != raw:
                raise RuntimeError("Frozen size differs from its spans")
            data = b"".join(pieces)
            target, label, area, episode = self.target
            if state["area"] != area or state["episode"] != episode:
                raise RuntimeError("Capture scene differs from requested level")
            app = next(row for row in spans if row["address"] == "0x803e10c0")
            raw_scene = data[app["offset"] + 0xE:app["offset"] + 0x10]
            if raw_scene != bytes((area, episode)):
                raise RuntimeError("Frozen TApplication scene differs from proof mailbox")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            row = {"label": label, "path": str(target), "region": "PAL", "game_id": "GMSP01",
                   "area": area, "episode": episode, "raw_bytes": raw, "sha256": hashlib.sha256(data).hexdigest(),
                   "scene_evidence": {"proof_mailbox": state, "frozen_application_scene": raw_scene.hex()},
                   "capture_sequence": sequence, "capacity": capacity, "used": used, "spans": spans}
            target.with_suffix(".json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
            self.rows.append(row)
            self.target = None
            print(json.dumps({"captured": label, "scene": raw_scene.hex(), "raw_bytes": raw}), flush=True)
        finally:
            self.write(self.capture + 8, struct.pack(">I", sequence))

    def wait(self, predicate, timeout=80, skip_movie=False):
        deadline = time.monotonic() + timeout
        phase = None
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("Capture wait timed out: " + json.dumps(self.state()))
            self.alive(deadline)
            self.frozen()
            state = self.state()
            current = state["scene"], state["state"], state["flags"], state["context"]
            if current != phase:
                print(json.dumps({"state": state}), flush=True)
                phase = current
            if predicate(state):
                return state
            if skip_movie and state["context"] == 6:
                self.feed(0x1000)
            time.sleep(0.04)

    def command(self, kind, arg=0, arg2=0):
        seq = self.state()["request"] + 1
        self.write(self.proof + 12, struct.pack(">3I", kind, arg, arg2))
        self.write(self.proof + 4, struct.pack(">I", seq))
        result = self.wait(lambda state: state["ack"] == seq)
        if result["result"] != 1:
            raise RuntimeError("Historical proof command refused: " + json.dumps(result))
        return self.wait(lambda state: state["frames"] >= result["frames"] + 2)

    def ready(self, area):
        self.wait(lambda state: state["scene"] == area << 8 and state["state"] == 4,
                  skip_movie=True)
        time.sleep(1)

    def warp(self, root, area):
        if self.state()["flags"] & 1:
            self.command(4)
        self.feed(0x10)
        if self.read(self.symbols["sShown__0"], 1) != b"\1":
            raise RuntimeError("Existing warp wheel did not open")
        directions = [(0, 100), (80, 80), (100, 0)]
        self.feed(0x100, *directions[root])
        if self.read(self.symbols["sRoot__0"], 1)[0] != root:
            raise RuntimeError("Existing warp wheel selected a different root")
        self.feed(0x100, 0, 100)
        self.ready(area)

    def save(self, path, label, area):
        if not self.state()["flags"] & 1:
            self.command(4)
        self.target = path, label, area, 0
        self.command(2, 0)
        if self.target:
            raise RuntimeError("Save completed without frozen source capture")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "build/cross-level")
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()) or folder.is_relative_to(args.fixture.resolve()):
        parser.error("Outputs must be private to this task's build directory")
    receipt = {"scope": "Same historical PAL capture build, distinct actual areas; not release gameplay or restore validation.",
               "source_fixture": str(args.fixture.resolve()), "captures": []}
    fixture = args.fixture.resolve()
    receipt["fixture_sha256"] = {name: digest(fixture / name) for name in
                                  ("adapter.cpp", "savestate.proof.cpp", "proof-baseline.json", "pal-input-symbols.txt")}
    receipt["fixture_baseline"] = json.loads((fixture / "proof-baseline.json").read_text())
    source = (fixture / "savestate.proof.cpp").read_text()
    receipt["snapshot_version"] = int(re.search(r"kSnapshotVersion = (\d+)u", source)[1])
    timer_before = digest(ROOT / "src/qft_timer.cpp")
    game = Capture(args.dolphin, folder, fixture)
    receipt["runtime"] = game.evidence
    try:
        with game:
            deadline = time.monotonic() + 70
            while game.state()["scene"] != 0xF00 or game.state()["state"] != 4:
                game.alive(deadline)
                game.feed(0x1000)
            time.sleep(3)
            game.command(1, 0)
            game.ready(1)
            for index, (name, area) in enumerate((("Bianco 1", 2), ("Ricco 1", 3), ("Gelato 1", 4))):
                game.warp(index, area)
                game.save(folder / "mixed" / f"slot{index + 1}.raw", name, area)
                receipt["captures"] = game.rows
                (folder / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            same = folder / "same-level"
            same.mkdir(exist_ok=True)
            shutil.copyfile(folder / "mixed/slot3.raw", same / "slot1.raw")
            shutil.copyfile(folder / "mixed/slot3.json", same / "slot1.json")
            for index in (2, 3):
                game.command(4)
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
        (folder / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
