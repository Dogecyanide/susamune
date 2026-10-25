"""Private execute-in-place transport pilot; not a production memory saving.

The real, unchanged CARD encoding module calls harmless MEM1 test doubles.
The standalone DOL embeds a duplicate cold payload solely to stage that test.
No game image, user profile, memory card or existing emulator is modified.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time

from elftools.elf.elffile import ELFFile
from timewarp_state_measure import PpcQuick

ROOT = Path(__file__).resolve().parents[1]
COLD_BASE = 0x71E3F040
WII_COLD_BASE = 0x91E3F040
CALLBACK, SYNC = 0x80354330, 0x803554E0
MOUNT, UNMOUNT = 0x8035873C, 0x803589C0
FONT = 0x8040CE58
FLAGS = ["--target=powerpc-gecko-ibm-kuribo-eabi", "-Oz", "-Xclang",
         "-fmerge-functions", "-fno-exceptions", "-fno-rtti", "-fsigned-char",
         "-ffast-math", "-fpermissive", "-fno-unwind-tables", "-nodefaultlibs",
         "-nostdlib", "-fno-use-cxa-atexit", "-fno-c++-static-destructors",
         "-ffunction-sections", "-fdata-sections", "-nobuiltininc",
         "-nostdinc++", "-std=c++17", "-Werror", "-Wno-main",
         "-Wno-incompatible-library-redeclaration", "-DSUSAMUNE_VERSION_US=1",
         "-DIS_EMULATOR=1", "-I", str(ROOT / "include")]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def run(command, receipt):
    receipt.setdefault("commands", []).append([str(arg) for arg in command])
    subprocess.run(command, check=True)


def long_jump(name, target):
    return (f".globl {name}\n{name}:\n"
            f"lis 12,0x{target >> 16:04x}\nori 12,12,0x{target & 65535:04x}\n"
            "mtctr 12\nbctr\n")


def inspect_cold(path):
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        section = elf.get_section_by_name(".cold")
        data, base = section.data(), section["sh_addr"]
        if not 0 < len(data) <= 4096:
            raise ValueError("Pilot cold payload exceeds its bounded test window")
        for item in elf.iter_sections():
            if item["sh_flags"] & 2 and item["sh_size"] and item.name != ".cold":
                raise ValueError("Unexpected allocated cold state: " + item.name)
        symbols = {sym.name: sym["st_value"] for sym in
                   elf.get_section_by_name(".symtab").iter_symbols() if sym.name}
        calls = []
        for offset, (word,) in enumerate(struct.iter_unpack(">I", data)):
            address = base + offset * 4
            if word >> 26 != 18:
                continue
            displacement = word & 0x3FFFFFC
            if displacement & 0x2000000:
                displacement -= 0x4000000
            target = (displacement if word & 2 else address + displacement) & 0xFFFFFFFF
            if not base <= target < base + len(data):
                raise ValueError("Unbridged cold REL24 branch")
            calls.append({"address": hex(address), "target": hex(target),
                          "link": bool(word & 1)})
        for name, target in (("CARDMountAsync", MOUNT), ("CARDUnmount", UNMOUNT)):
            offset = symbols[name] - base
            expected = struct.pack(">4I", 0x3D800000 | (target >> 16),
                                   0x618C0000 | (target & 65535), 0x7D8903A6, 0x4E800420)
            if data[offset:offset + 16] != expected:
                raise ValueError("Cold outbound gateway differs from its audited words")
        return data, {"base": hex(base), "bytes": len(data), "sha256": sha(data),
                      "entry": hex(symbols["susamuneCardMount"]),
                      "symbols": {name: hex(symbols[name]) for name in
                                  ("susamuneCardMount", "CARDMountAsync", "CARDUnmount")},
                      "direct_branches_stay_inside_cold_image": calls,
                      "outbound_absolute_gateways_checked": True,
                      "mutable_cold_sections": []}


HARNESS = r'''
#include "Dolphin/CARD.h"
volatile u32 *const box = (volatile u32*)0x81700000;
volatile u32 *const work = (volatile u32*)0x81600000;
volatile unsigned short *const font = (volatile unsigned short*)0x8040ce58;
extern "C" const unsigned char cold_image[], cold_image_end[];
extern "C" s32 pilotEntry(s32, void*, CARDCallback);
extern "C" void pilotDetach(s32, s32) { ++work[10]; }

extern "C" __attribute__((section(".mock_callback"), noinline))
void pilotCallback(s32 channel, s32 result) {
    ++work[4];
    if (channel != 3 || result != 0) work[5] |= 1;
}
extern "C" __attribute__((section(".mock_mount"), noinline))
s32 pilotMount(s32 channel, void *area, CARDCallback detach, CARDCallback callback) {
    work[6] = (u32)__builtin_return_address(0);
    ++work[1];
    if (channel != 3 || area != (void*)0x81601000 || detach != pilotDetach ||
        callback != (CARDCallback)0x80354330) work[5] |= 2;
    if (work[0] == 0) return -3;
    if (work[0] == 7) return -5;
    if (work[0] == 4 && work[1] == 1) return -13;
    if (work[0] == 8 && work[1] == 2) return -3;
    callback(channel, 0);
    return 0;
}
extern "C" __attribute__((section(".mock_sync"), noinline))
s32 pilotSync(s32 channel) {
    work[7] = (u32)__builtin_return_address(0);
    ++work[2];
    if (channel != 3) work[5] |= 4;
    const u32 mode = work[0];
    if (mode == 3 || mode == 5) return -13;
    if ((mode == 2 || mode == 6 || mode == 8) && work[2] == 1) return -13;
    return 0;
}
extern "C" __attribute__((section(".mock_unmount"), noinline))
s32 pilotUnmount(s32 channel) {
    work[8] = (u32)__builtin_return_address(0);
    ++work[3];
    if (channel != 3) work[5] |= 8;
    return 0;
}
static u32 hash(const volatile unsigned char *data, u32 bytes) {
    u32 value = 2166136261u;
    while (bytes--) value = (value ^ *data++) * 16777619u;
    return value;
}
static void invalidateCode(unsigned char *start, u32 bytes) {
    for (u32 i = 0; i < bytes; i += 32)
        asm volatile("dcbst 0,%0" :: "r"(start + i) : "memory");
    asm volatile("sync" ::: "memory");
    for (u32 i = 0; i < bytes; i += 32)
        asm volatile("icbi 0,%0" :: "r"(start + i) : "memory");
    asm volatile("sync; isync" ::: "memory");
}
extern "C" void bench() {
    for (u32 i = 0; i < 32; ++i) box[i] = 0;
    const u32 size = cold_image_end - cold_image;
    unsigned char *const cold = (unsigned char*)0x71e3f040;
    box[14] = size;
    box[0] = 0x54574350;
    box[11] = 1;
    for (u32 i = 0; i < 32; ++i) {
        ((volatile unsigned char*)cold)[(int)i - 32] = 0xa5;
        ((volatile unsigned char*)cold)[size + i] = 0x5a;
    }
    for (u32 i = 0; i < size; ++i) cold[i] = cold_image[i];
    box[11] = 2;
    invalidateCode(cold, size);
    box[11] = 3;
    box[12] = hash(cold, size);
    box[13] = hash(cold_image, size);
    u32 seen = 0;
    for (;;) {
        const u32 sequence = box[1];
        if (sequence == seen) continue;
        seen = sequence;
        const u32 mode = box[2];
        box[11] = 4;
        for (u32 i = 0; i < 16; ++i) work[i] = 0;
        work[0] = mode;
        *font = mode == 5 ? 2 : mode == 6 ? 1 : 0;
        if (box[15]) invalidateCode(cold, size);
        const s32 result = pilotEntry(3, (void*)0x81601000, pilotDetach);
        box[4] = (u32)result;
        for (u32 i = 1; i <= 4; ++i) box[4 + i] = work[i];
        box[9] = *font;
        box[10] = work[5] | (work[10] ? 16 : 0);
        box[16] = work[6]; box[17] = work[7]; box[18] = work[8];
        for (u32 i = 0; i < 32; ++i) {
            if (((volatile unsigned char*)cold)[(int)i - 32] != 0xa5 ||
                ((volatile unsigned char*)cold)[size + i] != 0x5a) box[10] |= 32;
        }
        for (u32 i = 0; i < size; ++i)
            if (((volatile unsigned char*)cold)[i] != cold_image[i]) box[10] |= 64;
        box[12] = hash(cold, size);
        box[13] = hash(cold_image, size);
        box[11] = 5;
        asm volatile("sync" ::: "memory");
        box[3] = sequence;
    }
}
asm(".section .text.start,\"ax\"\n.globl _start\n_start:\n"
    "lis 1,0x815f\nori 1,1,0xf000\nli 0,0\nstw 0,0(1)\n"
    "mfmsr 3\nrlwinm 3,3,0,17,15\nmtmsr 3\nisync\nbl bench\nb .\n");
'''


def build(folder, receipt):
    folder.mkdir(parents=True, exist_ok=True)
    compiler = ROOT / "toolchain/clang++.exe"
    linker = ROOT / "toolchain/ld.lld.exe"
    module = ROOT / "src/card_encoding.cpp"
    original = module.read_bytes()
    obj = folder / "card_encoding.o"
    run([compiler, *FLAGS, "-c", module, "-o", obj], receipt)
    gateways = folder / "outbound.s"
    gateways.write_text('.section .text.gateways,"ax"\n' +
                        long_jump("CARDMountAsync", MOUNT) + long_jump("CARDUnmount", UNMOUNT),
                        encoding="ascii")
    gate_obj = folder / "outbound.o"
    run([compiler, "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", gateways,
         "-o", gate_obj], receipt)
    for name, base in (("dolphin", COLD_BASE), ("wii-link-only", WII_COLD_BASE)):
        link, elf = folder / (name + ".ld"), folder / (name + ".elf")
        link.write_text(f"ENTRY(susamuneCardMount)\nSECTIONS {{ . = 0x{base:x}; "
                        ".cold : { *(.text*) *(.rodata*) . = ALIGN(32); } "
                        "/DISCARD/ : { *(.eh_frame*) *(.comment*) } }\n", encoding="ascii")
        run([linker, "--gc-sections", "-T", link, obj, gate_obj, "-o", elf], receipt)
        data, info = inspect_cold(elf)
        (folder / (name + ".bin")).write_bytes(data)
        receipt[name] = info
    cold = (folder / "dolphin.bin").read_bytes()
    entry = int(receipt["dolphin"]["entry"], 16)
    source = folder / "pilot.cpp"
    source.write_text(HARNESS, encoding="ascii")
    asm = folder / "entry-image.s"
    asm.write_text('.section .text.gateway,"ax"\n' + long_jump("pilotEntry", entry) +
                   '.section .rodata.cold_image,"a"\n.balign 32\n.globl cold_image\n'
                   'cold_image:\n.incbin "' + (folder / "dolphin.bin").as_posix() +
                   '"\n.globl cold_image_end\ncold_image_end:\n', encoding="ascii")
    pilot_obj, image_obj = folder / "pilot.o", folder / "entry-image.o"
    run([compiler, *FLAGS, "-fno-builtin", "-c", source, "-o", pilot_obj], receipt)
    run([compiler, "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", asm,
         "-o", image_obj], receipt)
    link = folder / "pilot.ld"
    link.write_text("ENTRY(_start)\nSECTIONS {\n"
                    ".text 0x80004000 : { *(.text.start) *(.text*) . = ALIGN(32); }\n"
                    ". = ALIGN(32); .rodata : { *(.rodata*) . = ALIGN(32); }\n"
                    ". = ALIGN(32); .data : { *(.data*) *(.got*) . = ALIGN(32); }\n"
                    ". = ALIGN(32); .bss : { *(.bss*) *(COMMON) . = ALIGN(32); }\n"
                    ".mock_callback 0x80354330 : { KEEP(*(.mock_callback)) . = ALIGN(32); }\n"
                    ".mock_sync 0x803554e0 : { KEEP(*(.mock_sync)) . = ALIGN(32); }\n"
                    ".mock_mount 0x8035873c : { KEEP(*(.mock_mount)) . = ALIGN(32); }\n"
                    ".mock_unmount 0x803589c0 : { KEEP(*(.mock_unmount)) . = ALIGN(32); }\n"
                    "/DISCARD/ : { *(.eh_frame*) *(.comment*) } }\n", encoding="ascii")
    elf, dol = folder / "pilot.elf", folder / "pilot.dol"
    run([linker, "--gc-sections", "-T", link, pilot_obj, image_obj, "-o", elf], receipt)
    with elf.open("rb") as stream:
        linked = ELFFile(stream)
        symbols = {sym.name: sym["st_value"] for sym in
                   linked.get_section_by_name(".symtab").iter_symbols()}
        for name, target in (("pilotCallback", CALLBACK), ("pilotSync", SYNC),
                             ("pilotMount", MOUNT), ("pilotUnmount", UNMOUNT)):
            if symbols.get(name) != target:
                raise ValueError("Test double is absent or misaligned: " + name)
        receipt["embedded_source_address"] = hex(symbols["cold_image"])
    run([sys.executable, ROOT / "scripts/elf2dol.py", elf, dol], receipt)
    if module.read_bytes() != original:
        raise ValueError("Production candidate changed during pilot build")
    receipt["candidate"] = {"path": str(module), "sha256": sha(original),
                            "unchanged": True, "compile_flags": FLAGS}
    receipt["pilot_dol"] = {"path": str(dol), "sha256": sha(dol.read_bytes())}
    receipt["expected_cold_fnv32"] = fnv(cold)
    receipt["scope"] = {
        "production_source_unchanged": True,
        "uses_real_retail_card_code": False,
        "wii_runtime_proven": False,
        "uses_real_reset_lifecycle": False,
        "mem1_savings_claimed": 0,
        "boot_image_duplicates_cold_bytes_for_test_only": True,
        "mutable_test_state": ["0x81600000..0x81600100", "0x8040ce58..0x8040ce5a",
                               "0x81700000..0x81700080"],
    }
    return dol


class Pilot(PpcQuick):
    MAGIC = b"TWCP"

    def __init__(self, dolphin, folder, dol, receipt, cpu):
        super().__init__(dolphin, folder)
        self.dol, self.receipt, self.cpu = dol, receipt, cpu

    def start(self):
        profile = Path(tempfile.mkdtemp(prefix="profile-", dir=self.folder))
        (profile / "Config").mkdir()
        (profile / "Config/Dolphin.ini").write_text(
            "[Core]\nHLE_BS2 = True\nCPUThread = False\n"
            f"CPUCore = {self.cpu}\nFastmem = False\nMMU = False\n"
            "EmulationSpeed = 0.0\nDefaultISO = \nEnableCheats = False\n"
            "SlotA = 0\nSlotB = 0\nGFXBackend = Null\n"
            "[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
            "PauseOnFocusLost = False\n[Analytics]\nEnabled = False\n", encoding="ascii")
        (profile / "Config/Logger.ini").write_text(
            "[Options]\nWriteToFile = True\nVerbosity = 4\n"
            "[Logs]\nBOOT = True\nCORE = True\nMEMMAP = True\nPOWERPC = True\nCOMMON = True\n",
            encoding="ascii")
        startup = subprocess.STARTUPINFO()
        startup.dwFlags, startup.wShowWindow = 1, 0
        self.process = subprocess.Popen([str(self.dolphin), "-b", "-u", str(profile),
                                         "-e", str(self.dol)], startupinfo=startup)
        self.evidence.update({"owned_pid": self.process.pid, "profile": str(profile),
                              "cpu_core": self.cpu, "dolphin_path": str(self.dolphin),
                              "dolphin_sha256": sha(self.dolphin.read_bytes())})
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
            raise OSError(C.get_last_error(), "Cannot open owned pilot process")
        deadline = time.monotonic() + 20
        self.mem1 = None
        while self.mem1 is None:
            if self.process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Standalone pilot handshake did not start")
            self.find_memory()
            time.sleep(0.1)
        while struct.unpack(">I", self.read(self.CONTROL + 44, 4))[0] != 3:
            if self.process.poll() is not None or time.monotonic() >= deadline:
                self.evidence["last_control_words"] = list(struct.unpack(">19I", self.read(self.CONTROL, 76)))
                raise RuntimeError("Cold staging/cache preparation did not finish")
            time.sleep(0.05)

    def case(self, mode, reentry):
        self.write(self.CONTROL + 8, struct.pack(">I", mode))
        self.write(self.CONTROL + 60, struct.pack(">I", reentry))
        self.sequence += 1
        self.write(self.CONTROL + 4, struct.pack(">I", self.sequence))
        deadline = time.monotonic() + 5
        while struct.unpack(">I", self.read(self.CONTROL + 12, 4))[0] != self.sequence:
            if self.process.poll() is not None or time.monotonic() >= deadline:
                self.evidence["last_control_words"] = list(struct.unpack(">19I", self.read(self.CONTROL, 76)))
                raise RuntimeError("Cold module call did not return")
            time.sleep(0.01)
        words = struct.unpack(">19I", self.read(self.CONTROL, 76))
        result = words[4] if words[4] < 0x80000000 else words[4] - 0x100000000
        actual = (result, *words[5:10])
        expected = [(-3, 1, 0, 0, 0, 0), (0, 1, 1, 0, 1, 0),
                    (0, 2, 2, 1, 2, 1), (-13, 2, 2, 1, 2, 0),
                    (0, 2, 1, 1, 1, 1), (-13, 1, 1, 0, 1, 2),
                    (0, 2, 2, 1, 2, 0), (-5, 1, 0, 0, 0, 0),
                    (-3, 2, 1, 1, 1, 1)][mode]
        cold_size = self.receipt["dolphin"]["bytes"]
        for address in words[16:19]:
            if address and not COLD_BASE <= address < COLD_BASE + cold_size:
                raise RuntimeError("CARD double was not called from the cold code")
        if actual != expected or words[10] or words[12] != self.receipt["expected_cold_fnv32"] or words[13] != words[12]:
            raise RuntimeError(f"Pilot case {mode} failed: {words}")
        if self.read(int(self.receipt["embedded_source_address"], 16), cold_size) != (self.folder / "dolphin.bin").read_bytes():
            raise RuntimeError("Embedded immutable source differs from the linked file")
        return {"mode": mode, "reentry_cache_invalidation": bool(reentry),
                "result": result, "mount_calls": words[5], "sync_calls": words[6],
                "unmount_calls": words[7], "callback_calls": words[8],
                "font_encoding_after": words[9], "argument_and_canary_errors": words[10],
                "cold_and_source_bytes_unchanged": True,
                "cold_compared_byte_for_byte_to_source": True,
                "source_compared_byte_for_byte_to_linked_file": True,
                "card_double_return_addresses": [hex(value) for value in words[16:19]],
                "returned_to_mem1": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/timewarp-cold-pilot")
    parser.add_argument("--dolphin", type=Path)
    parser.add_argument("--cpu-core", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()):
        parser.error("private outputs must stay within this checkout's build directory")
    receipt = {"purpose": "Cold code transport and execution with MEM1 CARD doubles"}
    timer = ROOT / "src/qft_timer.cpp"
    timer_before = sha(timer.read_bytes())
    pilot = None
    try:
        dol = build(folder, receipt)
        if args.dolphin:
            pilot = Pilot(args.dolphin, folder, dol, receipt, args.cpu_core)
            receipt["runtime"] = pilot.evidence
            receipt["cases"] = []
            with pilot:
                for reentry in (0, 1):
                    for mode in range(9):
                        receipt["cases"].append(pilot.case(mode, reentry))
            receipt["runtime_passed"] = True
        else:
            receipt["runtime_passed"] = False
            receipt["runtime_note"] = "Link-only; pass --dolphin for owned standalone execution"
    except Exception as error:
        receipt["failure"] = str(error)
        raise
    finally:
        receipt["timer_sha256_before"] = timer_before
        receipt["timer_sha256_after"] = sha(timer.read_bytes())
        receipt["timer_source_unchanged"] = receipt["timer_sha256_after"] == timer_before
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(folder / "receipt.json"),
                      "runtime_passed": receipt["runtime_passed"],
                      "cold_bytes": receipt["dolphin"]["bytes"],
                      "cases": len(receipt.get("cases", []))}))


if __name__ == "__main__":
    main()
