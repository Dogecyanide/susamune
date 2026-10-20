"""Execute the built PPC entry stub and the actual PatchGame orchestration.

This checks addresses/order, not hardware cache behavior or Wii execution.
Existing launcher artifacts are compared when present; the ARM object audit
requires that build. The entry and PatchGame tests compile current sources.
"""
import ctypes as C
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

from mod_transport import BASES, CAPS

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/timewarp-launcher"
TOOLS = ROOT / "launcher/nintendont_devkitpro"
STATUS = 0xD3003420
MASK = 0xFFFFFFFF


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def execute(code, address, lines, cold_address, cold_lines):
    words = struct.unpack(">" + "I" * (len(code) // 4), code)
    registers = [0x11220000 + i for i in range(32)]
    original = registers[:]
    memory = {STATUS + 4: lines, STATUS + 8: address,
              STATUS + 12: cold_lines, STATUS + 16: cold_address}
    entry, polls, pc, ctr, lr, equal = 0x80003154, 0, 0, 0, 0, False
    reads, stores, cache, barriers = [], [], [], []
    for _ in range(16 * (lines + cold_lines + 256) + 128):
        assert 0 <= pc < len(code) and pc % 4 == 0
        instruction, next_pc = words[pc // 4], pc + 4
        op = instruction >> 26
        rt, ra, rb = (instruction >> 21) & 31, (instruction >> 16) & 31, (instruction >> 11) & 31
        immediate = signed(instruction & 65535, 16)
        if op in (14, 15):
            registers[rt] = ((registers[ra] if ra else 0) +
                             (immediate << 16 if op == 15 else immediate)) & MASK
        elif op == 24:
            registers[ra] = registers[rt] | (instruction & 65535)
        elif op in (32, 36):
            target = ((registers[ra] if ra else 0) + immediate) & MASK
            if op == 36:
                stores.append((target, registers[rt]))
                memory[target] = registers[rt]
            else:
                reads.append(target)
                if target == STATUS:
                    polls += 1
                    if polls == 3:
                        memory[STATUS] = entry
                else:
                    assert polls >= 3, "handoff read before acknowledgement"
                registers[rt] = memory[target]
        elif op == 11:
            equal = signed(registers[ra], 32) == immediate
        elif op == 16:
            bo, bi = rt, ra
            assert not instruction & 3
            if bo == 12 and bi == 2:
                take = equal
            elif bo == 16 and bi == 0:
                ctr = (ctr - 1) & MASK
                take = ctr != 0
            else:
                raise AssertionError(f"unknown branch 0x{instruction:08x}")
            if take:
                next_pc = pc + signed(instruction & 0xFFFC, 16)
        elif op == 31:
            xo = (instruction >> 1) & 1023
            if xo == 32:
                equal = registers[ra] == registers[rb]
            elif xo == 467:
                spr = ((instruction >> 16) & 31) | ((instruction >> 6) & 992)
                if spr == 8:
                    lr = registers[rt]
                elif spr == 9:
                    ctr = registers[rt]
                else:
                    raise AssertionError(f"unknown SPR {spr}")
            elif xo in (470, 982):
                target = ((registers[ra] if ra else 0) + registers[rb]) & MASK
                cache.append(("dcbi" if xo == 470 else "icbi", target))
            elif xo == 598:
                barriers.append(("sync", len(cache)))
            else:
                raise AssertionError(f"unknown instruction 0x{instruction:08x}")
        elif instruction == 0x4C00012C:
            barriers.append(("isync", len(cache)))
        elif instruction == 0x4E800020:
            assert lr == entry and barriers == [("sync", len(cache)), ("isync", len(cache))]
            assert all(registers[i] == original[i] for i in range(32) if i not in (0, 3, 4))
            return reads, stores, cache
        else:
            raise AssertionError(f"unknown instruction 0x{instruction:08x}")
        pc = next_pc
    raise AssertionError("entry stub exceeded the bounded instruction count")


def function(source, name):
    start = source.index("void " + name + "(")
    opening = source.index("{", start)
    depth = 1
    for end in range(opening + 1, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if not depth:
            return source[start:end + 1]
    raise AssertionError("unclosed source function")


class BootCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assembler = TOOLS / "devkitPPC/bin/powerpc-eabi-as.exe"
        if not assembler.is_file():
            raise unittest.SkipTest("Launcher PPC toolchain required")
        cls.temp = tempfile.TemporaryDirectory(prefix="mod-boot-cache-")
        cls.addClassCleanup(cls.temp.cleanup)
        temp = Path(cls.temp.name)
        obj = temp / "entry.elf"
        subprocess.run([str(assembler),
                        str(ROOT / "launcher/kernel/asm/FakeEntryLoad.S"), "-o", str(obj)], check=True)
        subprocess.run([str(TOOLS / "devkitPPC/bin/powerpc-eabi-strip.exe"), str(obj),
                        "-O", "binary", "-S", "-s", "-o", str(temp / "entry.bin")], check=True)
        cls.code = (temp / "entry.bin").read_bytes()
        generated = BUILD / "group-ppc/asm/FakeEntryLoad.bin"
        if generated.is_file():
            assert cls.code == generated.read_bytes(), "generated launcher stub is stale"
        source = r'''
#include "susamune/mod_boot.h"
typedef unsigned int u32;
typedef __UINTPTR_TYPE__ uintptr_t;
#define RESET_STATUS 0x13003420u
#define FLUSH_LEN (RESET_STATUS+4)
#define FLUSH_ADDR (RESET_STATUS+8)
#define PATCH_STATE_PATCH 1
static u32 Datel, AppLoaderSize, DOLMinOff, DOLMaxOff, GameEntry, useipl, FirstLine;
static u32 PatchState, TITLE_ID, GAME_ID, TRIGame, drcAddress, drcAddressAligned;
static u32 NeedRelPatches, NeedConstantRelPatches, SusamuneModFlushEnd;
static u32 desiredEnd, desiredCold, desiredLines, mailbox[8], patchedLength, published;
static u32 DI_IRQ, diDelay, retireDelay, retireFail, resumeFail, trace[32], traceCount;
static void event(u32 value) { if(traceCount<32) trace[traceCount++]=value; }
static void DIFinishAsync(void) {event(1);}
static void DIInterrupt(void) {event(2); if(diDelay) --diDelay; else DI_IRQ=0;}
static void SusamuneTransferBeginRetire(void) {event(3);}
static int SusamuneTransferRetireStep(void) {
    event(4); if(retireFail) return 0; if(retireDelay) {--retireDelay;return 0;} return 1;
}
static int SusamuneTransferResumeLegacy(void) {event(7);return !resumeFail;}
static void write32(u32 address,u32 value) {
    if(address==RESET_STATUS) event(8);
    if(address >= RESET_STATUS && address < RESET_STATUS+32) mailbox[(address-RESET_STATUS)/4]=value;
}
static void sync_before_read(void *p,u32 n) {(void)p;(void)n;}
static void sync_after_write(void *p,u32 n) {
    if((uintptr_t)p == RESET_STATUS && n == 32) ++published;
}
static void DoPatches(void *p,u32 n,u32 off) {(void)p;(void)off;patchedLength=n;event(5);}
static void PatchSusamune(void) {
    event(6);
    if (!desiredEnd) return;
    SusamuneModFlushEnd=desiredEnd;
    write32(SUSAMUNE_MOD_BOOT_COLD_START,desiredCold);
    write32(SUSAMUNE_MOD_BOOT_COLD_LINES,desiredLines);
}
#define EXISetTimings(a,b) ((void)0)
#define ISOSetupCache() ((void)0)
#define SIInit() ((void)0)
#define TRIReset() ((void)0)
#define PADSwitchRequired() 0
#define PADForceConnected() 0
#define memset32(p,v,n) ((void)0)
#define Patch31A0() ((void)0)
#define dbgprintf(...) ((void)0)
#define GameRelTimerPatches() 0
#define GameRelConstantTimerPatches() 0
'''
        source += function((ROOT / "launcher/kernel/Patch.c").read_text(), "PatchGame")
        source += r'''
__declspec(dllexport) void run(u32 low,u32 high,u32 end,u32 cold,u32 lines) {
    DOLMinOff=low;DOLMaxOff=high;GameEntry=0x80003154;desiredEnd=end;
    desiredCold=cold;desiredLines=lines;published=0;traceCount=0;PatchGame();
}
__declspec(dllexport) void delay(u32 irq,u32 di,u32 retire,u32 fail,u32 resume) {
    DI_IRQ=irq;diDelay=di;retireDelay=retire;retireFail=fail;resumeFail=resume;
}
__declspec(dllexport) u32 trace_info(u32 index) { return index<32 ? trace[index] : traceCount; }
__declspec(dllexport) u32 info(u32 index) {
    return index<8 ? mailbox[index] : index==8 ? patchedLength : published;
}
'''
        (temp / "patch.c").write_text(source)
        dll = temp / "patch.dll"
        subprocess.run([str(ROOT / "toolchain/clang.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-O2", "-nostdlib", "-ffreestanding", "-fno-builtin",
                        "-fuse-ld=lld", "-Wl,/noentry", "-I" + str(ROOT / "include"),
                        str(temp / "patch.c"), "-o", str(dll), "-Wno-int-to-void-pointer-cast"], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.lib.run.argtypes = [C.c_uint] * 5
        cls.lib.info.argtypes = [C.c_uint]
        cls.lib.info.restype = C.c_uint
        cls.lib.delay.argtypes = [C.c_uint] * 5
        cls.lib.trace_info.argtypes = [C.c_uint]
        cls.lib.trace_info.restype = C.c_uint
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def check_trace(self, address, lines, cold_address, cold_lines):
        reads, stores, actual = execute(self.code, address, lines, cold_address, cold_lines)
        expected = [a for start, count in ((address, lines), (0x80001000, 256), (cold_address, cold_lines))
                    for a in range(start, start + count * 32, 32)]
        self.assertEqual(actual, [(kind, a) for a in expected for kind in ("dcbi", "icbi")])
        self.assertEqual(stores, [(STATUS, 0x4DEA)])
        self.assertEqual(reads.count(STATUS), 3)
        self.assertEqual(STATUS + 16 in reads, bool(cold_lines))

    def setUp(self):
        self.lib.delay(0, 0, 0, 0, 0)

    def patch_trace(self):
        return [self.lib.trace_info(i) for i in range(self.lib.trace_info(32))]

    def test_reset_waits_for_di_and_both_workers_before_any_patch_or_ack(self):
        args = (0x3100, 0x420D60, 0x4E0D60, 0x91E3F0A0, 2239)
        self.lib.run(*args)
        old = [self.lib.info(i) for i in range(9)]
        self.lib.delay(1, 2, 2, 0, 0)
        for expected in ([1, 2], [1, 2], [1, 2, 3, 4], [1, 3, 4]):
            self.lib.run(*args)
            self.assertEqual(self.patch_trace(), expected)
            self.assertEqual([self.lib.info(i) for i in range(9)], old)
            self.assertEqual(self.lib.info(9), 0)
        self.lib.run(*args)
        self.assertEqual(self.patch_trace(), [1, 3, 4, 5, 6, 7, 8])
        self.assertEqual(self.lib.info(9), 1)

    def test_retirement_and_resume_failures_keep_ppc_parked(self):
        args = (0x3100, 0x420D60, 0, 0, 0)
        self.lib.delay(0, 0, 0, 1, 0)
        for _ in range(3):
            self.lib.run(*args)
            self.assertEqual(self.patch_trace(), [1, 3, 4])
            self.assertEqual(self.lib.info(9), 0)
        self.lib.delay(0, 0, 0, 0, 1)
        self.lib.run(*args)
        self.assertEqual(self.patch_trace(), [1, 3, 4, 5, 6, 7])
        self.assertEqual(self.lib.info(9), 0)

    def test_generated_no_cold_skips_stale_pointer_and_preserves_legacy_range(self):
        self.check_trace(0x80003100, 1, 0xFFFFFFFF, 0)
        self.check_trace(0x1300000, 7, 0xFFFFFFFF, 0)

    def test_generated_cold_range_exact_one_line_and_real_payload(self):
        self.check_trace(0x80003100, 5, 0x91E3F0A0, 1)
        self.check_trace(0x80003100, 5, 0x91E3F0A0, 56928 // 32)

    def test_actual_patchgame_reset_clears_stale_cold_and_only_extends_cache_range(self):
        for vma in BASES.values():
            base = vma & 0x7FFFFFFF
            end = max(base + offset + size for offset, size in CAPS)
            low, high = 0x3100, base
            self.lib.run(low, high, end, 0x91E3F0A0, 56928 // 32)
            self.assertEqual(self.lib.info(8), (high - low + 31) & ~31)
            self.assertEqual(self.lib.info(1), (end - low + 31) // 32)
            self.assertEqual([self.lib.info(i) for i in (0, 2, 3, 4, 9)],
                             [0x80003154, low | 0x80000000, 56928 // 32, 0x91E3F0A0, 1])
            self.check_trace(self.lib.info(2), self.lib.info(1), self.lib.info(4), self.lib.info(3))
            self.lib.run(low, high, 0, 0, 0)
            self.assertEqual([self.lib.info(i) for i in (1, 3, 4, 9)],
                             [(high - low + 31) // 32, 0, 0, 1])

    def test_actual_arm_install_path_has_only_word_stores(self):
        obj = BUILD / "group-arm/kernel/CMakeFiles/kernel.dir/Patch.c.obj"
        if not obj.is_file():
            self.skipTest("Compiled launcher ARM Patch object required")
        dump = subprocess.check_output([str(TOOLS / "devkitARM/bin/arm-none-eabi-objdump.exe"), "-d",
            str(obj)], text=True)
        sections = re.split(r"Disassembly of section ", dump)
        selected = [s for s in sections if s.startswith(".text.PatchSusamune:") or s.startswith(".text.SusamuneMod")]
        self.assertGreaterEqual(len(selected), 3)
        conditions = r"(?:eq|ne|cs|cc|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?"
        # strhi is STR with the HI condition, not a halfword store.
        for section in selected:
            mnemonics = re.findall(r"^\s*[0-9a-f]+:\s+[0-9a-f]+\s+(\w+)", section, re.M)
            self.assertFalse([m for m in mnemonics if re.fullmatch(r"str[bh]" + conditions, m)], section.splitlines()[0])
        header = (ROOT / "include/susamune/mod_boot.h").read_text()
        values = [int(v, 16) for v in re.findall(r"#define SUSAMUNE_MOD_BOOT_\w+ (0x[0-9A-Fa-f]+)u", header)]
        self.assertEqual(values, [STATUS + 12 - 0xC0000000, STATUS + 16 - 0xC0000000])


if __name__ == "__main__":
    unittest.main()
