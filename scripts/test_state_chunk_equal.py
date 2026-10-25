"""Check the production chunk comparison across alignment and exact tails."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ChunkEqualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-chunk-equal-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source, library = folder / 'equal.c', folder / 'equal.dll'
        source.write_text('''#include "susamune/state_chunk_pool.h"
__declspec(dllexport) int equal(const unsigned char*a,const unsigned char*b,unsigned n){
 return TWChunkEqual(a,b,n);
}
__declspec(dllexport) unsigned hash(const unsigned char*p,unsigned n){return TWChunkHash(p,n);}
''')
        subprocess.run([str(ROOT / 'toolchain/clang.exe'), '--target=x86_64-pc-windows-msvc',
                        '-shared', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Wl,/noentry',
                        '-O2', '-I', str(ROOT / 'include'), str(source), '-o', str(library)],
                       check=True, capture_output=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.equal.argtypes = [C.c_void_p, C.c_void_p, C.c_uint]
        cls.lib.hash.argtypes = [C.c_void_p, C.c_uint]
        cls.lib.hash.restype = C.c_uint

    def test_hash_matches_scalar_reference_with_partial_words(self):
        for alignment in range(4):
            for size in (*range(34), 255, 256, 257, 131079):
                raw = bytes((i * 29 + 17) & 255 for i in range(size))
                owner = C.create_string_buffer(b'\xff' * alignment + raw + b'\xa7' * 4)
                expected = 2166136261
                for byte in raw:
                    expected = ((expected ^ byte) * 16777619) & 0xffffffff
                self.assertEqual(self.lib.hash(C.addressof(owner) + alignment, size), expected)

    def test_all_alignment_pairs_and_short_tails(self):
        for first in range(4):
            for second in range(4):
                for size in range(34):
                    with self.subTest(first=first, second=second, size=size):
                        a, b = (C.c_ubyte * 40)(), (C.c_ubyte * 40)()
                        for index in range(size):
                            a[first + index] = b[second + index] = (index * 29 + 17) & 255
                        # Distinct sentinel bytes immediately after each range.
                        a[first + size], b[second + size] = 17, 93
                        pa, pb = C.byref(a, first), C.byref(b, second)
                        self.assertEqual(self.lib.equal(pa, pb, size), 1)
                        for index in {0, size // 2, size - 1} if size else ():
                            b[second + index] ^= 1
                            self.assertEqual(self.lib.equal(pa, pb, size), 0)
                            b[second + index] ^= 1


if __name__ == '__main__':
    unittest.main()
