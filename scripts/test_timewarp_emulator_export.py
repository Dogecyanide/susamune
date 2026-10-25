"""Execute the production bootstrap and apply an exported source-copy BPS."""
import copy
from io import BytesIO
import struct
from pathlib import Path
import tempfile
import unittest
import zlib

from test_bps_ui_language import apply_bps
import timewarp_emulator_export as export


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


class PPC:
    """Small instruction interpreter: unsupported opcodes fail, including calls."""
    def __init__(self, payload, address, stop):
        self.words = dict(zip(range(address, address + len(payload), 4), struct.unpack(f">{len(payload)//4}I", payload)))
        self.pc, self.stop = address, stop
        self.r = [(0xA0010100 + i * 0x101) & 0xFFFFFFFF for i in range(32)]
        self.r[1] = 0x80410000
        self.cr = 0xB6A59283
        self.spr = {1: 0x12345678, 8: 0x80003008, 9: 0x87654321}
        self.mem, self.cache, self.halted = {}, [], False

    def execute(self):
        for _ in range(1000000):
            if self.pc == self.stop:
                return
            w = self.words[self.pc]
            old, self.pc = self.pc, self.pc + 4
            op, d, a, b, xo = w >> 26, w >> 21 & 31, w >> 16 & 31, w >> 11 & 31, w >> 1 & 1023
            imm = signed(w & 0xFFFF, 16)
            if op in (14, 15):
                self.r[d] = ((self.r[a] if a else 0) + (imm << 16 if op == 15 else imm)) & 0xFFFFFFFF
            elif op == 24:
                self.r[a] = self.r[d] | (w & 0xFFFF)
            elif op in (32, 36, 37):
                address = ((self.r[a] if a else 0) + imm) & 0xFFFFFFFF
                if op == 32:
                    self.r[d] = self.mem[address]
                else:
                    self.mem[address] = self.r[d]
                    if op == 37:
                        self.r[a] = address
            elif op in (46, 47):
                address = self.r[a] + imm
                for reg in range(d, 32):
                    if op == 46:
                        self.r[reg] = self.mem[address]
                    else:
                        self.mem[address] = self.r[reg]
                    address += 4
            elif op == 18:
                if w & 3:
                    raise AssertionError("Bootstrap must use only relative, non-linking tail branches")
                self.pc = old + signed(w & 0x3FFFFFC, 26)
                if self.pc == old:
                    self.halted = True
                    return
            elif op == 16:
                bo, bi = d, a
                if bo == 16:
                    self.spr[9] = (self.spr[9] - 1) & 0xFFFFFFFF
                    take = self.spr[9] != 0
                elif bo in (4, 12):
                    take = bool(self.cr & (1 << (31 - bi))) == (bo == 12)
                else:
                    raise AssertionError(f"Unexpected BO {bo}")
                if take:
                    self.pc = old + signed(w & 0xFFFC, 16)
            elif op == 31:
                if xo in (339, 467):
                    spr = a | b << 5
                    if xo == 339:
                        self.r[d] = self.spr[spr]
                    else:
                        self.spr[spr] = self.r[d]
                elif xo == 19:
                    self.r[d] = self.cr
                elif xo == 144:
                    if w >> 12 & 255 != 255:
                        raise AssertionError("Partial condition-register restore")
                    self.cr = self.r[d]
                elif xo == 32:
                    compare = 8 if self.r[a] < self.r[b] else 4 if self.r[a] > self.r[b] else 2
                    self.cr = self.cr & 0x0FFFFFFF | compare << 28
                elif xo == 266:
                    self.r[d] = (self.r[a] + self.r[b]) & 0xFFFFFFFF
                elif xo in (86, 982):
                    self.cache.append(("dcbf" if xo == 86 else "icbi", (self.r[a] if a else 0) + self.r[b]))
                elif xo == 598:
                    self.cache.append(("sync", 0))
                else:
                    raise AssertionError(f"Unexpected extended opcode {xo}: {w:08X}")
            elif op == 19 and xo == 150:
                self.cache.append(("isync", 0))
            else:
                raise AssertionError(f"Unexpected instruction {w:08X}")
        raise AssertionError("Unbounded bootstrap")


class EmulatorExportTests(unittest.TestCase):
    base = 0x80420D60
    stub = base + export.BOOTSTRAP_OFFSET
    cold_base = 0x71E3F0A0
    hardware = 0x80003180

    def machine(self, fst=0x817FE000, size=0x1000):
        code = export.build_bootstrap(self.stub, export.STAGING, self.cold_base, 96,
                                     self.hardware, ((self.base, 0x50000), (self.base + 0x80000, 0x3F400)))
        ppc = PPC(code, self.stub, self.hardware)
        ppc.mem.update({0x80000038: fst, 0x8000003C: size})
        for i in range(24):
            ppc.mem[export.STAGING + i * 4] = i * 0x10203 + 17
            ppc.mem[self.cold_base + i * 4] = 0xDEADBEEF
        return ppc

    def test_boot_copies_clears_synchronizes_and_preserves_all_registers(self):
        ppc = self.machine()
        registers, cr, spr = list(ppc.r), ppc.cr, dict(ppc.spr)
        ppc.execute()
        self.assertFalse(ppc.halted)
        self.assertEqual(ppc.pc, self.hardware)
        self.assertEqual((ppc.r, ppc.cr, ppc.spr), (registers, cr, spr))
        for i in range(24):
            self.assertEqual(ppc.mem[export.STAGING + i * 4], 0)
            self.assertEqual(ppc.mem[self.cold_base + i * 4], i * 0x10203 + 17)
        expected = []
        for name, address in (("dcbf", self.cold_base), ("dcbf", export.STAGING), ("icbi", self.cold_base)):
            expected.extend((name, address + i * 32) for i in range(3))
            expected.append(("sync", 0))
        self.assertEqual(ppc.cache, [*expected, ("isync", 0)])

    def test_live_fst_collision_or_invalid_range_halts_before_copy(self):
        for address, size in ((export.STAGING, 32), (export.STAGING - 4, 8),
                              (self.stub, 32), (self.base + 16, 32),
                              (0, 0x100), (0x817FFFF0, 0x20), (0xFFFFFFF0, 0x30),
                              (0x817FE000, 0)):
            with self.subTest(address=hex(address)):
                ppc = self.machine(address, size)
                ppc.execute()
                self.assertTrue(ppc.halted)
                self.assertEqual(ppc.mem[export.STAGING], 17)
                self.assertEqual(ppc.mem[self.cold_base], 0xDEADBEEF)
                self.assertEqual(ppc.cache, [])

    def test_fst_adjacent_ranges_are_allowed(self):
        for address, size in ((export.STAGING - 32, 32), (export.STAGING + 96, 32)):
            ppc = self.machine(address, size)
            ppc.execute()
            self.assertFalse(ppc.halted)

    def fixture(self):
        retail = bytearray(0x1100)
        for table, value in ((0, 0x100), (0x48, 0x80003000), (0x90, 0x1000),
                             (0xD8, 0x80300000), (0xDC, 0x1000), (0xE0, 0x80003000)):
            struct.pack_into(">I", retail, table, value)
        symbols = {"__start": 0x80003000, "__init_registers": 0x80003100, "__init_hardware": self.hardware}
        struct.pack_into(">II", retail, 0x100,
                         export.branch(0x80003000, symbols["__init_registers"], True),
                         export.branch(0x80003004, self.hardware, True))
        retail[0x180:0x1A0] = b"RETAIL-CODE-ONLY-FROM-SOURCE-ISO!!"
        manifest = {"base_addr": self.base, "segments": [
            {"offset": 0, "memory_size": 64, "code": "A5" * 32},
            {"offset": 0x80000, "memory_size": 64, "code": "5A" * 32}],
            "cold_image": {"vma": self.cold_base}, "writes": [[0x80003200, 0x60000000]]}
        protected = {"timer": {"address": self.base, "size": 32, "sha256": export.digest(bytes.fromhex("A5" * 32))}}
        return bytes(retail), manifest, bytes(range(96)), symbols, protected

    def test_model_masters_boot_into_existing_cpu_heaps_with_canaries(self):
        spans = [(self.cold_base, 96), *export.dolphin_ghost_assets.copy_spans()]
        code = export.build_bootstrap(self.stub, export.STAGING, self.cold_base, 96,
                                      self.hardware, model_assets=True)
        ppc = PPC(code, self.stub, self.hardware)
        ppc.mem.update({0x80000038: 0x817FE000, 0x8000003C: 0x1000})
        staged = export.STAGING
        for address, size in spans:
            ppc.mem[address - 4] = ppc.mem[address + size] = 0xCAFE
            for i in range(0, size, 4):
                ppc.mem[staged + i] = address + i
            staged += size
        ppc.execute()
        self.assertFalse(ppc.halted)
        for address, size in spans:
            self.assertEqual(ppc.mem[address - 4], 0xCAFE)
            self.assertEqual(ppc.mem[address + size], 0xCAFE)
            for i in range(0, size, 4):
                self.assertEqual(ppc.mem[address + i], address + i)
        self.assertTrue(all(ppc.mem[a] == 0 for a in range(export.STAGING, staged, 4)))
        args = self.fixture()
        with self.assertRaises(ValueError):
            export.plan_dol(*args, model_assets=b"bad")

    def test_source_free_patch_round_trip_preserves_assets_and_fst(self):
        retail, manifest, cold, symbols, protected = self.fixture()
        changed, payloads, length, info = export.plan_dol(retail, manifest, cold, symbols, protected)
        source = bytearray(0x100000)
        source[0x2000:0x2000 + len(retail)] = retail
        source[0x8000:0x9000] = bytes(range(256)) * 16
        struct.pack_into(">III", source, 0x420, 0x2000, 0x8000, 0x1000)
        operations, target = export.build_operations(0x2000, len(retail), [(0, 0x1000),
                    (0x2000, len(retail)), (0x8000, 0x1000)], changed, payloads, length, len(source))
        patch, _ = export.encode_patch(BytesIO(source), operations, zlib.crc32(source), len(source))
        result = apply_bps(source, patch)
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[:0x420], source[:0x420])
        self.assertEqual(result[0x424:target], source[0x424:target])
        self.assertEqual(result[target + length:], source[target + length:])
        self.assertEqual(struct.unpack_from(">I", result, 0x420)[0], target)
        self.assertNotIn(b"RETAIL-CODE-ONLY-FROM-SOURCE-ISO!!", patch)
        actual = export.DolFile(BytesIO(result[target:target + length]))
        self.assertEqual(len(list(actual.sections)), 4)
        self.assertEqual(actual.entryPoint, symbols["__start"])
        self.assertEqual(result[target + 0x104:target + 0x108], struct.pack(">I", export.branch(0x80003004, self.stub, True)))
        self.assertEqual(info["bootstrap_bytes"], 420)
        self.assertTrue(any(op["kind"] == "source" for op in operations))

    def test_rejects_changed_boot_protected_bytes_or_full_upper_tail(self):
        retail, manifest, cold, symbols, protected = self.fixture()
        for kind in ("boot", "timer", "tail", "hook", "staging", "alignment"):
            r, m, p, c = bytearray(retail), copy.deepcopy(manifest), copy.deepcopy(protected), cold
            if kind == "boot":
                r[0x100:0x104] = b"\x60\0\0\0"
            elif kind == "timer":
                p["timer"]["sha256"] = "0" * 64
            elif kind == "tail":
                m["segments"][1]["memory_size"] = 0x3F004
            elif kind == "hook":
                m["writes"].append([0x80003004, 0])
            elif kind == "staging":
                struct.pack_into(">II", r, 0xD8, export.STAGING, 0x1000)
            else:
                c = c[:-1]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                export.plan_dol(bytes(r), m, c, symbols, p)

    def test_occupied_gaps_and_operation_bounds_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "disc gap"):
            export.build_operations(0x2000, 0x100, [(0, 0xFF80)], {}, [(0x100, bytes(32))], 0x120, 0x10000)
        with self.assertRaisesRegex(ValueError, "DOL edit"):
            export.build_operations(0x2000, 0x100, [(0, 0x4000)], {0xFE: bytes(4)}, [], 0x100, 0x10000)

    def test_prefers_verified_interior_gap_but_never_overwrites_occupied_bytes(self):
        preferred = export.PREFERRED_DISC_OFFSET
        extents = [(0, 0x1000), (preferred + 0x1000, 0x2000)]
        self.assertEqual(export.unused_disc_span(extents, 0x1000, preferred + 0x3000),
                         (preferred, preferred + 0x1000))
        occupied = [(0, preferred + 0x1000), (preferred + 0x1100, 0x1F00)]
        with self.assertRaisesRegex(ValueError, "disc gap"):
            export.unused_disc_span(occupied, 0x1000, preferred + 0x3000)
        with self.assertRaisesRegex(ValueError, "extent"):
            export.unused_disc_span([(0, preferred + 0x3001)], 0x1000, preferred + 0x3000)

    def test_stale_or_incomplete_object_provenance_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            objects = build / "CMakeFiles/susamune_obj_pal.dir/src"
            objects.mkdir(parents=True)
            obj = objects / "example.cpp.obj"
            obj.write_bytes(b"compiled-current-source")
            partial = build / "susamune_pre_pal.o"
            partial.write_bytes(b"current-partial")
            proof = {"complete": True, "partial_rebuilt_from_current_objects": True,
                     "source_object_sha256": {"example.cpp": export.digest(obj.read_bytes())},
                     "source_partial_sha256": export.digest(partial.read_bytes())}
            export.verify_current_inputs(proof, build, "pal")
            obj.write_bytes(b"newer-compiled-source")
            with self.assertRaisesRegex(ValueError, "source objects"):
                export.verify_current_inputs(proof, build, "pal")
            obj.write_bytes(b"compiled-current-source")
            partial.write_bytes(b"newer-partial")
            with self.assertRaisesRegex(ValueError, "partial object"):
                export.verify_current_inputs(proof, build, "pal")
            with self.assertRaisesRegex(ValueError, "provenance"):
                export.verify_current_inputs(dict(proof, complete=False), build, "pal")


if __name__ == "__main__":
    unittest.main()
