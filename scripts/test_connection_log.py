"""Persist the production ARM connection log through the bundled FatFs."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConnectionLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled Windows compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-log-fatfs-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        for name, content in {
            'stdint.h': 'typedef unsigned char uint8_t;typedef unsigned short uint16_t;typedef unsigned int uint32_t;',
            'stdbool.h': '#define bool _Bool\n#define true 1\n#define false 0',
            'stddef.h': 'typedef __SIZE_TYPE__ size_t;\n#define NULL ((void*)0)',
            'string.h': 'void *memcpy(void*,const void*,__SIZE_TYPE__);',
            'stdarg.h': 'typedef __builtin_va_list va_list;\n#define va_start __builtin_va_start\n#define va_end __builtin_va_end\n#define va_arg __builtin_va_arg',
        }.items():
            (folder / name).write_text('#pragma once\n' + content)
        production = (ROOT / 'launcher/kernel/MoonshineNetLog.c').read_text()
        production = production.replace('static void emit(', 'static void logEmit(').replace('emit(out,', 'logEmit(out,')
        for header in ('"SusamuneCfg.h"', '<stdio.h>', '<string.h>'):
            production = production.replace('#include ' + header, '')
        source = folder / 'test.c'
        source.write_text(r'''
#include "data_migration_fixture.h"
#include <stdarg.h>
static unsigned ticks, failWrite;
#define HW_TIMER 0
#define read32(x) ticks
static const char *SusamuneCfgStoragePrefix(void){return "sd:/Moonshine data";}
static FRESULT logWrite(FIL*f,const void*p,UINT n,UINT*w){return failWrite?FR_DISK_ERR:f_write(f,p,n,w);}
#define f_write logWrite
''' + production + r'''
API void beginLog(void){
 sUsed=sWritten=sOmitted=sSampleAt=sFlushAt=sEpoch=sState=sFlushMs=0;sStarted=sFailed=sCreated=0;
 ticks=1;failWrite=0;memset(sStreams,0,sizeof(sStreams));
 f_mkdir_char("sd:/Moonshine data");
}
API void sample(unsigned seconds){struct MoonshineNetStatus s={0};ticks=seconds*1898437u;
 s.epoch=1;s.state=MOONSHINE_NET_READY;s.sent=50;s.received=40;
 MoonshineNetLogSample(&s,1,2,30);
}
API void capture(unsigned seq,unsigned kind){
 unsigned char data[80]={0};MSRHeader h={0};TWLiveEndpoint e={{127,0,0,1},99,0};
 h.kind=kind;h.sequence=seq;h.payloadBytes=48;h.timing=1;
 MSREncodeHeader(data,sizeof(data),&h);
 if(kind==MSR_HELLO)memcpy(data+32,"PRIVATE-ROOM-CODE",17);
 MoonshineNetLogPacket(0,&e,data,sizeof(data));
}
API void flushLog(unsigned fail){failWrite=fail;MoonshineNetLogService();}
API unsigned idleLog(unsigned seconds){ticks+=seconds*1898437u;return MoonshineNetLogPending();}
API unsigned stateLog(unsigned which){return which==0?sUsed:which==1?sFailed:which==2?sWritten:sOmitted;}
API const char *pathLog(void){return sPath;}
''')
        fatfs = ROOT / 'launcher/fatfs'
        library = folder / 'test.dll'
        result = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-U_WIN32',
            '-D__PPC__', '-shared', '-nostdlib', '-fno-builtin', '-mno-stack-arg-probe', '-O2',
            '-fuse-ld=lld', '-Wl,/noentry', '-I', str(folder), '-I', str(fatfs),
            '-I', str(ROOT / 'scripts'), '-I', str(ROOT / 'include'), '-I', str(ROOT / 'launcher/kernel'),
            str(source), str(fatfs / 'ff.c'), str(fatfs / 'ff_utf8.c'), str(fatfs / 'option/ccsbcs.c'),
            '-o', str(library)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.pathLog.restype = C.c_char_p
        cls.lib.get.argtypes = [C.c_char_p, C.c_void_p, C.c_uint]

    def setUp(self):
        self.assertEqual(self.lib.reset(), 0)
        self.lib.beginLog()

    def read(self, path):
        buf = C.create_string_buffer(16384)
        size = self.lib.get(path, buf, len(buf))
        self.assertGreaterEqual(size, 0)
        return buf.raw[:size]

    def test_capture_is_buffered_then_persisted_without_secrets(self):
        self.lib.sample(1)
        self.lib.capture(1, 1)
        for seq in range(1, 51):
            self.lib.capture(seq, 3)
        self.lib.sample(2)
        self.assertEqual(self.lib.stateLog(2), 0)
        self.lib.sample(7)
        self.lib.flushLog(0)
        saved = self.read(self.lib.pathLog())
        self.assertIn(b'count=50', saved)
        self.assertIn(b'ppc_rx=30', saved)
        self.assertNotIn(b'PRIVATE', saved)
        self.assertEqual(self.lib.stateLog(1), 0)

    def test_flushing_does_not_keep_writing_after_session_ends(self):
        self.lib.sample(1)
        self.lib.sample(7)
        self.lib.flushLog(0)
        self.assertEqual(self.lib.stateLog(0), 0)
        self.assertEqual(self.lib.idleLog(10), 0)
        self.assertEqual(self.lib.stateLog(1), 0)

    def test_next_boot_preserves_prior_log_and_write_failure_stops_only_logger(self):
        self.lib.sample(1)
        self.lib.sample(7)
        self.lib.flushLog(0)
        original_path = self.lib.pathLog()
        original = self.read(original_path)
        self.lib.beginLog()
        self.lib.sample(1)
        self.lib.sample(7)
        self.lib.flushLog(0)
        self.assertNotEqual(original_path, self.lib.pathLog())
        self.assertEqual(original, self.read(original_path))
        self.lib.sample(13)
        self.lib.flushLog(1)
        self.assertEqual(self.lib.stateLog(1), 1)
        self.assertEqual(original, self.read(original_path))


if __name__ == '__main__':
    unittest.main()
