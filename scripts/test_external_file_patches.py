"""Compile the production loader/parser with a small guarded patch window and fake FAT."""
import ctypes
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExternalFilePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Windows native fixture")
        clang = ROOT / "toolchain/clang.exe"
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-filepatch-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = (ROOT / "launcher/loader/source/main.c").read_text()
        start = source.index("static bool patchOnce = false;")
        end = source.index("\nvoid SMC_ROM(void)", start)
        production = source[start:end].replace("\n#endif\n", "\n", 1)
        fields = sorted(set(re.findall(r"ncfg->(\w+)", production)) - {"GamePath"})
        macros = sorted(set(re.findall(r"\bNIN_[A-Z0-9_]+", production)) -
                        {"NIN_MEM2_FILE_PATCH_SIZE", "NIN_MEM2_FILE_PATCH_PPC_BASE"})
        prelude = r"""
typedef __SIZE_TYPE__ size_t;
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;
typedef signed int s32; typedef volatile unsigned int vu32; typedef _Bool bool;
#define true 1
#define false 0
#define NULL ((void*)0)
#define NIN_MEM2_FILE_PATCH_SIZE 68u
#define NIN_MEM2_FILE_PATCH_PPC_BASE 0x91900000u
#define FR_OK 0
#define FR_DISK_ERR 1
#define FR_NO_FILE 4
#define FR_NO_PATH 5
#define FA_READ 1
#define FA_OPEN_EXISTING 0
#define API __declspec(dllexport)
static void *(*copy_fn)(void*,const void*,size_t);
static size_t (*length_fn)(const char*);
static int (*casecmp_fn)(const char*,const char*,size_t);
static int (*scan_fn)(const char*,const char*,...);
static int (*format_fn)(char*,size_t,const char*,...);
static int (*random_fn)(void);
static char *(*last_fn)(const char*,int);
#define memcpy copy_fn
#define strlen length_fn
#define strncasecmp casecmp_fn
#define sscanf scan_fn
#define snprintf format_fn
#define rand random_fn
#define strrchr last_fn
static char patchID[9]="GMSE01";
static int jingle,useCustom;
static unsigned char playlog_name[64];
static void DCFlushRange(void *p,size_t n) {(void)p;(void)n;}
static void VIDEO_SetTrapFilter(int x) {(void)x;}
static void VIWriteI2CRegister8(int x,int y) {(void)x;(void)y;}
static int gprintf(const char *s,...) {(void)s;return 0;}
static void ConvertName(unsigned char *p,int n,u32 x) {p[n]=x>>24;p[n+1]=x>>16;p[n+2]=x>>8;p[n+3]=x;}
typedef int FRESULT;
typedef unsigned int UINT;
typedef struct {struct {unsigned long long objsize;} obj; int index;} FIL;
struct File {const unsigned char *data;unsigned int bytes;unsigned long long reported;int open,read,close,shortRead;};
static struct File files[3];
static int reads,opens,allocationFailed;
static unsigned char scratch[NIN_MEM2_FILE_PATCH_SIZE+1];
static void *memalign(int a,size_t n) {(void)a;return allocationFailed||n>sizeof(scratch)?NULL:scratch;}
static void free(void *p) {(void)p;}
static int f_open_char(FIL *f,const char *path,int flags) {
 (void)flags; ++opens;f->index=path[1]=='a'?2:(strrchr(path,'.')[1]=='b'?0:1);
 f->obj.objsize=files[f->index].reported;return files[f->index].open;
}
static int f_read(FIL *f,void *out,UINT n,UINT *got) {
 struct File *x=&files[f->index];++reads;*got=x->bytes<n?x->bytes:n;
 if(x->shortRead&&*got)--*got;if(*got)memcpy(out,x->data,*got);return x->read;
}
static int f_close(FIL *f) {return files[f->index].close;}
static bool BuildSiblingPath(char *out,size_t n,const char *game,const char *file) {
 (void)n;if(!game)return false;memcpy(out,"/game/",6);memcpy(out+6,file,strlen(file)+1);return true;
}
static bool BuildDevicePath(char *out,size_t n,const char *p,const char *s) {
 (void)n;(void)s;memcpy(out,p,strlen(p)+1);return true;
}
"""
        prelude += "struct Config {const char *GamePath;" + "".join(
            "u32 " + field + ";" for field in fields) + "};\nstatic struct Config config;\nstatic struct Config *ncfg=&config;\n"
        prelude += "\n".join(f"#define {name} (1u<<{i})" for i, name in enumerate(macros)) + "\n"
        exports = r"""
API void init(void **p) {
 copy_fn=p[0];length_fn=p[1];casecmp_fn=p[2];scan_fn=p[3];format_fn=p[4];random_fn=p[5];last_fn=p[6];
}
API void reset(void) {
 unsigned i;for(i=0;i<3;++i){files[i].open=FR_NO_FILE;files[i].read=files[i].close=files[i].shortRead=0;files[i].bytes=0;files[i].reported=0;}
 for(i=0;i<NIN_MEM2_FILE_PATCH_SIZE+32;++i)((volatile u8*)NIN_MEM2_FILE_PATCH_PPC_BASE)[i]=0xA5;
 for(i=0;i<sizeof(scratch);++i)scratch[i]=0xA5;
 reads=opens=allocationFailed=0;patchOnce=false;config.GamePath="/game/game.iso";
}
API void file(int index,const void *data,u32 bytes,unsigned long long reported,int open,int read,int close,int shortRead) {
 struct File *f=&files[index];f->data=data;f->bytes=bytes;f->reported=reported;f->open=open;f->read=read;f->close=close;f->shortRead=shortRead;
}
API const char *load(void) {return SetFilePatches();}
API int parse(unsigned char *data,unsigned size) {return app_loadgameconfig(data,size);}
API int intact(void) {unsigned i;for(i=68;i<100;++i)if(((volatile u8*)NIN_MEM2_FILE_PATCH_PPC_BASE)[i]!=0xA5)return 0;return 1;}
API unsigned count(void) {return *(vu32*)NIN_MEM2_FILE_PATCH_PPC_BASE;}
API unsigned calls(void) {return reads;}
API unsigned word(unsigned i) {return ((vu32*)NIN_MEM2_FILE_PATCH_PPC_BASE)[i];}
API void failAllocation(void) {allocationFailed=1;}
"""
        (work / "fixture.c").write_text(prelude + production + exports)
        subprocess.run([str(clang), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-O1", "-nostdlib", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        "-Wno-int-to-void-pointer-cast", str(work / "fixture.c"),
                        "-o", str(work / "fixture.dll")], check=True, capture_output=True)
        kernel = ctypes.windll.kernel32
        kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
        kernel.VirtualAlloc.restype = ctypes.c_void_p
        kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
        for address in (0x91900000, 0x932F0000):
            allocation = kernel.VirtualAlloc(address, 65536, 0x3000, 0x04)
            if allocation != address:
                raise RuntimeError("Native fixture address unavailable")
            cls.addClassCleanup(lambda a=address: kernel.VirtualFree(a, 0, 0x8000))
        cls.dll = ctypes.CDLL(str(work / "fixture.dll"))
        cls.addClassCleanup(lambda: kernel.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))
        crt = ctypes.CDLL("msvcrt.dll")
        cls.crt = crt
        names = ["memcpy", "strlen", "_strnicmp", "sscanf", "_snprintf", "rand", "strrchr"]
        api = (ctypes.c_void_p * len(names))(*(ctypes.cast(getattr(crt, n), ctypes.c_void_p).value for n in names))
        cls.dll.init(api)
        cls.dll.file.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        cls.dll.load.restype = ctypes.c_char_p
        cls.dll.parse.argtypes = [ctypes.c_void_p, ctypes.c_uint]

    def setUp(self):
        self.dll.reset()
        self.buffers = []

    def add(self, index, data=b"", reported=None, open=0, read=0, close=0, short=0):
        buffer = ctypes.create_string_buffer(data)
        self.buffers.append(buffer)
        self.dll.file(index, buffer, len(data), len(data) if reported is None else reported,
                      open, read, close, short)

    def check_failure(self, expected):
        message = self.dll.load()
        self.assertIsNotNone(message)
        self.assertIn(expected, message)
        self.assertEqual(self.dll.count(), 0)
        self.assertTrue(self.dll.intact())

    def test_absent_files_remain_successful_without_reads(self):
        self.assertIsNone(self.dll.load())
        self.assertEqual(self.dll.calls(), 0)
        self.assertEqual(self.dll.count(), 0)

    def test_valid_binary_precedes_local_text(self):
        self.add(0, struct.pack("=3I", 1, 0x1234, 0x5678))
        self.add(1, b"DEFAULT:\npoke(8888,9999)")
        self.assertIsNone(self.dll.load())
        self.assertEqual(self.dll.count(), 1)
        self.assertEqual(self.dll.word(1), 0x1234)
        self.assertEqual(self.dll.calls(), 1)

    def test_binary_exact_limit_and_oversize_are_distinct(self):
        self.add(0, struct.pack("=17I", 8, *([0, 1] * 8)))
        self.assertIsNone(self.dll.load())
        self.assertEqual(self.dll.count(), 8)
        self.assertTrue(self.dll.intact())
        self.setUp()
        self.add(0, reported=69)
        self.check_failure(b"file too large")
        self.assertEqual(self.dll.calls(), 0)

    def test_bad_binary_header_count_and_conditional_are_rejected(self):
        for data, message in [(b"123", b"invalid patch header"),
                              (struct.pack("=I", 1), b"invalid patch record count"),
                              (struct.pack("=3I", 1, 1, 0), b"incomplete conditional")]:
            self.setUp(); self.add(0, data); self.check_failure(message)

    def test_io_and_allocation_failures_propagate(self):
        for kwargs in [dict(open=1), dict(read=1), dict(close=1), dict(short=1)]:
            self.setUp(); self.add(0, struct.pack("=I", 0), **kwargs)
            self.check_failure(b"could not read")
        self.setUp(); self.add(1, b"DEFAULT:\npoke(1234,5678)")
        self.dll.failAllocation(); self.check_failure(b"not enough buffer memory")

    def test_text_without_final_newline_and_filtered_bytes(self):
        self.add(1, b"\xffDEFAULT:\npoke(1234,5678)")
        self.assertIsNone(self.dll.load())
        self.assertEqual(self.dll.count(), 1)
        self.assertEqual(self.dll.word(1), 0x1234)
        self.assertEqual(self.dll.word(2), 0x5678)
        self.assertTrue(self.dll.intact())

    def test_text_and_global_input_limits(self):
        self.add(1, reported=69); self.check_failure(b"file too large")
        self.setUp(); self.add(2, reported=1024*1024)
        self.check_failure(b"file too large")

    def test_generated_output_limit_checks_whole_conditional(self):
        for prefix, suffix, expected in [
            (8, "", True), (9, "", False),
            (6, "pokeifequal(0,0,0,0)\n", True),
            (7, "pokeifequal(0,0,0,0)\n", False),
            (8, "rand(0,0,1,0,0)\n", False),
            (8, "noLoadStub(1)\n", False),
        ]:
            self.setUp()
            data = ("DEFAULT:\n" + "poke(0,0)\n" * prefix + suffix).encode()
            buffer = ctypes.create_string_buffer(data)
            self.assertEqual(bool(self.dll.parse(buffer, len(data))), expected)
            self.assertTrue(self.dll.intact())
            self.assertEqual(self.dll.count(), 8 if expected else 0)


if __name__ == "__main__":
    unittest.main()
