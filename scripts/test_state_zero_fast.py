"""Zero Quick blocks keep vendor bytes, checksums and protected-output rules."""
import ctypes as C
from pathlib import Path
import random
import struct
import tempfile
import unittest
import zlib

from test_state_codec import Guarded, Span, DirectPolicy
from timewarp_chunk_codec import Codec, ROOT, decode_case


class ZeroFastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='state-zero-fast-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = folder/'zero.cpp'
        source.write_text('#include "'+(ROOT/'src/state_codec.cpp').as_posix()+'"\n'+r'''
extern "C" {
__declspec(dllexport) unsigned optimized(void*w,const unsigned char*p,unsigned n,void*out){
 StateCodec::QuickWorkspace*q=(StateCodec::QuickWorkspace*)w;
 unsigned size=StateCodec::quickLz4Block(q,p,n);memcpy(out,q->packed,size);return size;}
__declspec(dllexport) unsigned reference(void*w,const char*p,unsigned n,char*out){
 return LZ4_compress_fast_extState(w,p,out,n,LZ4_COMPRESSBOUND(n),8);}
__declspec(dllexport) unsigned checkZero(const unsigned char*p,unsigned n,unsigned raw){return StateCodec::packedZero(p,n,raw);}
__declspec(dllexport) unsigned zeroAdler(unsigned seed,unsigned n){return StateCodec::zeroAdler(seed,n);}
}
''')
        cls.codec = Codec(folder, source)
        cls.addClassCleanup(cls.codec.close)
        for name in ('optimized', 'reference'):
            getattr(cls.codec.lib, name).argtypes = [C.c_void_p, C.c_void_p, C.c_uint, C.c_void_p]
            getattr(cls.codec.lib, name).restype = C.c_uint
        cls.codec.lib.checkZero.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
        cls.codec.lib.zeroAdler.argtypes = [C.c_uint, C.c_uint]
        cls.codec.lib.zeroAdler.restype = C.c_uint

    def block(self, data):
        source = C.create_string_buffer(data)
        candidate, reference = Guarded(len(data)+1024), Guarded(len(data)+1024)
        a = self.codec.lib.optimized(self.codec.work.ptr, source, len(data), candidate.ptr)
        b = self.codec.lib.reference(self.codec.work.ptr, source, len(data), reference.ptr)
        self.assertEqual(candidate.data()[:a], reference.data()[:b])
        self.assertTrue(candidate.guards() and reference.guards() and self.codec.work.guards())
        return candidate.data()[:a]

    def test_zero_and_near_zero_encode_exact_vendor_bytes(self):
        for size in (*range(1, 65), 254, 255, 256, 279, 280, 281, 65535, 65536, 131071, 131072):
            packed = self.block(bytes(size))
            owner = C.create_string_buffer(packed)
            self.assertEqual(bool(self.codec.lib.checkZero(owner, len(packed), size)), size >= 32)
        for offset in (0, 1, 15, 16, 65535, 131070, 131071):
            data = bytearray(131072); data[offset] = 1
            self.block(bytes(data))

    def test_adler_all_lengths_and_nonzero_prefixes(self):
        rng = random.Random(8824)
        for length in (0, 1, 31, 32, 255, 65520, 65521, 65522, 131071, 131072):
            for seed in (1, zlib.adler32(rng.randbytes(317)), 0xffffffff):
                self.assertEqual(self.codec.lib.zeroAdler(seed, length), zlib.adler32(bytes(length), seed))

    def test_strict_stream_recognition_and_filtered_restore(self):
        raw = bytes(131072)
        block = self.block(raw)
        for index in range(len(block)):
            changed = bytearray(block); changed[index] ^= 1
            owner = C.create_string_buffer(bytes(changed))
            self.assertFalse(self.codec.lib.checkZero(owner, len(changed), len(raw)))
        frame = b'MSL4\0\2\0\0'+struct.pack('>II',len(raw),len(block))+block
        for split in (1, 16, len(frame)-3):
            for protected in (False, True):
                decode_case(self.codec, frame, raw, [frame[:split], frame[split:]], preserve=protected)
        owners = [C.create_string_buffer(frame)]
        spans = (Span*1)(Span(C.addressof(owners[0]), len(frame)))
        self.assertNotEqual(self.codec.check(spans, len(raw), zlib.adler32(raw)^1), 0)


if __name__ == '__main__':
    unittest.main()
