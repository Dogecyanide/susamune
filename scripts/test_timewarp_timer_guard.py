"""Exercise timer guards using temporary receipts, ELF copies and Git inputs."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from elftools.elf.elffile import ELFFile

import timewarp_timer_guard as guard

ROOT = guard.ROOT
TEST_ROOT = ROOT / "build/timewarp-timer-guard-tests"


class TimerGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(guard.BASELINE.read_text())
        cls.console = ROOT / "build/baseline-console"
        cls.emu = ROOT / "build/baseline-emu"
        if not all((build / "susamune_pal.o").exists() for build in (cls.console, cls.emu)):
            raise unittest.SkipTest("Original console and emulator baseline fixtures required")
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        protected = [guard.BASELINE, ROOT / "src/qft_timer.cpp"]
        protected.extend(build / f"susamune_{region}.o" for build in (cls.console, cls.emu)
                         for region in ("jp", "us", "pal"))
        cls.original = {p: guard.digest(p.read_bytes()) for p in protected}

    @classmethod
    def tearDownClass(cls):
        for path, expected in cls.original.items():
            if guard.digest(path.read_bytes()) != expected:
                raise AssertionError(f"Test changed a protected original: {path}")

    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=TEST_ROOT)))

    def candidate(self):
        name = "CMakeFiles/susamune_obj_pal.dir/src/qft_timer.cpp.obj"
        (self.folder / name).parent.mkdir(parents=True)
        shutil.copyfile(self.console / name, self.folder / name)
        output = self.folder / "susamune_pal.o"
        shutil.copyfile(self.console / output.name, output)
        return output

    def verify(self, receipt=None, build=None):
        with redirect_stdout(io.StringIO()):
            guard.verify(receipt or self.receipt, build or self.console, "console", ("pal",))

    def test_all_six_original_baselines(self):
        with redirect_stdout(io.StringIO()):
            for target, build in (("console", self.console), ("emu", self.emu)):
                guard.verify(self.receipt, build, target, ("jp", "us", "pal"))

    def test_linked_cave_byte_change(self):
        path = self.candidate()
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            symbol = next(s for s in elf.get_section_by_name(".symtab").iter_symbols()
                          if "sFreezeCave" in s.name and s["st_size"])
            section = elf.get_section(symbol["st_shndx"])
            self.assertNotEqual(section["sh_type"], "SHT_NOBITS")
            offset = section["sh_offset"] + symbol["st_value"] - section["sh_addr"]
        data = bytearray(path.read_bytes())
        data[offset] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "linked bytes/locations.*sFreezeCave"):
            self.verify(build=self.folder)

    def test_symbol_address_movement(self):
        path = self.candidate()
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            self.assertEqual(elf.elfclass, 32)
            self.assertFalse(elf.little_endian)
            table = elf.get_section_by_name(".symtab")
            index, symbol = next((i, s) for i, s in enumerate(table.iter_symbols())
                                 if "sStatusCave" in s.name and s["st_size"])
            offset = table["sh_offset"] + index * table["sh_entsize"] + 4
            value = symbol["st_value"]
        data = bytearray(path.read_bytes())
        struct.pack_into(">I", data, offset, value + 4)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "linked bytes/locations.*sStatusCave"):
            self.verify(build=self.folder)

    def test_altered_source_receipt(self):
        receipt = copy.deepcopy(self.receipt)
        receipt["sources"]["src/qft_timer.cpp"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source changed.*qft_timer.cpp"):
            self.verify(receipt)

    def test_altered_scratch_receipt(self):
        receipt = copy.deepcopy(self.receipt)
        receipt["builds"]["console-pal"]["layout"]["SUSAMUNE_ADDR_QFT_STATE"] += 4
        with self.assertRaisesRegex(ValueError, "scratch changed.*SUSAMUNE_ADDR_QFT_STATE"):
            self.verify(receipt)

    def test_wrong_release_receipt(self):
        receipt = copy.deepcopy(self.receipt)
        receipt["release"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "protected release"):
            self.verify(receipt)

    def test_capture_cannot_bless_a_different_elf(self):
        for name in ("susamune_jp.o", "mod_jp.bin"):
            shutil.copyfile(self.console / name, self.folder / name)
        elf = self.folder / "susamune_jp.o"
        data = bytearray(elf.read_bytes())
        data[-1] ^= 1
        elf.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Capture artifacts differ"):
            guard.release_artifacts(self.folder, "console")

    def test_capture_never_overwrites_receipt(self):
        receipt = self.folder / "baseline.json"
        receipt.write_bytes(b"keep me")
        with self.assertRaises(FileExistsError):
            guard.capture(self.console, self.emu, receipt)
        self.assertEqual(receipt.read_bytes(), b"keep me")

    def test_non_release_compiler_flags(self):
        lines = {"IS_EMULATOR": "OFF", "ENABLE_DEBUG_WARPS": "OFF",
                 "ENABLE_MEM_DIAGNOSTICS": "OFF", "ENABLE_SAVESTATE_DBG": "OFF",
                 "VERS": "jp;us;pal", "CMAKE_GENERATOR": "Ninja", "CMAKE_BUILD_TYPE": "",
                 "CMAKE_CXX_FLAGS": "-DCHANGED_BASELINE=1"}
        (self.folder / "CMakeCache.txt").write_text("\n".join(f"{k}:STRING={v}" for k, v in lines.items()))
        with self.assertRaisesRegex(ValueError, "Non-release build override: CMAKE_CXX_FLAGS"):
            guard.build_configuration(self.folder, "console")


class CaptureProvenanceTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(dir=TEST_ROOT)))
        files = {"src/qft_timer.cpp": b"released timer\n", "include/layout.h": b"release layout\n",
                 "toolchain/clang++.exe": b"release compiler", "toolchain/ld.lld.exe": b"release linker"}
        for name, data in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Timer guard test", "-c", "user.email=timer-test@example.invalid",
                 "commit", "-qm", "Private provenance fixture")
        release = self.git("rev-parse", "HEAD").strip()
        self.enterContext(patch.object(guard, "ROOT", self.root))
        self.enterContext(patch.object(guard, "RELEASE", release))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True, stderr=subprocess.PIPE)

    def test_clean_release_inputs_have_receipt(self):
        provenance = guard.release_sources()
        self.assertEqual(provenance["input_count"], 4)
        self.assertIn("toolchain/clang++.exe", provenance["git_blobs"])

    def test_dirty_non_timer_header_rejected(self):
        (self.root / "include/layout.h").write_bytes(b"different layout\n")
        with self.assertRaisesRegex(ValueError, "Capture inputs differ.*include/layout.h"):
            guard.release_sources()

    def test_changed_compiler_rejected(self):
        (self.root / "toolchain/clang++.exe").write_bytes(b"another compiler")
        with self.assertRaisesRegex(ValueError, "Capture inputs differ.*clang"):
            guard.release_sources()

    def test_untracked_compile_input_rejected(self):
        (self.root / "src/new.cpp").write_bytes(b"unreleased input\n")
        with self.assertRaisesRegex(ValueError, "Unreleased build inputs.*src/new.cpp"):
            guard.release_sources()


if __name__ == "__main__":
    unittest.main(verbosity=2)
