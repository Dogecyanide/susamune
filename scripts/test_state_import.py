"""Borrowed SD windows into the production transactional store and codec."""
import ctypes as C
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
import zlib

import test_state_store as storetest
from mod_transport import encode_quick
from test_state_codec import Guarded
from test_timewarp_staged_transaction import StageHarness, Token

ROOT = Path(__file__).resolve().parents[1]
MORE, COMPLETE, INVALID, FULL = range(4)


class Cursor(C.Structure):
    _fields_ = [('transaction', Token), ('total', C.c_uint), ('offset', C.c_uint), ('kind', C.c_uint)]


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='timewarp-state-import-')
        folder = Path(cls.temp.name)
        cls.harness = StageHarness(folder)
        original = storetest.EXTRA
        storetest.EXTRA += '#include "' + (ROOT / 'src/state_import.cpp').as_posix() + '"\n' + r'''
extern "C" {
__declspec(dllexport) int ib(StateStore::Store*s,StateImport::Cursor*c,unsigned n){return StateImport::begin(*s,*c,n);}
__declspec(dllexport) int ia(StateStore::Store*s,StateImport::Cursor*c,const void*p,unsigned n){return StateImport::append(*s,*c,p,n);}
}
'''
        try:
            cls.codec = storetest.StoreCodec(folder)
        finally:
            storetest.EXTRA = original
        cls.codec.lib.ib.argtypes = [C.c_void_p, C.POINTER(Cursor), C.c_uint]
        cls.codec.lib.ia.argtypes = [C.c_void_p, C.POINTER(Cursor), C.c_void_p, C.c_uint]
        cls.addClassCleanup(cls.temp.cleanup)
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.codec.lib._handle)))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.harness.lib._handle)))
        command = [str(ROOT / 'toolchain/clang++.exe'), '--target=powerpc-gecko-ibm-kuribo-eabi',
                   '-std=c++17', '-Oz', '-ffreestanding', '-fno-builtin', '-fno-exceptions',
                   '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'include'),
                   '-c', str(ROOT / 'src/state_import.cpp'), '-o', str(folder / 'import.o')]
        compiled = subprocess.run(command, capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError(compiled.stdout + compiled.stderr)

    def seeded(self, sizes=None, staging=0x2f0000):
        store = storetest.StorePool(self.harness, self.codec, sizes, staging)
        for slot in range(3):
            raw = random.Random(slot + 89).randbytes(0x5000)
            packed = zlib.compress(raw) if slot == 1 else encode_quick(raw)
            self.assertTrue(store.put(slot, raw, packed, 501 + slot, int(slot == 1)))
        return store

    def begin(self, store, packed):
        self.assertTrue(store.begin(1))
        cursor = Cursor()
        self.assertTrue(store.call('ib', C.byref(cursor), len(packed)))
        return cursor

    def append(self, store, cursor, data):
        borrowed = Guarded(len(data))
        C.memmove(borrowed.ptr, data, len(data))
        result = store.call('ia', C.byref(cursor), borrowed.ptr, len(data))
        self.assertTrue(borrowed.guards())
        C.memset(borrowed.ptr, 0xa7, len(data))
        return result

    def finish(self, store, cursor, raw, packed, kind):
        self.assertEqual(cursor.offset, len(packed))
        self.assertEqual(cursor.kind, kind)
        info = storetest.identity(raw, packed, 9842, kind)
        self.assertEqual(store.call('sch'), info.checksum)
        self.assertTrue(store.seal(info))
        store.commit(1, raw, packed, info)
        for slot in range(3):
            store.decode(slot, protected=True)
        store.guards()

    def test_quick_windows_reread_partial_blocks_without_retaining_borrowed_bytes(self):
        for capacity in (0x20008, 0x20010, 0x30000, 0x4e000):
            with self.subTest(capacity=capacity):
                store = self.seeded()
                raw = random.Random(811).randbytes(0xa0011)
                packed = encode_quick(raw)
                cursor = self.begin(store, packed)
                reread = False
                while cursor.offset < len(packed):
                    before = cursor.offset
                    data = packed[before:before + capacity]
                    result = self.append(store, cursor, data)
                    self.assertIn(result, (MORE, COMPLETE))
                    self.assertGreater(cursor.offset, before)
                    reread |= cursor.offset - before < len(data)
                self.assertTrue(reread)
                self.finish(store, cursor, raw, packed, 0)

    def test_old_deflate_is_preserved_across_bounded_windows(self):
        store = self.seeded()
        raw = random.Random(197).randbytes(0xc0217)
        packed = zlib.compress(raw)
        cursor = self.begin(store, packed)
        while cursor.offset < len(packed):
            self.assertIn(self.append(store, cursor, packed[cursor.offset:cursor.offset + 0x4e000]),
                          (MORE, COMPLETE))
        self.finish(store, cursor, raw, packed, 1)

    def test_abort_after_each_window_preserves_all_old_roots(self):
        for kind in (0, 1):
            raw = random.Random(882).randbytes(0xa0031)
            packed = encode_quick(raw) if kind == 0 else zlib.compress(raw)
            for stop in range(4):
                store = self.seeded()
                cursor = self.begin(store, packed)
                for _ in range(stop):
                    if cursor.offset == len(packed):
                        break
                    self.assertIn(self.append(store, cursor, packed[cursor.offset:cursor.offset + 0x4e000]),
                                  (MORE, COMPLETE))
                self.assertTrue(store.call('sa'))
                for slot in range(3):
                    store.decode(slot)
                store.guards()

    def test_stale_transaction_and_live_memory_aliases_refuse_before_append(self):
        store = self.seeded()
        packed = encode_quick(b'new state' * 40000)
        cursor = self.begin(store, packed)
        self.assertTrue(store.call('sa'))
        self.assertTrue(store.begin(1))
        before = bytes(store.pool.memory)
        self.assertEqual(self.append(store, cursor, packed), INVALID)
        self.assertEqual(bytes(store.pool.memory), before)
        cursor = Cursor()
        self.assertTrue(store.call('ib', C.byref(cursor), len(packed)))
        for address in (store.pool.memory.banks[0], store.pool.stage_memory.staging,
                        store.storage.ptr, C.addressof(cursor)):
            self.assertEqual(store.call('ia', C.byref(cursor), address, min(16, len(packed))), INVALID)
        self.assertEqual(cursor.offset, 0)
        self.assertTrue(store.call('sa'))
        for slot in range(3):
            store.decode(slot)

    def test_malformed_or_truncated_stream_cannot_commit(self):
        quick = encode_quick(random.Random(844).randbytes(0x30001))
        cases = [quick[:4] + bytes(4) + quick[8:], quick[:-1], quick + b'x',
                 quick[:12] + struct.pack('>I', 0x80020001) + quick[16:],
                 quick[:8] + struct.pack('>I', 1) + quick[12:], b'not zlib' * 100,
                 zlib.compress(b'hello')[:-1]]
        for packed in cases:
            with self.subTest(prefix=packed[:16], size=len(packed)):
                store = self.seeded()
                cursor = self.begin(store, packed)
                result = self.append(store, cursor, packed)
                if result == COMPLETE:
                    info = storetest.identity(b'hello', packed, 733, cursor.kind)
                    self.assertFalse(store.seal(info))
                else:
                    self.assertIn(result, (INVALID, FULL))
                self.assertTrue(store.call('sa'))
                for slot in range(3):
                    store.decode(slot)

    def test_cursor_alias_and_changed_offset_cannot_modify_live_control(self):
        store = self.seeded()
        packed = encode_quick(random.Random(853).randbytes(0x60001))
        cursor = self.begin(store, packed)
        for address in (store.storage.ptr, C.addressof(store.pool.stage_memory),
                        C.addressof(store.pool.memory), store.table.ptr):
            self.assertFalse(store.call('ib', C.cast(address, C.POINTER(Cursor)), len(packed)))
        self.assertEqual(self.append(store, cursor, packed[:0x4e000]), MORE)
        offset = cursor.offset
        cursor.offset += 32
        self.assertEqual(self.append(store, cursor, packed[offset:]), INVALID)
        cursor.offset = offset
        self.assertIn(self.append(store, cursor, packed[offset:]), (MORE, COMPLETE))
        self.assertTrue(store.call('sa'))
        for slot in range(3):
            store.decode(slot)

    def test_capacity_failure_is_abortable_and_does_not_evict_old_roots(self):
        store = self.seeded([0x30000, 0x20000, 0x10000, 0x10000], staging=0x20000)
        raw = random.Random(323).randbytes(0xc0000)
        packed = encode_quick(raw)
        cursor = self.begin(store, packed)
        result = MORE
        while result == MORE:
            result = self.append(store, cursor, packed[cursor.offset:cursor.offset + 0x4e000])
        self.assertEqual(result, FULL)
        self.assertTrue(store.call('sa'))
        for slot in range(3):
            store.decode(slot)
        store.guards()


if __name__ == '__main__':
    unittest.main()
