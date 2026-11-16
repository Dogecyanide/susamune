"""Exercise real kernel FatFs creation with colliding long recording names."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NAMES_FILE = None
EVIDENCE_FILE = None
EVIDENCE = {}
DIRECTORY = b'0:/Moonshine data/ghosts/recordings/'

FIXTURE = r'''
#include "ff.h"
#include "diskio.h"
void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){BYTE*a=d;const BYTE*b=s;while(n--)*a++=*b++;return d;}
void *memset(void*d,int v,__SIZE_TYPE__ n){BYTE*a=d;while(n--)*a++=(BYTE)v;return d;}
#include "variant.c"
#define API __declspec(dllexport)
#define SECTORS 8192
static BYTE image[SECTORS*512];
static FATFS volume;
static unsigned reads,writes,failRead,failWrite,writeProtected;
DSTATUS disk_initialize(BYTE drive){return drive?STA_NODISK:(writeProtected?STA_PROTECT:0);}
DSTATUS disk_status(BYTE drive){return disk_initialize(drive);}
static DRESULT readDisk(BYTE drive,BYTE*out,DWORD sector,UINT count){
 if(drive||sector>=SECTORS||count>SECTORS-sector)return RES_PARERR;
 if(++reads==failRead)return RES_ERROR;
 memcpy(out,image+sector*512,count*512);return RES_OK;
}
static DRESULT writeDisk(BYTE drive,const BYTE*in,DWORD sector,UINT count){
 if(drive||sector>=SECTORS||count>SECTORS-sector)return RES_PARERR;
 if(++writes==failWrite)return RES_ERROR;
 if(writeProtected)return RES_WRPRT;
 memcpy(image+sector*512,in,count*512);return RES_OK;
}
DiskReadFunc disk_read=readDisk;
DiskWriteFunc disk_write=writeDisk;
DRESULT disk_ioctl(BYTE drive,BYTE cmd,void*out){
 if(drive)return RES_PARERR;
 if(cmd==CTRL_SYNC)return RES_OK;
 if(cmd==GET_SECTOR_SIZE){*(WORD*)out=512;return RES_OK;}
 if(cmd==GET_SECTOR_COUNT){*(DWORD*)out=SECTORS;return RES_OK;}
 if(cmd==GET_BLOCK_SIZE){*(DWORD*)out=1;return RES_OK;}
 return RES_PARERR;
}
DWORD get_fattime(void){return (46u<<25)|(11u<<21)|(6u<<16);}
static void word(unsigned offset,WORD value){image[offset]=value;image[offset+1]=value>>8;}
static int pathOf(const char*in,TCHAR*out){unsigned n=0;do{if(n==511)return 0;out[n]=(BYTE)in[n];}while(in[n++]);return 1;}
static const TCHAR drive[]={'0',':',0};
API void faults(unsigned readAt,unsigned writeAt,unsigned protect){reads=writes=0;failRead=readAt;failWrite=writeAt;writeProtected=protect;volume.winsect=0xffffffff;}
API unsigned statIo(unsigned write){return write?writes:reads;}
API unsigned imageSize(void){return sizeof(image);}
API const BYTE* imageBytes(void){return image;}
API int remount(void){int r=f_mount(0,drive,0);if(r)return r;memset(&volume,0,sizeof(volume));return f_mount(&volume,drive,1);}
API int resetDisk(void){
 f_mount(0,drive,0);memset(image,0,sizeof(image));writeProtected=failRead=failWrite=reads=writes=0;
 image[0]=0xeb;image[1]=0x3c;image[2]=0x90;memcpy(image+3,"MSDOS5.0",8);
 word(11,512);image[13]=1;word(14,1);image[16]=1;word(17,512);word(19,SECTORS);
 image[21]=0xf8;word(22,32);word(24,32);word(26,64);image[38]=0x29;
 memcpy(image+54,"FAT16   ",8);word(510,0xaa55);word(512,0xfff8);word(514,0xffff);
 return remount();
}
API int loadImage(const BYTE*data,unsigned bytes){
 if(bytes!=sizeof(image))return FR_INVALID_PARAMETER;
 f_mount(0,drive,0);memcpy(image,data,bytes);writeProtected=failRead=failWrite=reads=writes=0;return remount();
}
API int mkdirOne(const char*name){TCHAR p[512];if(!pathOf(name,p))return FR_INVALID_NAME;return f_mkdir(p);}
API int createFile(const char*name,const BYTE*data,unsigned size,unsigned mode){
 TCHAR p[512];FIL f;UINT done=0;int r,closed;
 if(!pathOf(name,p))return FR_INVALID_NAME;
 r=f_open(&f,p,FA_WRITE|mode);if(r)return r;
 r=f_write(&f,data,size,&done);closed=f_close(&f);if(r)return r;if(closed)return closed;return done==size?FR_OK:FR_INT_ERR;
}
API int readFile(const char*name,BYTE*out,unsigned cap){
 TCHAR p[512];FIL f;UINT done=0;int r,closed;if(!pathOf(name,p))return -FR_INVALID_NAME;
 r=f_open(&f,p,FA_READ);if(r)return -r;
 r=f_read(&f,out,cap,&done);closed=f_close(&f);return r?-r:closed?-closed:(int)done;
}
API int renameFile(const char*from,const char*to){TCHAR a[512],b[512];if(!pathOf(from,a)||!pathOf(to,b))return FR_INVALID_NAME;return f_rename(a,b);}
API int deleteFile(const char*name){TCHAR p[512];if(!pathOf(name,p))return FR_INVALID_NAME;return f_unlink(p);}
API int aliasFor(const char*name,unsigned seq,char*out){
 WCHAR lfn[256];TCHAR p[512];const TCHAR*cursor=p;DIR d;BYTE sn[12];unsigned i,n=0;
 if(!pathOf(name,p))return FR_INVALID_NAME;
 memset(&d,0,sizeof(d));d.obj.fs=&volume;volume.lfnbuf=lfn;
 int r=create_name(&d,&cursor);if(r)return r;gen_numname(sn,d.fn,lfn,seq);
 for(i=0;i<8&&sn[i]!=' ';i++)out[n++]=sn[i];
 if(sn[8]!=' '){out[n++]='.';for(i=8;i<11&&sn[i]!=' ';i++)out[n++]=sn[i];}
 out[n]=0;return 0;
}
API int configuration(void){return _FS_RPATH|(_USE_LFN<<4)|(_FS_EXFAT<<8);}
'''


def names_for_test():
    if NAMES_FILE:
        return json.loads(NAMES_FILE.read_text(encoding='utf-8-sig'))
    names = []
    for i in range(307):
        nonce = (0xC1A6804B + i * 0x9e3779b9) & 0xffffffff
        if i in (0, 170, 306):
            names.append(f'trace_{nonce:08X}_{0x80000000+i:08X}.part')
        elif i % 3:
            names.append(f'trace_{nonce:08X}_{0x80000000+i:08X}.msgt')
        else:
            names.append(f'ref_{nonce:08X}_80000001_00000000_0000003F_00000001.msgb')
    return names


def compile_library(folder, policy):
    folder.mkdir()
    production = ROOT / 'launcher/fatfs/ff.c'
    source = production.read_text(encoding='utf-8')
    if policy == 'candidate':
        EVIDENCE['production_sha256'] = hashlib.sha256(production.read_bytes()).hexdigest()
    pattern = r'for \(n = \d+; n < \d+; n\+\+\) \{(\s*gen_numname\(dp->fn, sn, fs->lfnbuf, n\);)'
    if len(re.findall(pattern, source)) != 1 or 'for (n = 6; n < 105; n++)' not in source:
        raise AssertionError('Production must try the 99 hash-first SFN candidates')
    if source.count('if (n == 105) return FR_DENIED;') != 1:
        raise AssertionError('Production must refuse all 99 collisions')
    if policy == 'baseline':
        source = source.replace('for (n = 6; n < 105; n++)', 'for (n = 1; n < 100; n++)')
        source = source.replace('if (n == 105) return FR_DENIED;', 'if (n == 100) return FR_DENIED;')
    (folder / 'variant.c').write_text(source, encoding='utf-8')
    fixture = folder / 'fixture.c'
    fixture.write_text(FIXTURE, encoding='ascii')
    library = folder / 'fixture.dll'
    fatfs = ROOT / 'launcher/fatfs'
    result = subprocess.run([str(ROOT / 'toolchain/clang.exe'),
        '--target=x86_64-pc-windows-msvc', '-U_WIN32', '-shared', '-nostdlib',
        '-fno-builtin', '-mno-stack-arg-probe', '-O2', '-fuse-ld=lld', '-Wl,/noentry',
        '-I', str(fatfs), str(fixture), str(fatfs / 'option/ccsbcs.c'), '-o', str(library)],
        capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    lib = C.CDLL(str(library))
    lib.createFile.argtypes = [C.c_char_p, C.c_void_p, C.c_uint, C.c_uint]
    lib.readFile.argtypes = [C.c_char_p, C.c_void_p, C.c_uint]
    lib.renameFile.argtypes = [C.c_char_p, C.c_char_p]
    lib.deleteFile.argtypes = lib.mkdirOne.argtypes = [C.c_char_p]
    lib.aliasFor.argtypes = [C.c_char_p, C.c_uint, C.c_void_p]
    lib.faults.argtypes = [C.c_uint, C.c_uint, C.c_uint]
    lib.loadImage.argtypes = [C.c_void_p, C.c_uint]
    lib.imageBytes.restype = C.c_void_p
    return lib


class FatFsLfnCreateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / 'toolchain/clang.exe').exists():
            raise unittest.SkipTest('Bundled Windows compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-fatfs-lfn-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.libs = {name: compile_library(Path(cls.temp.name) / name, name)
                    for name in ('baseline', 'candidate')}
        for lib in cls.libs.values():
            cls.addClassCleanup(lambda lib=lib: C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
        cls.names = names_for_test()
        if len(cls.names) != len(set(name.upper() for name in cls.names)):
            raise AssertionError('Recording names must be unique on FAT')
        lib = cls.libs['baseline']
        cls.initialize(lib)
        for i, name in enumerate(cls.names):
            data = f'old-recording-{i:03}'.encode()
            result = lib.createFile(DIRECTORY + name.encode('ascii'), data, len(data), 4)
            if result:
                raise AssertionError(f'Cannot prepare {name}: {result}')
        cls.base_image = C.string_at(lib.imageBytes(), lib.imageSize())
        EVIDENCE['recording_names'] = len(cls.names)
        EVIDENCE['configuration'] = 'Kernel FatFs: RPATH=0, LFN=2, exFAT support enabled; in-memory FAT16'
        EVIDENCE['scope'] = 'Real production FatFs device-request counts, not elapsed Wii time'

    @staticmethod
    def initialize(lib):
        if lib.resetDisk():
            raise AssertionError('Cannot format FAT16 fixture')
        for path in (b'0:/Moonshine data', b'0:/Moonshine data/ghosts', DIRECTORY[:-1]):
            if lib.mkdirOne(path):
                raise AssertionError(f'Cannot create {path}')

    def restored(self, policy='candidate'):
        lib = self.libs[policy]
        self.assertEqual(lib.loadImage(self.base_image, len(self.base_image)), 0)
        return lib

    def create(self, lib, name, data=b'new capture header', mode=4):
        return lib.createFile(DIRECTORY + name.encode(), data, len(data), mode)

    def read(self, lib, name):
        output = C.create_string_buffer(512)
        size = lib.readFile(DIRECTORY + name.encode(), output, len(output))
        return output.raw[:size] if size >= 0 else size

    def alias(self, lib, leaf, seq):
        output = C.create_string_buffer(20)
        self.assertEqual(lib.aliasFor(leaf.encode(), seq, output), 0)
        return output.value.decode()

    def image(self, lib):
        return C.string_at(lib.imageBytes(), lib.imageSize())

    def test_kernel_configuration_and_existing_names_survive_remount(self):
        lib = self.restored()
        self.assertEqual(lib.configuration(), 0x120)
        for i, name in enumerate(self.names):
            self.assertEqual(self.read(lib, name), f'old-recording-{i:03}'.encode())
        self.assertEqual(lib.remount(), 0)
        for i in (0, len(self.names)//2, len(self.names)-1):
            self.assertEqual(self.read(lib, self.names[i]), f'old-recording-{i:03}'.encode())

    def test_same_directory_image_reduces_create_work(self):
        target = 'trace_ABCDEF01_FF123456.part'
        final = target[:-4] + 'msgt'
        work = {}
        for policy in self.libs:
            lib = self.restored(policy)
            work[policy] = {}
            for operation, action in (
                ('create', lambda: self.create(lib, target, b'X'*64)),
                ('rename', lambda: lib.renameFile(DIRECTORY+target.encode(), DIRECTORY+final.encode())),
                ('delete', lambda: lib.deleteFile(DIRECTORY+final.encode())),
            ):
                lib.faults(0, 0, 0)
                self.assertEqual(action(), 0, (policy, operation))
                work[policy][operation] = {'reads': lib.statIo(0), 'writes': lib.statIo(1)}
            self.assertEqual(lib.remount(), 0)
            for i, name in enumerate(self.names):
                self.assertEqual(self.read(lib, name), f'old-recording-{i:03}'.encode())
        EVIDENCE['same_image_operation_counts'] = work
        self.assertLess(work['candidate']['create']['reads'], work['baseline']['create']['reads'])
        self.assertLessEqual(work['candidate']['rename']['reads'], work['baseline']['rename']['reads'])

    def test_create_new_duplicate_refuses_without_any_disk_mutation(self):
        for policy in self.libs:
            lib = self.restored(policy)
            name = self.names[len(self.names)//2]
            before = self.image(lib)
            lib.faults(0, 0, 0)
            self.assertEqual(self.create(lib, name, b'cannot overwrite'), 8)
            self.assertEqual(lib.statIo(1), 0)
            self.assertEqual(self.image(lib), before)
            self.assertEqual(self.read(lib, name), f'old-recording-{len(self.names)//2:03}'.encode())

    def test_hash_alias_collision_retries_without_overwriting_alias_owner(self):
        lib = self.libs['candidate']
        self.initialize(lib)
        target = 'trace_ABCDEF01_80000001.part'
        alias6 = self.alias(lib, target, 6)
        alias7 = self.alias(lib, target, 7)
        self.assertNotEqual(alias6, alias7)
        self.assertEqual(self.create(lib, alias6, b'alias owner'), 0)
        self.assertEqual(self.create(lib, target, b'new long name'), 0)
        self.assertEqual(lib.remount(), 0)
        self.assertEqual(self.read(lib, target), b'new long name')
        self.assertEqual(self.read(lib, alias6), b'alias owner')
        self.assertEqual(self.read(lib, alias7), b'new long name')

    def test_all_99_alias_collisions_refuse_without_disk_mutation(self):
        for policy, bounds in (('baseline', (1, 100)), ('candidate', (6, 105))):
            with self.subTest(policy=policy):
                lib = self.libs[policy]
                self.initialize(lib)
                target = 'trace_ABCDEF01_80000002.part'
                aliases = {self.alias(lib, target, n) for n in range(*bounds)}
                for name in aliases:
                    self.assertEqual(self.create(lib, name, b'owned'), 0)
                before = self.image(lib)
                lib.faults(0, 0, 0)
                self.assertEqual(self.create(lib, target), 7)
                self.assertEqual(lib.statIo(1), 0)
                self.assertEqual(self.image(lib), before)
                self.assertEqual(lib.remount(), 0)
                for name in aliases:
                    self.assertEqual(self.read(lib, name), b'owned')

    def test_read_error_is_reported_without_mutating_existing_files(self):
        lib = self.restored()
        before = self.image(lib)
        lib.faults(1, 0, 0)
        self.assertEqual(self.create(lib, 'trace_DEADBEEF_FF123456.part'), 1)
        self.assertEqual(lib.statIo(1), 0)
        self.assertEqual(self.image(lib), before)
        lib.faults(0, 0, 0)
        self.assertEqual(lib.remount(), 0)
        self.assertEqual(self.read(lib, self.names[0]), b'old-recording-000')

    def test_write_error_is_reported_and_existing_file_remains_readable(self):
        lib = self.restored()
        lib.faults(0, 1, 0)
        self.assertEqual(self.create(lib, 'trace_DEADBEEF_FF123456.part', b'X'*1024), 1)
        lib.faults(0, 0, 0)
        self.assertEqual(lib.remount(), 0)
        for i in (0, len(self.names)//2, len(self.names)-1):
            self.assertEqual(self.read(lib, self.names[i]), f'old-recording-{i:03}'.encode())

    def test_write_protection_refuses_creation_and_preserves_image(self):
        lib = self.restored()
        before = self.image(lib)
        lib.faults(0, 0, 1)
        self.assertEqual(self.create(lib, 'trace_DEADBEEF_FF123456.part'), 10)
        self.assertEqual(lib.statIo(1), 0)
        self.assertEqual(self.image(lib), before)
        self.assertEqual(self.read(lib, self.names[0]), b'old-recording-000')
        lib.faults(0, 0, 0)

    def test_short_name_and_repeated_discard_round_trips(self):
        lib = self.restored()
        self.assertEqual(self.create(lib, 'SHORT.BIN', b'short'), 0)
        self.assertEqual(self.read(lib, 'SHORT.BIN'), b'short')
        for i in range(4):
            leaf = f'trace_10203040_{0x80000000+i:08X}.part'
            final = leaf[:-4] + 'msgt'
            self.assertEqual(self.create(lib, leaf, bytes([i])*64), 0)
            self.assertEqual(lib.remount(), 0)
            self.assertEqual(self.read(lib, leaf), bytes([i])*64)
            self.assertEqual(lib.renameFile(DIRECTORY+leaf.encode(), DIRECTORY+final.encode()), 0)
            self.assertEqual(lib.remount(), 0)
            self.assertEqual(self.read(lib, final), bytes([i])*64)
            self.assertEqual(lib.deleteFile(DIRECTORY+final.encode()), 0)
            self.assertEqual(self.read(lib, final), -4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--recording-names', type=Path)
    parser.add_argument('--evidence', type=Path)
    options, rest = parser.parse_known_args()
    NAMES_FILE, EVIDENCE_FILE = options.recording_names, options.evidence
    program = unittest.main(argv=[sys.argv[0]] + rest, exit=False)
    if EVIDENCE_FILE:
        EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE['tests_run'] = program.result.testsRun
        EVIDENCE['successful'] = program.result.wasSuccessful()
        EVIDENCE_FILE.write_text(json.dumps(EVIDENCE, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(not program.result.wasSuccessful())
