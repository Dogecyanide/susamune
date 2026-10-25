"""Native fixed-span installation and actual PPC cross-span branch proofs."""
from copy import deepcopy
import ctypes as C
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zlib
import mod_transport as mt
import timewarp_cold_cluster as cold
import link_pinned_mod as pinned
from test_pinned_cold_target_identity import fixture
from timewarp_emulator_export import build_bootstrap

ROOT = Path(__file__).resolve().parents[1]
CAP = 0x4100


def seal(p):
    struct.pack_into(">I", p, 36, zlib.crc32(p[64:]))
    struct.pack_into(">I", p, 40, 0)
    struct.pack_into(">I", p, 40, zlib.crc32(p[:64]))
    return p


def image(flags=0):
    menu = bytes(range(256)) * 4
    spans = [dict(offset=o, memory_size=64, raw=bytes([i + 1]) * 32)
             for i, (o, _) in enumerate(mt.CAPS)]
    address = mt.shared_define("SUSAMUNE_MENU_CODE_" +
        ("DOLPHIN" if flags else "CONSOLE") + "_PPC_BASE", "mem2_map.h")
    p = mt.build_mod_v4(mt.GAMES["jp"], spans, [], flags=flags,
        cold=bytes(range(32)), cold_vma=mt.stage(flags) + 0xC0,
        menu_code=menu, menu_vma=address)
    return p, menu, address


class MenuSegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="menu-segment-", dir=ROOT / "build")
        folder = Path(cls.temp.name)
        source = folder / "check.c"
        source.write_text('''#include "susamune/mod_bin.h"
__declspec(dllexport) int install(const void*p,unsigned n,unsigned f,void*d,void*m,unsigned cap,unsigned vma) {
return SusamuneModV4InstallMapped(p,n,SUSAMUNE_MOD_GAME_ID_JP,f,SusamuneModV4Stage(f),d,SUSAMUNE_MOD_REGION_SIZE,SUSAMUNE_MOD_BASE_JP,m,cap,vma); }
''')
        dll = folder / "check.dll"
        subprocess.run([str(ROOT / "toolchain/clang.exe"), "--target=x86_64-pc-windows-msvc",
            "-std=c11", "-O2", "-fno-builtin", "-ffreestanding", "-Wall", "-Wextra",
            "-Werror", "-I", str(ROOT / "include"), "-shared", "-nostdlib", "-fuse-ld=lld",
            "-Wl,/noentry", str(source), "-o", str(dll)], check=True,
            env=dict(os.environ, TEMP=str(folder), TMP=str(folder)))
        cls.lib = C.CDLL(str(dll))
        cls.lib.install.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_void_p,
                                   C.c_void_p, C.c_uint, C.c_uint]

    @classmethod
    def tearDownClass(cls):
        C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle))
        cls.temp.cleanup()

    def run_install(self, p, flags, valid, *, pointer=None, cap=CAP, vma=None):
        _, expected_menu, address = image(flags)
        src = C.create_string_buffer(bytes(p))
        hot = C.create_string_buffer(bytes([0xA7]) * (0xC0000 + 128))
        menu = C.create_string_buffer(bytes([0xA7]) * (CAP + 128))
        hp = C.addressof(hot) + 64
        mp = (C.addressof(menu) + 63) & ~31
        mo = mp - C.addressof(menu)
        before = hot.raw, menu.raw
        if pointer == "unaligned":
            mp += 1
        elif pointer == "source":
            mp = (C.addressof(src) + 31) & ~31
        elif pointer == "hot":
            mp = (hp + 31) & ~31
        elif pointer == "null":
            mp = 0
        expected = bytearray(hot.raw)
        expected[64:128] = bytes([1]) * 32 + bytes(32)
        expected[64 + 0x80000:128 + 0x80000] = bytes([2]) * 32 + bytes(32)
        expected_extra = bytearray(menu.raw)
        expected_extra[mo:mo + len(expected_menu)] = expected_menu
        for _ in range(2):
            status = self.lib.install(src, len(p), flags, hp, mp, cap,
                                      address if vma is None else vma)
            if valid:
                self.assertEqual(status, 0)
                self.assertEqual(hot.raw, expected)
                self.assertEqual(menu.raw, expected_extra)
            else:
                self.assertNotEqual(status, 0)
                self.assertEqual((hot.raw, menu.raw), before)
            self.assertEqual(src.raw[:-1], bytes(p))

    def test_exact_install_reset_and_adjacent_canaries_both_environments(self):
        for flags in (0, 1):
            self.run_install(image(flags)[0], flags, True)

    def test_rejects_invalid_mapping_before_any_write(self):
        p, _, address = image()
        for kw in ({"pointer": "null"}, {"pointer": "unaligned"}, {"pointer": "source"},
                   {"pointer": "hot"}, {"cap": CAP - 32}, {"cap": CAP + 32},
                   {"vma": address + 32}):
            with self.subTest(kw=kw):
                self.run_install(p, 0, False, **kw)

    def test_rejects_malformed_descriptor_and_checksum_before_any_write(self):
        p, _, address = image()
        for offset, value in ((32, 5), (160, address + 32), (164, 0),
                              (168, CAP + 32), (172, 0), (180, 0), (188, 1), (44, 1)):
            bad = bytearray(p)
            struct.pack_into(">I", bad, offset, value)
            with self.subTest(offset=offset):
                self.run_install(seal(bad), 0, False)
        bad = bytearray(p)
        bad[-1] ^= 1
        self.run_install(bad, 0, False)

    def test_real_ppc_cross_span_branches_exact_and_reachable(self):
        for flags, extra in ((0, 0x91CF9000), (1, 0x713BA000)):
            functions, targets = fixture()
            original = deepcopy(functions)
            records = [dict(r) for f in original for r in f["relocations"]]
            rows = [dict(moved=True, analysis_address=a, address=b, linked_bytes=4)
                    for a, b in targets.items()]
            base = mt.stage(flags) + 0xC0
            with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
                folder = Path(tmp)
                cold.link_cold(folder, functions, base, "two", targets, shared_tails=True,
                    extension_base=extra, extension_names={"caller_a"}, extension_capacity=CAP)
                payload = (folder / "cold-two.bin").read_bytes()
                tail = (folder / "menu-code-two.bin").read_bytes()
                with patch.object(cold, "final_relocations", return_value=records):
                    pinned.verify_cold_branches(None, payload, base, rows, functions,
                        shared_tails=True, extension=(extra, tail))
                self.assertEqual(functions[0]["cold_address"], extra)

    def test_bootstrap_geometry_and_existing_mailbox(self):
        shim = build_bootstrap(0x804E5020, 0x81000000, mt.stage(1) + 0xC0, 32,
            0x80005700, (), (0x713BA000, 1024))
        self.assertLessEqual(len(shim), 1024)
        for menu in ((0x713BA020, 32), (0x713BA000, CAP + 32), (0x713BA000, 33)):
            with self.assertRaises(ValueError):
                build_bootstrap(0x804E5020, 0x81000000, mt.stage(1) + 0xC0, 32,
                    0x80005700, (), menu)
        asm = (ROOT / "launcher/kernel/asm/FakeEntryLoad.S").read_text()
        for value in ("0x91CF", "0x9000", "0x208"):
            self.assertIn(value, asm)
        boot = (ROOT / "include/susamune/mod_boot.h").read_text()
        self.assertNotIn("0x13003434", boot)
        self.assertNotIn("0x13003438", boot)


if __name__ == "__main__":
    unittest.main()
