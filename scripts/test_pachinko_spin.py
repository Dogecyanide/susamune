"""Execute the compiled JP parity shim against its narrow retail call gates."""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
CHECKER = 0x80130758
SHIM = 0x804E5820
APP, ORIGINAL = 0x803E6000, 0x8040A378
MARIO, OTHER, STACK = 0x81000000, 0x81010000, 0x81700000
RUN, WAIT, WALK_END, JUMP = 0x04000440, 0x0C400201, 0x0400044A, 0x02000880


def signed16(value):
    return value - 0x10000 if value & 0x8000 else value


class Shim:
    """Small instruction runner; unsupported code fails rather than being skipped."""

    def __init__(self, code, scene, state, original, residue):
        self.code = code
        self.regs = [0x12340000 + i for i in range(32)]
        self.regs[1], self.regs[3], self.regs[4] = STACK, MARIO, STACK + 0x70
        self.memory = {}
        self.writes = []
        self.pc, self.eq = SHIM, False
        self.put(APP + 0xE, scene, 2)
        self.put(ORIGINAL, original)
        self.put(MARIO + 0x7C, state)
        for i, value in enumerate(residue):
            self.put(STACK - 0x20 + 4 * i, value)
        self.writes.clear()
        self.before = dict(self.memory)
        self.before_regs = list(self.regs)

    def get(self, address, size=4):
        return int.from_bytes(bytes(self.memory.get(address + i, 0xCD)
                                    for i in range(size)), "big")

    def put(self, address, value, size=4):
        for i, byte in enumerate(value.to_bytes(size, "big")):
            self.memory[address + i] = byte
        self.writes.append((address, size))

    def run(self):
        for _ in range(50):
            if self.pc in (CHECKER, CHECKER + 4):
                return self
            word, = struct.unpack_from(">I", self.code, self.pc - SHIM)
            op, rt, ra = word >> 26, (word >> 21) & 31, (word >> 16) & 31
            immediate, next_pc = word & 0xFFFF, self.pc + 4
            if op in (14, 15):
                value = signed16(immediate) * (0x10000 if op == 15 else 1)
                self.regs[rt] = ((self.regs[ra] if ra else 0) + value) & 0xFFFFFFFF
            elif op == 24:
                self.regs[ra] = self.regs[rt] | immediate
            elif op in (32, 40):
                self.regs[rt] = self.get(self.regs[ra] + signed16(immediate),
                                         2 if op == 40 else 4)
            elif op in (36, 37):
                address = self.regs[ra] + signed16(immediate)
                self.put(address, self.regs[rt])
                if op == 37:
                    self.regs[ra] = address
            elif op == 11:
                self.eq = self.regs[ra] == signed16(immediate)
            elif op == 31 and ((word >> 1) & 1023) == 32:
                self.eq = self.regs[ra] == self.regs[(word >> 11) & 31]
            elif op == 16:
                if (word >> 21) & 31 != 4 or (word >> 16) & 31 != 2 or word & 3:
                    raise AssertionError("Unexpected conditional branch")
                if not self.eq:
                    next_pc = self.pc + signed16(immediate)
            elif op == 18:
                if word & 3:
                    raise AssertionError("Wrapper must preserve the caller's LR")
                displacement = word & 0x03FFFFFC
                if displacement & 0x02000000:
                    displacement -= 0x04000000
                next_pc = self.pc + displacement
            else:
                raise AssertionError(f"Unsupported wrapper instruction {word:08x}")
            self.pc = next_pc
        raise AssertionError("Wrapper did not reach the retail checker")


class PachinkoSpinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled PPC compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="pachinko-spin-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        cls.objects = {}
        for region in ("jp", "us", "pal"):
            output = work / f"{region}.o"
            subprocess.run([
                str(compiler), "--target=powerpc-gecko-ibm-kuribo-eabi",
                "-Oz", "-std=c++17", "-fsigned-char", "-fno-exceptions", "-fno-rtti",
                "-ffunction-sections", "-fdata-sections", "-Werror",
                "-DIS_EMULATOR=1", f"-DSUSAMUNE_VERSION_{region.upper()}=1",
                "-I", str(ROOT / "include"), "-I", str(ROOT / "include/JSystem"),
                "-c", str(ROOT / "src/pachinko_spin.cpp"), "-o", str(output),
            ], check=True, capture_output=True)
            cls.objects[region] = output
        layout = work / "shim.ld"
        layout.write_text(
            f'INCLUDE "{(ROOT / "maps/jp.ld").as_posix()}"\n'
            f'ENTRY(susamunePachinkoRunningSpin)\nSECTIONS {{ . = {SHIM:#x}; '
            '.shim : { *(.text.susamunePachinkoRunningSpin) } '
            '/DISCARD/ : { *(.text.init*) *(.comment) *(.llvm_addrsig) *(.eh_frame) } }\n'
        )
        linked = work / "shim.elf"
        subprocess.run([str(ROOT / "toolchain/ld.lld.exe"), "-T", str(layout),
                        "-o", str(linked), str(cls.objects["jp"])],
                       check=True, capture_output=True)
        with linked.open("rb") as stream:
            cls.code = ELFFile(stream).get_section_by_name(".shim").data()

    def check_gate(self, scene, state, owner, admitted):
        trial = Shim(self.code, scene, state, owner, (0xDEADBEEF, 1, 2, 3)).run()
        self.assertEqual(trial.pc, CHECKER + (4 if admitted else 0))
        for index in set(range(32)) - {0, 1, 12}:
            self.assertEqual(trial.regs[index], trial.before_regs[index])
        if admitted:
            self.assertEqual(trial.regs[1], STACK - 48)
            self.assertEqual(trial.get(STACK - 48), STACK)
            self.assertEqual([trial.get(STACK - 32 + 4 * i) for i in range(4)],
                             [1, 0, 0, 1])
            self.assertEqual(set(trial.writes), {(STACK - x, 4) for x in (48, 32, 28, 24, 20)})
        else:
            self.assertEqual(trial.regs[1], STACK)
            self.assertEqual(trial.memory, trial.before)
            self.assertEqual(trial.writes, [])

    def test_only_original_mario_running_in_jp_pachinko_episode_zero(self):
        for scene in (0x0100, 0x0200, 0x1500, 0x1600, 0x1601, 0x1700):
            for state in (RUN, WAIT, WALK_END, JUMP, 0x895, 0x896):
                for owner in (MARIO, OTHER, 0):
                    with self.subTest(scene=scene, state=state, owner=owner):
                        self.check_gate(scene, state, owner,
                                        scene == 0x1600 and state == RUN and owner == MARIO)

    def test_us_and_pal_have_no_patch_or_storage(self):
        for region in ("us", "pal"):
            with self.objects[region].open("rb") as stream:
                elf = ELFFile(stream)
                allocated = [section for section in elf.iter_sections()
                             if section["sh_flags"] & 2 and section["sh_size"]]
                self.assertEqual(allocated, [])

    def test_jp_adds_no_persistent_storage(self):
        with self.objects["jp"].open("rb") as stream:
            elf = ELFFile(stream)
            writable = [section for section in elf.iter_sections()
                        if section["sh_flags"] & 3 == 3 and section["sh_size"]]
            self.assertEqual(writable, [])

    def test_measured_history_still_needs_both_missing_directions(self):
        # Native q1/q2 acceptance boundaries from the retail checker.
        def accepted(history):
            flags = [1, 0, 0, 1]
            for angle in history[:-1]:
                if -24576 <= angle <= -8192:
                    flags[1] = 1
                if -8192 < angle < 8192:
                    flags[2] = 1
            return all(flags)
        self.assertTrue(accepted([-12208, -4016, -4016, -5313, -5403, -4016]))
        self.assertFalse(accepted([-12208] * 6))
        self.assertFalse(accepted([-4016] * 6))
        self.assertFalse(accepted([]))
        self.assertFalse(accepted([-12208, -4016]))  # newest sample is excluded


if __name__ == "__main__":
    unittest.main()
