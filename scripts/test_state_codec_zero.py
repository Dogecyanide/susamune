"""Focused encoded-only zero interval checks against the production codec."""
import ctypes as C
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
import zlib

from test_state_codec import Guarded, Span, Result, ROOT, QUICK_BLOCK, reference_quick_frame


class ZeroRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='state-codec-zero-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        shim = folder / 'codec.cpp'
        shim.write_text('#include "' + (ROOT / 'src/state_codec.cpp').as_posix() + '"\n' + r'''
extern "C" {
void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){unsigned char*o=(unsigned char*)d;
 const unsigned char*i=(const unsigned char*)s;while(n--)*o++=*i++;return d;}
void *memset(void*d,int b,__SIZE_TYPE__ n){unsigned char*o=(unsigned char*)d;
 while(n--)*o++=(unsigned char)b;return d;}
void *memmove(void*d,const void*s,__SIZE_TYPE__ n){unsigned char*o=(unsigned char*)d;
 const unsigned char*i=(const unsigned char*)s;if(o<i){for(__SIZE_TYPE__ j=0;j<n;++j)o[j]=i[j];}
 else{while(n){--n;o[n]=i[n];}}return d;}
int memcmp(const void*a,const void*b,__SIZE_TYPE__ n){const unsigned char*x=(const unsigned char*)a;
 const unsigned char*y=(const unsigned char*)b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;}
__declspec(dllexport) unsigned workspace(){return StateCodec::workspaceSize();}
__declspec(dllexport) void pack(void*w,unsigned ws,const StateCodec::ReadSpan*s,unsigned n,
 const StateCodec::WriteSpan*d,unsigned dn,unsigned mode,unsigned offset,unsigned size,StateCodec::Result*r){
 *r=StateCodec::compress(w,ws,s,n,d,dn,mode==1,mode==2,{offset,size});}
__declspec(dllexport) void defaults(void*w,unsigned ws,const StateCodec::ReadSpan*s,unsigned n,
 const StateCodec::WriteSpan*d,unsigned dn,unsigned mode,StateCodec::Result*r){
 *r=StateCodec::compress(w,ws,s,n,d,dn,mode==1,mode==2);}
struct Sink {unsigned char*data;unsigned capacity,written,calls;};
bool emit(void*p,const StateCodec::ReadSpan(&parts)[2]){
 Sink&s=*(Sink*)p;++s.calls;
 if(parts[0].size+parts[1].size>s.capacity-s.written)return false;
 for(unsigned i=0;i<2;++i){memcpy(s.data+s.written,parts[i].data,parts[i].size);s.written+=parts[i].size;}
 return true;
}
__declspec(dllexport) void blocks(void*w,unsigned ws,const StateCodec::ReadSpan*s,unsigned n,
 const StateCodec::WriteSpan*d,unsigned dn,unsigned offset,unsigned size,StateCodec::Result*r,unsigned*calls){
 Sink sink={(unsigned char*)d[0].data,d[0].size,0,0};
 *r=StateCodec::compressQuickBlocks(w,ws,s,n,d,dn,emit,&sink,{offset,size});*calls=sink.calls;}
}
''')
        library = folder / 'codec.dll'
        subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2', '-fno-builtin',
            '-mno-stack-arg-probe', '-I', str(ROOT / 'include'), str(shim), '-o', str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        common = [C.c_void_p, C.c_uint, C.POINTER(Span), C.c_uint, C.POINTER(Span), C.c_uint]
        cls.lib.workspace.restype = C.c_uint
        cls.lib.pack.argtypes = common + [C.c_uint, C.c_uint, C.c_uint, C.POINTER(Result)]
        cls.lib.defaults.argtypes = common + [C.c_uint, C.POINTER(Result)]
        cls.lib.blocks.argtypes = common + [C.c_uint, C.c_uint, C.POINTER(Result), C.POINTER(C.c_uint)]

    def source(self, raw, splits=()):
        points = [0, *splits, len(raw)]
        owners = [C.create_string_buffer(raw[a:b]) for a, b in zip(points, points[1:])]
        spans = (Span * len(owners))(*(Span(C.addressof(p), b-a)
            for p, a, b in zip(owners, points, points[1:])))
        return owners, spans

    def encode(self, raw, gap, mode=2, splits=(), capacity=None, count=False, blocks=False, defaults=False):
        owners, source = self.source(raw, splits)
        work = Guarded(self.lib.workspace())
        output = Guarded(len(raw) + 4096 if capacity is None else capacity)
        destinations = (Span * 1)(Span(output.ptr, output.size))
        before = [p.raw for p in owners]
        descriptors = bytes(source), bytes(destinations)
        result, calls = Result(), C.c_uint()
        args = (work.ptr, work.size, source, len(source), None if count else destinations, 1)
        if blocks:
            self.lib.blocks(*args, *gap, C.byref(result), C.byref(calls))
        elif defaults:
            self.lib.defaults(*args, mode, C.byref(result))
        else:
            self.lib.pack(*args, mode, *gap, C.byref(result))
        self.assertEqual([p.raw for p in owners], before)
        self.assertEqual((bytes(source), bytes(destinations)), descriptors)
        self.assertTrue(work.guards() and output.guards())
        if result.status == 1:
            self.assertEqual(work.data(), b'\xa7' * work.size)
            self.assertEqual(output.data(), b'\xa7' * output.size)
            self.assertEqual(calls.value, 0)
        payload = output.data()[:result.compressed - 8] if blocks and result.status == 0 else output.data()[:result.compressed]
        if blocks and result.status == 0:
            payload = struct.pack('>II', 0x4D534C34, QUICK_BLOCK) + payload
        return result, payload, calls.value

    def test_quick_exact_canonical_blocks_across_spans_and_boundaries(self):
        raw = random.Random(312).randbytes(2 * QUICK_BLOCK + 41)
        gaps = [(13, 75), (QUICK_BLOCK-3, 9), (QUICK_BLOCK, QUICK_BLOCK),
                (len(raw)-9, 9), (0, len(raw))]
        for splits in ((), (19, QUICK_BLOCK-1, QUICK_BLOCK-1, QUICK_BLOCK+2)):
            for gap in gaps:
                with self.subTest(splits=splits, gap=gap):
                    canonical = raw[:gap[0]] + bytes(gap[1]) + raw[sum(gap):]
                    expected, encoded, _ = self.encode(canonical, (0, 0))
                    packed, actual, _ = self.encode(raw, gap, splits=splits)
                    streamed, blocks, calls = self.encode(raw, gap, splits=splits, blocks=True)
                    self.assertEqual((expected.status, packed.status, streamed.status), (0, 0, 0))
                    self.assertEqual(actual, encoded)
                    self.assertEqual(blocks, encoded)
                    self.assertEqual(reference_quick_frame(actual, len(raw)), canonical)
                    self.assertEqual((packed.raw, packed.adler, streamed.adler),
                                     (len(raw), zlib.adler32(canonical), zlib.adler32(canonical)))
                    self.assertEqual(calls, 3)

    def test_deflate_both_modes_across_spans_and_zero_buffer_boundaries(self):
        raw = random.Random(478).randbytes(10003)
        for mode in (0, 1):
            for gap in ((0, 257), (123, 4097), (len(raw)-1, 1), (0, len(raw))):
                with self.subTest(mode=mode, gap=gap):
                    result, encoded, _ = self.encode(raw, gap, mode, (31, 31, 250, 8192))
                    canonical = raw[:gap[0]] + bytes(gap[1]) + raw[sum(gap):]
                    self.assertEqual(result.status, 0)
                    self.assertEqual(zlib.decompress(encoded), canonical)
                    self.assertEqual((result.raw, result.adler), (len(raw), zlib.adler32(canonical)))

    def test_count_and_output_full_keep_complete_required_size(self):
        raw = random.Random(204).randbytes(QUICK_BLOCK + 333)
        gap = (QUICK_BLOCK - 17, 301)
        for mode in (0, 1, 2):
            with self.subTest(mode=mode):
                full, encoded, _ = self.encode(raw, gap, mode)
                counted, _, _ = self.encode(raw, gap, mode, count=True)
                short, prefix, _ = self.encode(raw, gap, mode, capacity=19)
                self.assertEqual((full.status, counted.status, short.status), (0, 0, 3))
                self.assertEqual((counted.compressed, short.compressed), (full.compressed, full.compressed))
                self.assertEqual((counted.adler, short.adler), (full.adler, full.adler))
                self.assertEqual(prefix, encoded[:19])
        refused, _, calls = self.encode(raw, gap, capacity=19, blocks=True)
        self.assertEqual((refused.status, refused.compressed, calls), (3, 0, 1))

    def test_empty_interval_preserves_default_encoding(self):
        raw = random.Random(67).randbytes(301)
        for mode in (0, 1, 2):
            expected, encoded, _ = self.encode(raw, (0, 0), mode, defaults=True)
            for gap in ((0, 0), (len(raw), 0)):
                actual, result, _ = self.encode(raw, gap, mode)
                self.assertEqual((actual.status, actual.adler), (expected.status, expected.adler))
                self.assertEqual(result, encoded)

    def test_invalid_ranges_and_aliases_fail_before_any_write(self):
        raw = b'unchanged source data' * 5
        for mode in (0, 1, 2):
            for gap in ((len(raw)+1, 0), (len(raw), 1), (0xffffffff, 2), (1, 0xffffffff)):
                with self.subTest(mode=mode, gap=gap):
                    result, _, _ = self.encode(raw, gap, mode)
                    self.assertEqual(result.status, 1)
                    if mode == 2:
                        result, _, _ = self.encode(raw, gap, blocks=True)
                        self.assertEqual(result.status, 1)
        owners, source = self.source(raw)
        work = Guarded(self.lib.workspace())
        result = Result()
        destination = (Span * 1)(Span(source[0].data, len(raw)))
        before = owners[0].raw
        self.lib.pack(work.ptr, work.size, source, 1, destination, 1, 2, 0, len(raw), C.byref(result))
        self.assertEqual(result.status, 1)
        self.assertEqual(owners[0].raw, before)
        self.assertEqual(work.data(), b'\xa7' * work.size)


if __name__ == '__main__': unittest.main()
