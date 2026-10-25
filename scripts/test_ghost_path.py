"""Execute production Watch path clipping, work bounds and scene ownership."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_ghost_tas_clock import function

ROOT = Path(__file__).resolve().parents[1]


class GhostPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ghost-path-')
        cls.addClassCleanup(cls.temp.cleanup)
        path = (ROOT / 'src/ghost_path.cpp').read_text()
        ghost = (ROOT / 'src/ghost.cpp').read_text()
        code = r'''
#include "susamune/ghost_format.h"
using u8=unsigned char;using u16=unsigned short;using u32=unsigned;using s16=short;using s32=int;using f32=float;
using Mtx=float[3][4];using Mtx44=float[4][4];
extern "C" int _fltused=0;
extern "C" void *memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
namespace JUtility {struct TColor {u8 r,g,b,a;TColor(u8 r,u8 g,u8 b,u8 a):r(r),g(g),b(b),a(a){}};}
unsigned calls,bad,colors[2];s16 ends[4];bool shown,matricesReady;
class Menu {public:
 bool shown(){return ::shown;}
 void strokePoly(const s16*p,int n,JUtility::TColor c){
  if(n!=2)++bad;for(int i=0;i<4;++i){if(p[i]<0||p[i]>(i%2?480:640))++bad;ends[i]=p[i];}
  ++calls;++colors[c.r==255];
 }
 void drawText(const char*,int,int,int,int,JUtility::TColor){}
} menu;
namespace GhostCamera {bool renderMatrices(Mtx v,Mtx44 p){
 if(!matricesReady)return false;
 memset(v,0,sizeof(Mtx));memset(p,0,sizeof(Mtx44));v[0][0]=v[1][1]=v[2][2]=1;
 p[0][0]=p[1][1]=1;p[2][2]=-0.001001001f;p[2][3]=-1.001001f;p[3][2]=-1;
 return true;
}}
'''
        code += '\n'.join(line for line in path.splitlines()
                          if not line.startswith('#include'))
        code += r'''
using Sample=SusamuneGhostPoseSample;using Segment=SusamuneGhostSegment;
struct Track {Sample*samples;Segment*segments;unsigned count,segmentCount;bool valid;};
Sample poses[26974];Segment scenes[2];Track sPlayback,sObserverSecondary;
bool sLiveRouteValid,sObserverStageReady,watch,loading,two,enabled,display;
u8 sLiveArea=2,sLiveEpisode=0,sLiveRouteParentArea=255,sLiveRouteFlags=0;s32 sLiveParentEpisode=0;
u16 sObserverPrimarySegment,sObserverSecondarySegment;
bool sGhostVisible,sSecondaryGhostVisible;int sGhostPosition,sSecondaryGhostPosition;
enum {SETTING_GHOST_DISPLAY,SETTING_GHOST_PATH,SETTING_GHOST_OPACITY};
struct Settings {bool getBool(int id){return id==SETTING_GHOST_PATH?enabled:display;}u8 get(int){return 0;}}gSettings;
bool observerRunning(){return watch;}bool observerLoading(){return loading;}bool observerHasTwo(){return two;}
namespace GhostScrub {void drawStatus(Menu*){}}
namespace GhostModel {bool submitted(bool){return true;}}
void drawMarker(Menu*,int,bool,u8){}bool playbackIsTas(bool=false){return false;}
'''
        for signature in ('bool segmentRouteEquals(', 'void drawObserverPath(', 'void draw(Menu *menu)'):
            code += function(ghost, signature)
        code += r'''
#define API extern "C" __declspec(dllexport)
void put(u8*p,int n){p[0]=(u8)(n>>16);p[1]=(u8)(n>>8);p[2]=(u8)n;}
API void reset(unsigned count){
 calls=bad=colors[0]=colors[1]=0;shown=loading=two=false;
 watch=enabled=display=matricesReady=sLiveRouteValid=sObserverStageReady=true;
 sObserverPrimarySegment=sObserverSecondarySegment=0;
 scenes[0]={0,count,0,100,0,2,0,255,0,0,0};scenes[1]=scenes[0];
 sPlayback={poses,scenes,count,1,true};sObserverSecondary={poses,scenes+1,count,1,true};
 for(unsigned i=0;i<count&&i<26974;++i){put(poses[i].x,(int)i%800-400);put(poses[i].y,-64);put(poses[i].z,-800);}
}
API void option(unsigned kind,unsigned value){switch(kind){case 0:watch=value;break;case 1:enabled=value;break;
 case 2:loading=value;break;case 3:sObserverStageReady=value;break;case 4:shown=value;break;
 case 5:two=value;break;case 6:scenes[0].routeArea=value;break;case 7:sObserverPrimarySegment=value;break;
 case 8:matricesReady=value;break;case 9:display=value;break;case 10:sLiveRouteValid=value;break;
 case 11:scenes[0].firstSample=value;break;case 12:scenes[0].sampleCount=value;break;}}
API void pose(unsigned i,int x,int y,int z){put(poses[i].x,x*8);put(poses[i].y,y*8);put(poses[i].z,z*8);}
API void tick(){calls=bad=colors[0]=colors[1]=0;draw(&menu);}
API unsigned get(unsigned field){return field==0?calls:field==1?bad:field==2?colors[0]:colors[1];}
API int endpoint(unsigned field){return ends[field];}
'''
        cpp = Path(cls.temp.name) / 'path.cpp'
        cpp.write_text(code)
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'),
            '--target=x86_64-pc-windows-msvc', '-shared', '-nostdlib', '-fuse-ld=lld',
            '-Wl,/noentry', '-fno-builtin', '-O2', '-ffast-math', '-I', str(ROOT / 'include'),
            str(cpp), '-o', str(cpp.with_suffix('.dll'))], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(cpp.with_suffix('.dll')))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_maximum_legacy_and_current_tracks_bound_two_distinct_paths(self):
        for count in (2, 97, 17983, 26974):
            self.lib.reset(count)
            self.lib.option(5, 1)
            self.lib.tick()
            self.assertEqual([self.lib.get(i) for i in range(4)],
                             [2 * min(count - 1, 96), 0, min(count - 1, 96), min(count - 1, 96)])

    def test_path_is_watch_only_and_requires_ready_current_scene(self):
        for kind, value in ((0, 0), (1, 0), (2, 1), (3, 0), (4, 1), (6, 3),
                            (7, 1), (8, 0), (9, 0), (10, 0), (11, 2), (12, 3)):
            with self.subTest(kind=kind):
                self.lib.reset(2)
                self.lib.option(kind, value)
                self.lib.tick()
                self.assertEqual(self.lib.get(0), 0)

    def test_clips_offscreen_and_camera_plane_without_screen_overflow(self):
        cases = [((-200, -8, -100), (200, -8, -100), 1),
                 ((0, -8, 10), (0, -8, -100), 1),
                 ((0, -8, 10), (10, -8, 20), 0),
                 ((200, -8, -100), (300, -8, -100), 0),
                 ((0, -8, -2000), (10, -8, -2100), 0)]
        for a, b, expected in cases:
            self.lib.reset(2)
            self.lib.pose(0, *a)
            self.lib.pose(1, *b)
            self.lib.tick()
            self.assertEqual([self.lib.get(i) for i in range(2)], [expected, 0])

    def test_teleport_jump_and_empty_segment_do_not_draw(self):
        self.lib.reset(2)
        self.lib.pose(0, -900, -8, -100)
        self.lib.pose(1, 900, -8, -100)
        self.lib.tick()
        self.assertEqual(self.lib.get(0), 0)
        for count in (0, 1):
            self.lib.reset(count)
            self.lib.tick()
            self.assertEqual(self.lib.get(0), 0)


if __name__ == '__main__':
    unittest.main()
