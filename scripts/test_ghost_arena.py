"""Host tests for production shared-arena leases; no game memory is mapped."""
import ctypes as C
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
#include "susamune/ghost_arena.hxx"
#include <cstring>
using namespace GhostArena;
static Arena arena;
alignas(32) static unsigned char memory[131136];
#define API extern "C" __declspec(dllexport)
API int reset() {
    arena={};memset(memory,0xa5,sizeof(memory));
    const Span banks[]={{memory+32,65536},{memory+65568,65536}};
    return configure(arena,banks,2);
}
API unsigned long long take(unsigned owner,unsigned bytes) {
    Handle h=acquire(arena,static_cast<Owner>(owner),bytes);
    return (static_cast<unsigned long long>(h.serial)<<32)|h.slot;
}
static Handle handle(unsigned long long h){return {unsigned(h),unsigned(h>>32)};}
API unsigned offset(unsigned long long h,unsigned owner) {
    const Entry *e=find(arena,handle(h),static_cast<Owner>(owner));
    return e?unsigned(static_cast<unsigned char*>(e->span.data)-memory):~0u;
}
API unsigned size(unsigned long long h,unsigned owner) {
    const Entry *e=find(arena,handle(h),static_cast<Owner>(owner));return e?e->span.bytes:0;
}
API int drop(unsigned long long h,unsigned owner){return release(arena,handle(h),static_cast<Owner>(owner));}
API int readable(unsigned long long h,unsigned owner){return read(arena,handle(h),static_cast<Owner>(owner)).data!=nullptr;}
API int writable(unsigned long long h,unsigned owner){return write(arena,handle(h),static_cast<Owner>(owner)).data!=nullptr;}
API int pin_io(unsigned long long h,unsigned owner,unsigned seq,unsigned dir){return pin(arena,handle(h),static_cast<Owner>(owner),seq,static_cast<Transfer>(dir));}
API int done(unsigned long long h,unsigned owner,unsigned seq){return complete(arena,handle(h),static_cast<Owner>(owner),seq);}
API unsigned free_bytes(){return available(arena);}
API unsigned largest_bytes(){return largest(arena);}
API int reconfigure(){return configure(arena,arena.bank,arena.banks);}
API void exhaust(){arena.serial=~0u;}
API unsigned control_bytes(){return sizeof(Arena);}
API int malformed(unsigned kind) {
    Arena a={};Span banks[]={{memory+32,65536},{memory+65568,65536}};unsigned n=2;
    switch(kind) {
    case 0:banks[0].data=nullptr;break;
    case 1:banks[0].data=memory+33;break;
    case 2:banks[0].bytes=65535;break;
    case 3:banks[0].bytes=0;break;
    case 4:banks[1]=banks[0];break;
    case 5:banks[0].data=reinterpret_cast<void*>(Address(-32));banks[0].bytes=64;break;
    case 6:return configure(a,nullptr,2);
    case 7:n=0;break;
    case 8:n=9;break;
    case 9:banks[0].data=reinterpret_cast<void*>(reinterpret_cast<Address>(&a)&~Address(31));banks[0].bytes=65536;break;
    }
    return configure(a,banks,n);
}
API int guards() {
    for(unsigned i=0;i<32;++i)if(memory[i]!=0xa5||memory[131104+i]!=0xa5)return 0;
    return 1;
}
'''


class ArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-arena-')
        cls.addClassCleanup(cls.temp.cleanup)
        out = Path(cls.temp.name)
        (out / 'fixture.cpp').write_text(FIXTURE, encoding='utf-8')
        env = dict(os.environ, PATH='C:/msys64/mingw64/bin;' + os.environ['PATH'])
        subprocess.run(['C:/msys64/mingw64/bin/g++.exe', '-std=c++11', '-O2',
                        '-Wall', '-Wextra', '-Werror', '-shared', '-static',
                        '-I', str(ROOT / 'include'), str(out / 'fixture.cpp'), str(ROOT / 'src/ghost_arena.cpp'),
                        '-o', str(out / 'arena.dll')], env=env, check=True,
                       capture_output=True, text=True, encoding='utf-8')
        cls.lib = C.CDLL(str(out / 'arena.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.take.restype = C.c_uint64
        cls.lib.take.argtypes = [C.c_uint, C.c_uint]
        for name in ('offset', 'size', 'drop', 'readable', 'writable'):
            getattr(cls.lib, name).argtypes = [C.c_uint64, C.c_uint]
        cls.lib.offset.restype = C.c_uint
        cls.lib.pin_io.argtypes = [C.c_uint64, C.c_uint, C.c_uint, C.c_uint]
        cls.lib.done.argtypes = [C.c_uint64, C.c_uint, C.c_uint]

    def setUp(self):
        self.assertEqual(self.lib.reset(), 1)

    def tearDown(self):
        self.assertEqual(self.lib.guards(), 1)

    def test_bad_spans_fail_without_writes(self):
        for case in range(10):
            with self.subTest(case=case):
                self.assertEqual(self.lib.malformed(case), 0)
        self.assertEqual(self.lib.free_bytes(), 131072)

    def test_rounding_and_mixed_owners(self):
        handles = [(self.lib.take(owner, size), owner) for owner, size in ((1, 1), (2, 33), (3, 1000), (4, 64))]
        self.assertEqual([self.lib.size(h, o) for h, o in handles], [32, 64, 1024, 64])
        spans = [(self.lib.offset(h, o), self.lib.size(h, o)) for h, o in handles]
        for i, (p, n) in enumerate(spans):
            self.assertEqual(p % 32, 0)
            for q, m in spans[:i]:
                self.assertFalse(p < q + m and q < p + n)
        self.assertEqual(self.lib.free_bytes(), 131072 - 1184)

    def test_invalid_requests_and_owner(self):
        for owner, size in ((0, 32), (5, 32), (1, 0), (1, 0xffffffff), (1, 131072)):
            self.assertEqual(self.lib.take(owner, size), 24)
        handle = self.lib.take(1, 32)
        for owner in (0, 2, 3, 4, 5):
            self.assertEqual(self.lib.size(handle, owner), 0)
            self.assertEqual(self.lib.drop(handle, owner), 0)
            self.assertEqual(self.lib.pin_io(handle, owner, 1, 1), 0)

    def test_transfer_read_blocks_writes_and_release(self):
        h = self.lib.take(1, 64)
        self.assertEqual(self.lib.pin_io(h, 1, 1, 1), 1)
        self.assertEqual(self.lib.readable(h, 1), 1)
        self.assertEqual(self.lib.writable(h, 1), 0)
        self.assertEqual(self.lib.drop(h, 1), 0)
        self.assertEqual(self.lib.reconfigure(), 0)
        self.assertEqual(self.lib.done(h, 1, 2), 0)
        self.assertEqual(self.lib.done(h, 1, 1), 1)
        self.assertEqual(self.lib.writable(h, 1), 1)
        self.assertEqual(self.lib.drop(h, 1), 1)

    def test_transfer_write_blocks_all_access(self):
        h = self.lib.take(3, 64)
        self.assertEqual(self.lib.pin_io(h, 3, 8, 2), 1)
        self.assertEqual(self.lib.readable(h, 3), 0)
        self.assertEqual(self.lib.writable(h, 3), 0)
        self.assertEqual(self.lib.pin_io(h, 3, 9, 1), 0)
        self.assertEqual(self.lib.done(h, 3, 8), 1)
        for seq, direction in ((0, 1), (8, 1), (7, 2), (9, 0), (9, 3)):
            self.assertEqual(self.lib.pin_io(h, 3, seq, direction), 0)
        self.assertEqual(self.lib.pin_io(h, 3, 9, 1), 1)

    def test_stale_handle_and_completion_cannot_touch_new_lease(self):
        first = self.lib.take(1, 32)
        self.assertEqual(self.lib.pin_io(first, 1, 1, 1), 1)
        self.assertEqual(self.lib.done(first, 1, 1), 1)
        self.assertEqual(self.lib.drop(first, 1), 1)
        second = self.lib.take(1, 32)
        self.assertNotEqual(first, second)
        self.assertEqual(self.lib.pin_io(second, 1, 1, 2), 1)
        self.assertEqual(self.lib.done(first, 1, 1), 0)
        self.assertEqual(self.lib.drop(first, 1), 0)
        self.assertEqual(self.lib.writable(second, 1), 0)

    def test_reconfiguration_preserves_generation(self):
        first = self.lib.take(3, 32)
        self.assertEqual(self.lib.reconfigure(), 0)
        self.assertEqual(self.lib.drop(first, 3), 1)
        self.assertEqual(self.lib.reconfigure(), 1)
        second = self.lib.take(3, 32)
        self.assertNotEqual(first, second)
        self.assertEqual(self.lib.drop(first, 3), 0)

    def test_generation_exhaustion_fails_closed(self):
        self.lib.exhaust()
        last = self.lib.take(1, 32)
        self.assertEqual(last >> 32, 0xffffffff)
        self.assertEqual(self.lib.take(2, 32), 24)
        self.assertEqual(self.lib.drop(last, 1), 1)
        self.assertEqual(self.lib.reconfigure(), 0)

    def test_fragmentation_best_fit_and_largest(self):
        a, b, c = (self.lib.take(1, n) for n in (1024, 2048, 4096))
        self.assertEqual(self.lib.largest_bytes(), 65536)
        self.assertEqual(self.lib.drop(b, 1), 1)
        d = self.lib.take(3, 2000)
        self.assertEqual(self.lib.offset(d, 3), 32 + 1024)
        big = self.lib.take(2, 65536)
        self.assertNotEqual(big, 24)
        self.assertEqual(self.lib.largest_bytes(), 65536 - 7168)
        self.assertEqual(self.lib.take(4, 65536), 24)
        self.assertEqual(self.lib.drop(a, 1), 1)
        self.assertEqual(self.lib.drop(c, 1), 1)

    def test_lease_limit_is_independent_of_free_capacity(self):
        handles = [self.lib.take(1, 32) for _ in range(24)]
        self.assertNotIn(24, handles)
        self.assertEqual(self.lib.take(2, 32), 24)
        self.assertEqual(self.lib.drop(handles[5], 1), 1)
        self.assertNotEqual(self.lib.take(3, 32), 24)

    def test_randomized_nonoverlap_accounting(self):
        rng = random.Random(23012026)
        leases = []
        for _ in range(6000):
            if leases and rng.randrange(3) == 0:
                h, owner = leases.pop(rng.randrange(len(leases)))
                self.assertEqual(self.lib.drop(h, owner), 1)
            else:
                owner = rng.randrange(1, 5)
                h = self.lib.take(owner, rng.randrange(1, 40000))
                if h != 24:
                    leases.append((h, owner))
            spans = [(self.lib.offset(h, o), self.lib.size(h, o)) for h, o in leases]
            self.assertEqual(self.lib.free_bytes(), 131072 - sum(n for _, n in spans))
            for i, (p, n) in enumerate(spans):
                self.assertTrue(32 <= p and p + n <= 131104)
                self.assertFalse(p < 65568 < p + n)
                for q, m in spans[:i]:
                    self.assertFalse(p < q + m and q < p + n)


if __name__ == '__main__':
    unittest.main()
