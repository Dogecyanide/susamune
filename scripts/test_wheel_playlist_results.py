"""Execute wheel destination resolution and final playlist rendering."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_iling_attempt_lifecycle import function

ROOT = Path(__file__).resolve().parents[1]


class WheelPlaylistResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-wheel-results-")
        cls.addClassCleanup(cls.temp.cleanup)
        wheel = (ROOT / "src/warp_wheel.cpp").read_text()
        loader = (ROOT / "src/stage_loader.cpp").read_text()
        code = r'''
using u8=unsigned char;using s8=signed char;using u16=unsigned short;
using u32=unsigned int;using u64=unsigned long long;using s32=int;
int (*snprintf)(char*,u64,const char*,...);
int strlen(const char *p){int n=0;while(p[n])++n;return n;}
char *strcpy(char *out,const char *in){char *p=out;while((*p++=*in++)){}return out;}
int strcmp(const char *a,const char *b){while(*a&&*a==*b){++a;++b;}return *a-*b;}
namespace LevelWarp {struct Dest {enum{POST_CORONA=0x80};u8 area,episode,gameInt3;};}
struct TGameSequence {enum{AREA_PINNABEACH=5};};
struct Slot {u8 slot,area,episode,gameInt3;};struct Wheel {u8 first,count;};
struct Root {u8 episodeArea;s8 mainWheel,subWheel;};
const int kNumSlots=9;int sRoot;bool sSubMode;
'''
        for name in ("kPinnaPark", "kSlots", "kWheels", "kRoot"):
            code += re.search(r"(?:constexpr|const) [^\n]*\b" + name +
                              r"\[.*?\};", wheel, re.S).group(0) + "\n"
        for name in ("currentWheel", "currentWheelData", "findSlot", "slotDest"):
            code += function(wheel, name) + "\n"
        code += r'''
struct Color {Color(int,int,int,int){}};
struct Text {char value[96];int x,y;};Text texts[40];int textCount;
struct Menu {
 static int textWidth(const char *p,int size){return (int)strlen(p)*size/2;}
 void fillBox(int,int,int,int,Color){}
 void drawText(const char *p,int x,int y,int,int,Color){Text &t=texts[textCount++];strcpy(t.value,p);t.x=x;t.y=y;}
};
namespace StageLoader {enum{MODE_LOADER,MODE_STREAKING,BUILTIN_PLAYLIST_COUNT=3};
const char *builtinPlaylistName(int){return "Test playlist";}}
namespace ILing {const char *label(int){return "Test level";}
void formatTime(int,char *p,u32 n){snprintf(p,n,"target");}}
constexpr int SUSAMUNE_STAGE_PLAYLIST_TOTAL_COUNT=10;
constexpr u32 SUSAMUNE_STAGE_PLAYLIST_BEST_UNSET=0xffffffffu;
const char kCompletedTotalLabel[]="Total time";
struct Runtime {
u64 totalObservedActiveQf,completedQfTotal;
u32 attempts,eligibleCompletes,priorPlaylistBestQf,finalPlaylistQf;
int mode,lastEntry,activePlaylistId,activeCount,targetQf,progress,goal;
bool playlistTimeOverflow,playlistPbEligible;
}sRuntime;bool sPlaylistsAvailable;
'''
        for name in ("formatDuration", "drawModalRow", "drawModalRowColor",
                     "completionPercent", "formatPlaylistDelta", "drawFinalModal"):
            code += function(loader, name) + "\n"
        code += r'''
#define API extern "C" __declspec(dllexport)
API void bindPrintf(void *p){snprintf=(int(*)(char*,u64,const char*,...))p;}
API int destination(int root,int sub,int slot){sRoot=root;sSubMode=sub;
 LevelWarp::Dest out{};if(!slotDest(slot,&out))return -1;
 return (out.area<<16)|(out.episode<<8)|out.gameInt3;}
API const char *row(int mode,const char *label){textCount=0;sRuntime={};
 sRuntime.mode=mode;sRuntime.totalObservedActiveQf=3600;sRuntime.completedQfTotal=1200;
 sRuntime.attempts=4;sRuntime.eligibleCompletes=2;sRuntime.targetQf=-1;
 sRuntime.activeCount=sRuntime.progress=2;sRuntime.goal=2;
 sRuntime.priorPlaylistBestQf=SUSAMUNE_STAGE_PLAYLIST_BEST_UNSET;
 Menu m;drawFinalModal(&m);
 for(int i=0;i+1<textCount;++i)
   if(texts[i].x==108&&!strcmp(texts[i].value,label)&&texts[i+1].y==texts[i].y)
     return texts[i+1].value;
 return "ABSENT";}
'''
        folder = Path(cls.temp.name)
        source, library = folder / "test.cpp", folder / "test.dll"
        source.write_text(code)
        subprocess.run([str(ROOT / "toolchain/clang++.exe"),
                        "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib",
                        "-fuse-ld=lld", "-Wl,/noentry", "-O2", "-std=c++17",
                        str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.bindPrintf.argtypes = [C.c_void_p]
        cls.lib.bindPrintf(C.cast(C.CDLL("msvcrt")._snprintf, C.c_void_p))
        cls.lib.row.argtypes = [C.c_int, C.c_char_p]
        cls.lib.row.restype = C.c_char_p

    def test_pinna_matches_il_episode_starts(self):
        entries = (ROOT / "src/iling_entries.inc").read_text()
        for episode in range(1, 9):
            row = re.search(r'SHINE(?:_FULL|_CLEAR)?\("Pinna ' + str(episode) +
                            r'(?: \(Full\))?", ([\dxA-F]+), (\d+), (\d+),', entries)
            self.assertIsNotNone(row)
            area, scene, parent = (int(x, 0) for x in row.groups())
            self.assertEqual(self.lib.destination(3, 0, episode - 1),
                             (area << 16) | (scene << 8) | parent)

    def test_other_generated_episodes_and_pinna_secrets(self):
        for root, area in ((0, 2), (1, 3), (2, 4), (4, 6), (5, 8), (6, 9)):
            for episode in range(8):
                self.assertEqual(self.lib.destination(root, 0, episode),
                                 (area << 16) | (episode << 8) | episode)
        for slot, area, episode, parent in ((0, 0x3a, 1, 0), (1, 0x32, 0, 1),
                                             (5, 0x29, 0, 5), (7, 0x3a, 0, 7)):
            self.assertEqual(self.lib.destination(3, 1, slot),
                             (area << 16) | (episode << 8) | parent)
        self.assertEqual(self.lib.destination(3, 1, 2), -1)

    def test_completed_total_is_distinct_from_active_playlist_time(self):
        self.assertEqual(self.lib.row(0, b"Total time"), b"0:00:10.010")
        self.assertEqual(self.lib.row(0, b"Playlist time"), b"0:00:30.030")
        self.assertEqual(self.lib.row(0, b"Golds"), b"ABSENT")
        self.assertEqual(self.lib.row(1, b"Average time"), b"0:00:05.005")
        self.assertEqual(self.lib.row(1, b"Golds"), b"--")


if __name__ == "__main__":
    unittest.main()
