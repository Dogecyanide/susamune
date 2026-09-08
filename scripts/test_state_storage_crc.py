"""Compare the production table CRC with existing archive bytes and seed semantics."""
import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]


class StateStorageCrcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=ROOT/'toolchain/clang.exe'
        if not compiler.exists():raise unittest.SkipTest('Bundled Windows compiler required')
        cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-state-crc-')
        cls.addClassCleanup(cls.temp.cleanup)
        path=Path(cls.temp.name)
        (path/'crc.c').write_text(r'''
#include "susamune/state_storage.h"
__declspec(dllexport) unsigned int update(unsigned int crc,const void*p,unsigned int n){return SusamuneStateCrcUpdate(crc,p,n);}
__declspec(dllexport) unsigned int legacy(unsigned int crc,const void*p,unsigned int n){
 const unsigned char*b=p;unsigned int i,bit;
 for(i=0;i<n;++i){crc^=b[i];for(bit=0;bit<8;++bit)crc=(crc>>1)^((0u-(crc&1u))&0xEDB88320u);}return crc;
}
__declspec(dllexport) unsigned int archive(const void*p){return SusamuneStateHeaderCrc(p);}
__declspec(dllexport) unsigned int name(const void*p){return SusamuneStateNameCrc(p);}
''',encoding='ascii')
        result=subprocess.run([str(compiler),'--target=x86_64-pc-windows-msvc','-shared','-O2',
            '-nostdlib','-fuse-ld=lld','-Wl,/noentry','-I',str(ROOT/'include'),
            str(path/'crc.c'),'-o',str(path/'crc.dll')],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        cls.lib=C.CDLL(str(path/'crc.dll'))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        for func in ('update','legacy'):
            getattr(cls.lib,func).argtypes=[C.c_uint,C.c_void_p,C.c_uint]
            getattr(cls.lib,func).restype=C.c_uint
        for func in ('archive','name'):
            getattr(cls.lib,func).argtypes=[C.c_void_p]
            getattr(cls.lib,func).restype=C.c_uint

    def test_standard_vectors_and_legacy_seed_compatibility(self):
        rng=random.Random(9327)
        cases=[b'',b'123456789',bytes(range(256))]
        cases += [rng.randbytes(size) for size in (1,2,3,31,32,33,255,4096,16384,65537,1000000)]
        for data in cases:
            owner=C.create_string_buffer(b'!'+data)
            pointer=C.addressof(owner)+1
            for seed in (0,0xFFFFFFFF,0xCBF43926,rng.getrandbits(32)):
                with self.subTest(size=len(data),seed=seed):
                    actual=self.lib.update(seed,pointer,len(data))
                    self.assertEqual(actual,self.lib.legacy(seed,pointer,len(data)))
                    self.assertEqual(actual,(~zlib.crc32(data,(~seed)&0xFFFFFFFF))&0xFFFFFFFF)

    def test_chunked_accumulation_and_header_checksum_holes_are_unchanged(self):
        rng=random.Random(6587)
        data=rng.randbytes(100003);owner=C.create_string_buffer(data)
        for chunk in (1,7,31,16384,65536):
            crc=0xFFFFFFFF
            for offset in range(0,len(data),chunk):
                crc=self.lib.update(crc,C.addressof(owner)+offset,min(chunk,len(data)-offset))
            self.assertEqual((~crc)&0xFFFFFFFF,zlib.crc32(data))
        for size,func in ((96,'archive'),(64,'name')):
            header=bytearray(rng.randbytes(size));owner=C.create_string_buffer(bytes(header))
            header[48:52]=bytes(4)
            self.assertEqual(getattr(self.lib,func)(owner),zlib.crc32(header))


if __name__=='__main__':unittest.main()
