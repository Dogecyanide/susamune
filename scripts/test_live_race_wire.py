"""Independent network-order vectors and fail-closed live-pose admission."""
import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
#include "susamune/live_race_wire.h"
__declspec(dllexport) int decode(const void *p,unsigned n,unsigned *v,void *wire) {
 MSRHeader h; MSRPose s;
 if(!MSRDecodeHeader(p,n,&h) || h.kind!=MSR_POSE ||
    !MSRDecodePose((const unsigned char*)p+MSR_HEADER_BYTES,h.payloadBytes,&s))return 0;
 const unsigned a[]={h.sequence,h.sessionHigh,h.sessionLow,h.round,h.region,
  h.timing,h.participant,s.area,s.episode,s.parentArea,s.parentEpisode,s.remoteMs,
  s.sceneEpoch,(unsigned)s.x,(unsigned)s.y,(unsigned)s.z,s.yaw,s.animation,s.phase,
  s.heldNameKey,s.heldObjectId,s.yoshi,s.flags,s.buttons,(unsigned)s.stickX,(unsigned)s.stickY,
  (unsigned)s.substickX,(unsigned)s.substickY,s.triggerL,s.triggerR};
 for(unsigned i=0;i<sizeof(a)/sizeof(*a);++i)v[i]=a[i];
 return MSREncodeHeader(wire,n,&h) &&
  MSREncodePose((unsigned char*)wire+MSR_HEADER_BYTES,n-MSR_HEADER_BYTES,&s);
}
__declspec(dllexport) int after(unsigned a,unsigned b){return MSRSequenceAfter(a,b);}
'''


class LiveRaceWireTests(unittest.TestCase):
    def test_portable_vectors_and_invalid_packets(self):
        with tempfile.TemporaryDirectory(prefix='moonshine-live-wire-') as folder:
            folder = Path(folder)
            source, dll = folder / 'wire.c', folder / 'wire.dll'
            source.write_text(SOURCE, encoding='ascii')
            compiled = subprocess.run([str(ROOT / 'toolchain/clang.exe'),
                '--target=x86_64-pc-windows-msvc', '-std=c11', '-O2', '-Werror',
                '-Wall', '-Wextra', '-fno-builtin', '-ffreestanding', '-nostdlib',
                '-shared', '-fuse-ld=lld', '-Wl,/noentry', '-I', str(ROOT / 'include'),
                str(source), '-o', str(dll)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            lib = C.CDLL(str(dll))
            try:
                lib.decode.argtypes = [C.c_void_p, C.c_uint, C.c_void_p, C.c_void_p]
                lib.after.argtypes = [C.c_uint, C.c_uint]
                for region in range(3):
                    header = struct.pack('>IHBBHHIIII4B', 0x4d535231, 3, 3, 0, 56, 0,
                        0xfffffffe, 0x12345678, 0x9abcdef0, 7, region, 1, 1, 0)
                    pose = struct.pack('>4BIIiii4HIBBH', 7, 2, 6, 3, 0xfffffff0, 19,
                        -8000000, 17, 8000000, 65535, 335, 4095, 0xbeef,
                        0x40000001, 5, 1, 0) + bytes(8) + struct.pack('>H4b2B', 0x1f7f, -128, 127, -80, 42, 0, 255)
                    packet = header + pose
                    self.assertEqual(len(packet), 88)
                    expected = [0xfffffffe, 0x12345678, 0x9abcdef0, 7, region, 1, 1,
                        7, 2, 6, 3, 0xfffffff0, 19, (-8000000) & 0xffffffff, 17,
                        8000000, 65535, 335, 4095, 0xbeef, 0x40000001, 5, 1, 0x1f7f, (-128) & 0xffffffff, 127,
                        (-80) & 0xffffffff, 42, 0, 255]
                    values = (C.c_uint * 30)()
                    output = C.create_string_buffer(b'!' * 104)
                    self.assertEqual(lib.decode(packet, len(packet), values, C.addressof(output)+8), 1)
                    self.assertEqual(list(values), expected)
                    self.assertEqual(output.raw[:-1], b'!'*8 + packet + b'!'*8)

                invalid = [packet[:n] for n in range(88)] + [packet + b'\0']
                for offset, value in [(0, 0), (5, 1), (7, 1), (9, 55), (10, 1),
                        (28, 3), (29, 0), (30, 4), (31, 1), (70, 1),
                        (68, 6), (69, 2), (72, 0x81), (79, 1), (80, 0x80), (81, 0xff)]:
                    altered = bytearray(packet)
                    altered[offset] = value
                    invalid.append(bytes(altered))
                for offset, value in [(44, 0x80000000), (48, 8000001), (52, 0x7fffffff)]:
                    altered = bytearray(packet)
                    struct.pack_into('>I', altered, offset, value)
                    invalid.append(bytes(altered))
                for offset, value in [(58, 336), (60, 4096)]:
                    altered = bytearray(packet)
                    struct.pack_into('>H', altered, offset, value)
                    invalid.append(bytes(altered))
                for bad in invalid:
                    values = (C.c_uint * 30)(*[0xa7a7a7a7]*30)
                    output = C.create_string_buffer(b'!' * 104)
                    self.assertEqual(lib.decode(bad, len(bad), values, C.addressof(output)+8), 0)
                    self.assertEqual(list(values), [0xa7a7a7a7]*30)
                    self.assertEqual(output.raw[:-1], b'!'*104)
                self.assertTrue(lib.after(0, 0xffffffff))
                self.assertFalse(lib.after(0xffffffff, 0))
                self.assertFalse(lib.after(7, 7))
                self.assertFalse(lib.after(0x80000000, 0))
            finally:
                C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle))


if __name__ == '__main__':
    unittest.main()
