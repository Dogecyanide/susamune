"""Execute the IL recorder observer without altering the attempt or eligibility."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_iling_attempt_lifecycle import function

ROOT = Path(__file__).resolve().parents[1]


class ILTraceContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-il-trace-context-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT/"src/iling.cpp").read_text()
        code = r"""
#include "susamune/iling.hxx"
extern "C" void *memcpy(void *d,const void *s,__SIZE_TYPE__ n) {
volatile unsigned char *out=(volatile unsigned char*)d;
const volatile unsigned char *in=(const volatile unsigned char*)s;
while(n--)*out++=*in++;return d;}
namespace LevelWarp {struct Dest{u8 area,episode,gameInt3;};}
"""
        for name in ("OverlayFlag", "AttemptState"):
            code += re.search(r"struct "+name+r" \{.*?\n\};", source, re.S).group(0)+"\n"
        code = code.replace("struct AttemptState", "const int kOverlayFlagCount=2;\nstruct AttemptState")
        code += source[source.index("enum RejectionCause {"):source.index("struct Entry {")]
        count = re.search(r'static_assert\(kEntryCount == (\d+),', source).group(1)
        code += "const int kEntryCount="+count+";\n"
        code += r"""
struct Entry {LevelWarp::Dest start;} kEntries[kEntryCount];
static AttemptState sAttemptState;
"""
        code += source[source.index("#define sRunning "):source.index("#define sCustomPbProfileNames ")]
        code += r"""
static u8 sActivePbProfile;
static bool recordingSetting,alternate;
enum{SETTING_ILING_RECORDING};
struct Settings {bool getBool(int)const{return recordingSetting;}}gSettings;
namespace StageLoader {bool fastAnyStart(int){return alternate;}}
"""
        for name in ("validEntry", "sameDest", "sessionStartChanged"):
            code += function(source, name)+"\n"
        code += "namespace ILing {\n"+function(source, "rejectionCause")+"\n"
        code += function(source, "captureTraceContext")+"\n}\n"
        code += r"""
#define API extern "C" __declspec(dllexport)
API void configure(unsigned profile,int entry,unsigned bits,unsigned start,unsigned assists,unsigned cause,unsigned different,unsigned defaultStart) {
 sAttemptState={};sActivePbProfile=profile;recordingSetting=(bits&128)!=0;alternate=different;
 sRunning=(bits&1)!=0;sAttemptReady=(bits&2)!=0;sAwaitingStageSetup=(bits&4)!=0;
 sRecordsEligible=(bits&8)!=0;sSecretOnly=(bits&16)!=0;sChildRetryContinuation=(bits&32)!=0;
 sAttemptStart={(u8)(start>>24),(u8)(start>>16),(u8)start};
 sSelectedEntry=entry;sAssistReasons=assists;sRejectionCause=cause;sAttemptSerial=0x12345678;
 if(validEntry(entry))kEntries[entry].start={(u8)(defaultStart>>24),(u8)(defaultStart>>16),(u8)defaultStart};
}
API int observe(unsigned out[6]) {
 const AttemptState before=sAttemptState;const unsigned profile=sActivePbProfile;
 const bool oldSetting=recordingSetting,oldAlternate=alternate;
 ILing::captureTraceContext(out);
 const unsigned char*a=(const unsigned char*)&before,*b=(const unsigned char*)&sAttemptState;
 for(unsigned i=0;i<sizeof(before);++i)if(a[i]!=b[i])return 0;
 return profile==sActivePbProfile&&oldSetting==recordingSetting&&oldAlternate==alternate;
}
"""
        cls.libraries = []
        for trace in (0,1):
            path = Path(cls.temp.name)/f"context{trace}.cpp"
            path.write_text(code)
            result = subprocess.run([str(ROOT/"toolchain/clang++.exe"),
                "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib", "-O2",
                "-fuse-ld=lld", "-Wl,/noentry", f"-DMOONSHINE_GHOST_TRACE={trace}",
                "-I",str(ROOT/"include"),str(path),"-o",str(path.with_suffix(".dll"))],
                capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError(result.stdout+result.stderr)
            lib=C.CDLL(str(path.with_suffix(".dll")))
            cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
            lib.configure.argtypes=[C.c_uint,C.c_int]+[C.c_uint]*6
            lib.observe.argtypes=[C.POINTER(C.c_uint)]
            cls.libraries.append(lib)

    def capture(self, *,profile=0,entry=-1,flags=0,start=0,assists=0,cause=0,different=False,default=0):
        results=[]
        for lib in self.libraries:
            lib.configure(profile,entry,flags,start,assists,cause,different,default)
            out=(C.c_uint*6)(*[0xdeadbeef]*6)
            self.assertEqual(lib.observe(out),1,"capture mutated the live attempt")
            results.append(tuple(out))
        self.assertEqual(results[0],results[1],"trace compile switch changed observer availability or values")
        return results[0]

    def test_initial_inactive_observation_does_not_invent_an_entry(self):
        self.assertEqual(self.capture(),(0,0,0,0,0,0))

    def test_inactive_stale_attempt_fields_are_masked(self):
        self.assertEqual(self.capture(profile=4,entry=26,flags=254,start=0x20000003,
                                      assists=15,cause=9,different=True),(4,0,128,0,0,0))

    def test_raw_hoverless_profile_is_four_and_is_not_the_manifest_namespace(self):
        for profile in range(5):
            self.assertEqual(self.capture(profile=profile)[0],profile)

    def test_natural_live_attempt_has_no_selected_entry(self):
        self.assertEqual(self.capture(entry=-1,flags=139,start=0x06030003),
                         (0,0,139,0x06030003,0,0))

    def test_selected_secret_waiting_for_setup_is_distinct_from_ready(self):
        self.assertEqual(self.capture(entry=26,flags=149,start=0x20000003),
                         (0,27,149,0x20000003,0,0))

    def test_selected_entry_zero_and_last_entry_have_unambiguous_encoding(self):
        for entry in (0,132):
            self.assertEqual(self.capture(entry=entry,flags=1)[1],entry+1)
        for entry in (-1,133,500):
            self.assertEqual(self.capture(entry=entry,flags=1)[1],0)

    def test_exact_start_keeps_plaza_marker_and_leaves_middle_byte_zero(self):
        self.assertEqual(self.capture(flags=1,start=0x0107ff82)[3],0x01070082)

    def test_child_retry_reason_overrides_different_start_reason(self):
        result=self.capture(entry=2,flags=35,start=0x06030003,different=True)
        self.assertEqual((result[2],result[5]),(99,7))

    def test_alternate_start_uses_real_session_start_predicate(self):
        changed=self.capture(entry=2,flags=3,start=0x06030003,different=True)
        self.assertEqual((changed[2],changed[5]),(67,8))
        same=self.capture(entry=2,flags=3,start=0x06030003,default=0x06030003,different=True)
        self.assertEqual((same[2],same[5]),(3,0))

    def test_assist_reason_inventory_is_retained_without_changing_eligibility(self):
        self.assertEqual(self.capture(entry=4,flags=131,assists=10,cause=4)[4:],(10,4))
        self.assertEqual(self.capture(entry=4,flags=139,assists=0,cause=0)[2],139)

    def test_pb_recording_configuration_is_separate_from_live_eligibility(self):
        self.assertEqual(self.capture(flags=11)[2],11)
        self.assertEqual(self.capture(flags=139)[2],139)


if __name__=="__main__":
    unittest.main()
