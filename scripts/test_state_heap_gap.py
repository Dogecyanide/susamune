"""Focused admission tests for the optional solid-heap canonicalization."""
import ctypes as C
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
Read = C.CFUNCTYPE(C.c_void_p, C.c_uint, C.c_uint, C.c_void_p)


class GapAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='timewarp-gap-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = folder / 'gap.cpp'
        source.write_text('#include "susamune/state_heap_gap.hxx"\n'
            'extern "C" __declspec(dllexport) void inspect(unsigned a,unsigned n,unsigned v,unsigned o,'
            'StateHeapGap::ReadHeader r,unsigned *out) {'
            'StateCodec::ZeroRange z=StateHeapGap::inspect(a,n,v,o,r,0);out[0]=z.offset;out[1]=z.size;}\n')
        dll = folder / 'gap.dll'
        subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2', '-fno-builtin',
            '-mno-stack-arg-probe', '-I', str(ROOT / 'include'), str(source), '-o', str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.inspect.argtypes = [C.c_uint] * 4 + [Read, C.POINTER(C.c_uint)]

    def synthetic(self):
        base, size, vtable = 0x81000000, 0x10000, 0x803d7a28
        words = [0] * 30
        words[0] = vtable
        for at, value in {0x30: base + 0x80, 0x34: base + size, 0x38: size - 0x80,
                          0x68: 0x8000, 0x6c: base + 0x3000, 0x70: base + 0xb000}.items():
            words[at // 4] = value
        return base, size, vtable, words

    def inspect(self, base, size, vtable, words, offset=91, child=None):
        sources = {base: (C.c_uint * len(words))(*words)}
        if child:
            address, values = child
            sources[address] = (C.c_uint * len(values))(*values)
        requests = []
        @Read
        def read(address, count, _):
            requests.append((address, count))
            data = sources.get(address)
            return C.addressof(data) if data is not None and count <= C.sizeof(data) else None
        out = (C.c_uint * 2)()
        self.lib.inspect(base, size, vtable, offset, read, out)
        return tuple(out), requests

    def test_exact_free_interval_and_zero_sized_gap(self):
        base, size, table, words = self.synthetic()
        result, _ = self.inspect(base, size, table, words)
        self.assertEqual(result, (91 + 0x3000, 0x8000))
        words[0x70 // 4] = words[0x6c // 4]
        words[0x68 // 4] = 0
        self.assertEqual(self.inspect(base, size, table, words)[0], (0, 0))

    def test_busy_inconsistent_and_unknown_headers_retain_all_bytes(self):
        base, size, table, good = self.synthetic()
        changes = {0: table + 4, 0x18: 1, 0x1c: 1, 0x20: 1, 0x24: 1,
                   0x30: base, 0x34: base + size - 1, 0x38: size, 0x68: 1,
                   0x6c: base + size, 0x70: base + size + 1, 0x74: base + 0x100,
                   0x44: 65, 0x3c: base + 0x100, 0x40: base + 0x100}
        for at, value in changes.items():
            with self.subTest(field=hex(at)):
                words = good.copy()
                words[at // 4] = value
                self.assertEqual(self.inspect(base, size, table, words)[0], (0, 0))
        for address, length, offset in ((base + 1, size, 91), (0x81800000, size, 91),
            (base, 0x77, 91), (base, 0xffffffff, 91), (base, size, 0xffffffff - size + 1)):
            result, reads = self.inspect(address, length, table, good, offset)
            self.assertEqual(result, (0, 0))
            self.assertEqual(reads, [])

    def test_child_heap_overlap_and_list_integrity(self):
        base, size, table, words = self.synthetic()
        child = base + 0x1000
        values = [0] * 26
        for at, value in {0x30: child + 0x80, 0x34: child + 0x400, 0x38: 0x380,
                          0x48: child, 0x4c: base + 0x3c}.items():
            values[at // 4] = value
        words[0x3c // 4] = words[0x40 // 4] = child + 0x48
        words[0x44 // 4] = 1
        self.assertEqual(self.inspect(base, size, table, words, child=(child, values))[0],
                         (91 + 0x3000, 0x8000))
        for at, value in ((0x48, child + 4), (0x4c, 0), (0x50, child + 0x48),
                          (0x54, child + 0x48), (0x34, base + size + 1)):
            bad = values.copy()
            bad[at // 4] = value
            self.assertEqual(self.inspect(base, size, table, words, child=(child, bad))[0], (0, 0))
        values[0x30 // 4], values[0x34 // 4] = base + 0x3000, base + 0x4000
        values[0x38 // 4] = 0x1000
        self.assertEqual(self.inspect(base, size, table, words, child=(child, values))[0], (0, 0))

    def test_available_captured_heap_trees_admit_the_measured_gap(self):
        path = ROOT / 'build/timewarp-heap-gap-measure/receipt.json'
        if not path.is_file():
            self.skipTest('Private captures unavailable; synthetic boundaries remain covered')
        rows = [group['slots'][0] for group in json.loads(path.read_text())['sets']]
        for row in rows:
            raw_path = Path(row['raw_path'])
            raw, metadata = raw_path.read_bytes(), raw_path.with_suffix('.metadata').read_bytes()
            base, size = struct.unpack_from('>2I', metadata, 12)
            count = struct.unpack_from('>I', metadata, 24)[0]
            spans = [struct.unpack_from('>3I', metadata, 40 + i * 12) for i in range(count)]
            _, _, start = next(s for s in spans if s[0] == base)
            table = struct.unpack_from('>I', raw, start)[0]
            keep = []
            @Read
            def read(address, count, _):
                for at, length, offset in spans:
                    if at <= address and address + count <= at + length:
                        values = struct.unpack_from('>' + 'I' * (count // 4), raw, offset + address - at)
                        data = (C.c_uint * len(values))(*values)
                        keep.append(data)
                        return C.addressof(data)
                return None
            out = (C.c_uint * 2)()
            self.lib.inspect(base, size, table, start, read, out)
            self.assertEqual(tuple(out), (row['raw_offset'], row['free_bytes']), row['name'])


if __name__ == '__main__':
    unittest.main()
