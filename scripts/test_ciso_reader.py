"""Exercise the actual bounded CISO mapping code with sparse image fixtures."""
import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BLOCK = 0x200000
HEADER = 0x8000


class CisoReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clang = ROOT / "toolchain/clang.exe"
        if sys.platform != "win32" or not clang.exists():
            raise unittest.SkipTest("Bundled Windows compiler required for native C fixture")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-ciso-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = work / "test.c"
        source.write_text('''#include "susamune/ciso_reader.h"
#include "susamune/crash_report.h"
__declspec(dllexport) int init(unsigned short *m, const unsigned char *h,
    unsigned int n, unsigned long long s) { return SusamuneCisoMapInit(m,h,n,s); }
__declspec(dllexport) unsigned int span(const unsigned short *m,
    unsigned long long o, unsigned int n, unsigned long long s,
    unsigned long long *p, int *e) { return SusamuneCisoSpan(m,o,n,s,p,e); }
''', encoding="ascii")
        library = work / "ciso.dll"
        subprocess.run([str(clang), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, capture_output=True, text=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(
            ctypes.c_void_p(cls.dll._handle)))
        cls.dll.init.argtypes = [ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint, ctypes.c_ulonglong]
        cls.dll.init.restype = ctypes.c_int
        cls.dll.span.argtypes = [ctypes.POINTER(ctypes.c_ushort), ctypes.c_ulonglong,
            ctypes.c_uint, ctypes.c_ulonglong, ctypes.POINTER(ctypes.c_ulonglong),
            ctypes.POINTER(ctypes.c_int)]
        cls.dll.span.restype = ctypes.c_uint

    def initialize(self, used=(0, 2), file_size=None, corrupt=None):
        header = bytearray(1032)
        header[:8] = b"CISO\x00\x00\x20\x00"
        for index in used:
            header[8 + index] = 1
        if corrupt:
            header[corrupt[0]] = corrupt[1]
        mapping = (ctypes.c_ushort * 1024)()
        source = (ctypes.c_ubyte * len(header)).from_buffer_copy(header)
        size = file_size if file_size is not None else HEADER + len(used) * BLOCK
        return self.dll.init(mapping, source, len(header), size), mapping, size

    def span(self, mapping, offset, length, size):
        physical, empty = ctypes.c_ulonglong(), ctypes.c_int()
        amount = self.dll.span(mapping, offset, length, size,
                               ctypes.byref(physical), ctypes.byref(empty))
        return amount, physical.value, empty.value

    def test_sparse_translation_crosses_present_empty_present_blocks(self):
        valid, mapping, size = self.initialize()
        self.assertEqual(valid, 1)
        self.assertEqual(self.span(mapping, BLOCK - 4, 12, size),
                         (4, HEADER + BLOCK - 4, 0))
        self.assertEqual(self.span(mapping, BLOCK, BLOCK + 8, size), (BLOCK, 0, 1))
        self.assertEqual(self.span(mapping, 2 * BLOCK, 8, size), (8, HEADER + BLOCK, 0))

    def test_truncated_payload_and_invalid_map_rejected(self):
        self.assertEqual(self.initialize(file_size=HEADER + 2 * BLOCK - 1)[0], 0)
        self.assertEqual(self.initialize(corrupt=(9, 2))[0], 0)
        self.assertEqual(self.initialize(corrupt=(6, 0x10))[0], 0)
        self.assertEqual(self.initialize(used=())[0], 0)

    def test_logical_end_and_damaged_physical_map_are_bounded(self):
        _, mapping, size = self.initialize()
        self.assertEqual(self.span(mapping, 1024 * BLOCK, 1, size)[0], 0)
        self.assertEqual(self.span(mapping, 0xFFFFFFFFFFFFFFFF, 1, size)[0], 0)
        mapping[0] = 1023
        self.assertEqual(self.span(mapping, 0, 1, size)[0], 0)


if __name__ == "__main__":
    unittest.main()
