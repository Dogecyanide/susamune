"""Exercise the production own-disc decoder; native fixtures remain local."""
import argparse
import ctypes as C
import _ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from inspect_rarc_asset import disc_files, decode_yaz0, rarc_files

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = None


def picture(data):
    from PIL import Image
    width, height = struct.unpack_from(">HH", data, 2)
    image = Image.new("RGBA", (width, height))
    for y in range(height):
        for x in range(width):
            offset = 32 + (((y // 4) * ((width + 3) // 4) + x // 4) * 16 +
                           (y & 3) * 4 + (x & 3)) * 2
            p = struct.unpack_from(">H", data, offset)[0]
            color = (((p >> 10) & 31) * 255 // 31, ((p >> 5) & 31) * 255 // 31,
                     (p & 31) * 255 // 31, 255) if p & 0x8000 else (
                     ((p >> 8) & 15) * 17, ((p >> 4) & 15) * 17,
                     (p & 15) * 17, ((p >> 12) & 7) * 255 // 7)
            image.putpixel((x, y), color)
    return image


class NativeIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="native-menu-icon-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        cpp = Path(cls.temp.name) / "fixture.cpp"
        cpp.write_text(r'''
#include "susamune/menu_native_icon.h"
using namespace MenuNativeIcon;
struct Guarded { Byte before[32]; Workspace value; Byte after[32]; } workspace;
Word sourceSize, calls, requested, failedAt;
bool badRead;
bool readInput(void *context, Word at, Byte *out, Word size) {
 ++calls; requested += size;
 if ((at & 31) || size > sizeof(workspace.value.metadata) || !range(at,size,sourceSize)) {
  badRead=true; return false;
 }
 if(at>=failedAt)return false;
 const Byte*p=static_cast<const Byte*>(context)+at;
 for(Word i=0;i<size;++i)out[i]=p[i];
 return true;
}
#define API extern "C" __declspec(dllexport)
API bool run(Byte*input,Word size,Byte*out,Word cap,Word fail) {
 sourceSize=size; calls=requested=0;badRead=false;failedAt=fail;
 for(Word i=0;i<32;++i)workspace.before[i]=workspace.after[i]=0xa7;
 return extract(readInput,input,size,workspace.value,out,cap);
}
API bool guards() {
 for(Word i=0;i<32;++i)if(workspace.before[i]!=0xa7||workspace.after[i]!=0xa7)return false;
 return !badRead;
}
API Word readCalls(){return calls;}
API Word bytesRequested(){return requested;}
API bool controller(const Byte*p,Word n,Byte*out,Word cap){return shrinkController(p,n,out,cap);}
API bool tables(const Byte*p,Word n,Word outputSize){
 if(n>sizeof(workspace.value.metadata))return false;
 for(Word i=0;i<n;++i)workspace.value.metadata[i]=p[i];
 Decoder d={workspace.value,readInput,0,0,0,0,0,outputSize,0,n,0,workspace.value.input,false};
 return d.tables();
}
''')
        dll = cpp.with_suffix(".dll")
        command = [str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                   "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-fno-builtin",
                   "-O2", "-I", str(ROOT / "include"), str(cpp), "-o", str(dll)]
        result = subprocess.run(command, capture_output=True, text=True,
                                env={**os.environ, "TEMP": cls.temp.name, "TMP": cls.temp.name})
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.run.argtypes = [C.c_char_p, C.c_uint, C.c_void_p, C.c_uint, C.c_uint]
        cls.lib.run.restype = cls.lib.guards.restype = C.c_bool
        cls.lib.controller.argtypes = [C.c_char_p, C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.controller.restype = C.c_bool
        cls.lib.tables.argtypes = [C.c_char_p, C.c_uint, C.c_uint]
        cls.lib.tables.restype = C.c_bool

    def extract(self, source, capacity=2080, fail=0xffffffff):
        out = C.create_string_buffer(b"\x69" * (2080 + 64))
        ok = self.lib.run(source, len(source), C.byref(out, 32), capacity, fail)
        self.assertTrue(self.lib.guards())
        self.assertEqual(out.raw[:32], b"\x69" * 32)
        self.assertEqual(out.raw[2112:2144], b"\x69" * 32)
        if not ok:
            self.assertEqual(out.raw[32:2112], b"\x69" * 2080)
        return ok, out.raw[32:2112]

    def test_bad_yaz0_and_metadata_fail_without_publication(self):
        header = b"Yaz0" + struct.pack(">I", 0x10000) + bytes(8)
        cases = (b"", header, b"Bad0" + header[4:], header + b"\0\0\0",
                 header + b"\xff" + b"not RARC", header[:4] + b"\xff" * 4 + header[8:])
        for source in cases:
            with self.subTest(source=source[:20]):
                self.assertFalse(self.extract(source)[0])
        metadata = bytearray(64)
        metadata[:4] = b"RARC"
        struct.pack_into(">III", metadata, 4, 0x10000, 0x20, 0x20)
        struct.pack_into(">I", metadata, 0x20, 0xffffffff)
        self.assertFalse(self.lib.tables(bytes(metadata), len(metadata), 0x10000))

    def test_controller_rejects_bounds_and_preserves_transparency(self):
        source = bytearray(24992)
        source[0] = 5
        struct.pack_into(">HH", source, 2, 120, 104)
        struct.pack_into(">I", source, 28, 32)
        out = C.create_string_buffer(6272)
        self.assertTrue(self.lib.controller(bytes(source), len(source), out, 6272))
        self.assertEqual(out.raw[32:], bytes(6240))
        self.assertFalse(self.lib.controller(bytes(source), len(source) - 1, out, 6272))
        self.assertFalse(self.lib.controller(bytes(source), len(source), out, 6271))
        struct.pack_into(">I", source, 28, 0)
        self.assertFalse(self.lib.controller(bytes(source), len(source), out, 6272))

    def test_three_retail_regions_produce_identical_boo(self):
        if not OPTIONS or not OPTIONS.iso_root:
            self.skipTest("supply --iso-root for private native fixtures")
        receipts, outputs = [], []
        for region, leaf in (
            ("jp", "SUper Mario Sunshine (Japan).iso"),
            ("us", "Super Mario Sunshine (USA).iso"),
            ("pal", "Super Mario Sunshine (Europe) (En,Fr,De,Es,It).iso"),
        ):
            with (OPTIONS.iso_root / leaf).open("rb") as f, mmap.mmap(
                    f.fileno(), 0, access=mmap.ACCESS_READ) as iso:
                files = disc_files(iso)
                at, size = files["data/scene/casino0.szs"]
                source = iso[at:at + size]
                ok, image = self.extract(source)
                self.assertTrue(ok, region)
                outputs.append(image)
                receipts.append(dict(region=region, disc_id=iso[:6].decode("ascii"),
                                     compressed_bytes=size, bytes_requested=self.lib.bytesRequested(),
                                     read_calls=self.lib.readCalls(),
                                     boo_sha256=hashlib.sha256(image).hexdigest()))
                self.assertFalse(self.extract(source, capacity=2079)[0])
                self.assertFalse(self.extract(source[:1024])[0])
                self.assertFalse(self.extract(source, fail=1024)[0])
                if region == "pal":
                    decoded_archive = bytearray(decode_yaz0(source))
                    model = next(v for k, v in rarc_files(decoded_archive).items()
                                 if k.endswith("/srotdram.bmd"))
                    model_at = decoded_archive.index(model)
                    decoded_archive[model_at + 32] ^= 1
                    prefix = decoded_archive[:model_at + len(model)]
                    corrupt = (source[:16] + b"".join(
                        b"\xff" + prefix[p:p + 8] for p in range(0, len(prefix), 8)))
                    self.assertFalse(self.extract(corrupt)[0])
                    at, size = files["data/option.szs"]
                    option = rarc_files(decode_yaz0(iso[at:at + size]))
                    controller = next(v for k, v in option.items() if k.endswith("/option_control.bti"))
                    out = C.create_string_buffer(6272)
                    self.assertTrue(self.lib.controller(controller, len(controller), out, 6272))
                    if OPTIONS.receipt:
                        picture(out.raw).save(OPTIONS.receipt.parent / "controller-60x52.png")
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])
        decoded = picture(outputs[0])
        self.assertEqual(decoded.getpixel((0, 0))[3], 0)
        self.assertGreater(sum(c[3] == 255 for c in decoded.get_flattened_data()), 200)
        if OPTIONS.receipt:
            OPTIONS.receipt.parent.mkdir(parents=True, exist_ok=True)
            decoded.save(OPTIONS.receipt.parent / "boo-32x32.png")
            decoded.resize((256, 256)).save(OPTIONS.receipt.parent / "boo-preview.png")
            OPTIONS.receipt.write_text(json.dumps(dict(
                core_sha256=hashlib.sha256((ROOT / "include/susamune/menu_native_icon.h").read_bytes()).hexdigest(),
                workspace_bytes=76704, cache_bytes=12224, regions=receipts), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iso-root", type=Path)
    parser.add_argument("--receipt", type=Path)
    OPTIONS, rest = parser.parse_known_args()
    if OPTIONS.receipt:
        OPTIONS.receipt.parent.mkdir(parents=True, exist_ok=True)
    unittest.main(argv=[__file__, *rest])
