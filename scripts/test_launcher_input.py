"""Check the adopted upstream input contract and redraw/repeat integration."""
import ctypes as C,hashlib,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED='b26d7eb0867df1d58be468059138d500babb26a12308a55a5a8e4a9282e5db4a'
class LauncherInputTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='stock-pad-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  src=(ROOT/'launcher/loader/source/FPad.c').read_text(encoding='utf-8')
  cls.body=src[src.index('void FPAD_Update('):src.index('inline void Screenshot')]
  macros=src[src.index('#define LEFT_STICK'):src.index('static u32 (*const PADRead)')]
  body=cls.body.replace('PADRead(0);','HIDRead(0);').replace('(PADStatus*)(0x93003100)','HidPads').replace('(*(vu32*)0xCD8000C8)','Power')
  menu=(ROOT/'launcher/loader/source/SusamuneMenu.c').read_text(encoding='utf-8');repeat=menu[menu.index('/** Key repeat,'):menu.index('/** Devices **/')]
  pre=r"""
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stddef.h>
typedef uint32_t u32;typedef uint8_t u8;typedef int8_t s8;
#define WPAD_MAX_WIIMOTES 4
#define PAD_CHANMAX 4
#define WPAD_ERR_NONE 0
#define WPAD_EXP_CLASSIC 2
#define DELAY_START 900
#define PAD_BUTTON_LEFT 1
#define PAD_BUTTON_RIGHT 2
#define PAD_BUTTON_DOWN 4
#define PAD_BUTTON_UP 8
#define PAD_BUTTON_A 256
#define PAD_BUTTON_B 512
#define PAD_BUTTON_X 1024
#define PAD_BUTTON_Y 2048
#define PAD_BUTTON_START 4096
struct WUPCData {u32 button;int yAxisL,xAxisL;};
typedef struct {int err;u32 btns_d,btns_h;struct {int type;struct {struct {float mag,ang;} ljs;}classic;}exp;} WPADData;
struct WiiDRCData {u32 button;};
typedef struct {u32 button;s8 stickY,stickX;} PADStatus;
static PADStatus HidPads[4];static WPADData Wpad[4];static struct WiiDRCData Drc;
static u32 WPAD_Pressed,WiiDRC_Pressed,PAD_Pressed,Repeat,SpeedX,Power,Held,Down,Scans;
static s8 PAD_Stick_Y,PAD_Stick_X,X,Y;static bool SLock;
static void WPAD_ScanPads(void){}static struct WUPCData*WUPC_Data(int i){return NULL;}
static WPADData*WPAD_Data(int i){return &Wpad[i];}
static bool WiiDRC_Inited(void){return false;}static bool WiiDRC_Connected(void){return false;}
static void WiiDRC_ScanPads(void){}static const struct WiiDRCData*WiiDRC_Data(void){return &Drc;}
static bool WiiDRC_ShutdownRequested(void){return false;}
static void SetShutdown(void){}static void HIDUpdateRegisters(void){}static void HIDRead(unsigned v){}
static bool IsWiiU(void){return false;}static void PAD_ScanPads(void){++Scans;}
static u32 PAD_ButtonsDown(int i){return i?0:Down;}static u32 PAD_ButtonsHeld(int i){return i?0:Held;}
static s8 PAD_StickX(int i){return i?0:X;}static s8 PAD_StickY(int i){return i?0:Y;}
"""
  names=['UP','DOWN','LEFT','RIGHT','A','B','1','2','HOME','X','Y','PLUS','MINUS']
  pre+='\n'.join('#define '+family+'_BUTTON_'+name+' 0u' for family in ['WPAD','WPAD_CLASSIC','WIIDRC'] for name in names)+'\n'
  exports=r"""
static HeldCounters h;
__declspec(dllexport) void reset(void){memset(&h,0,sizeof(h));memset(HidPads,0,sizeof(HidPads));for(int i=0;i<4;i++)Wpad[i].err=-1;SLock=false;Repeat=Scans=Held=Down=0;X=Y=0;}
__declspec(dllexport) void sample(unsigned held,unsigned down,int x,int y){Held=held;Down=down;X=x;Y=y;FPAD_Update();}
__declspec(dllexport) unsigned move(void){h.redraw=false;return RepeatDown(&h);}
__declspec(dllexport) unsigned redraw(void){return h.redraw;}
__declspec(dllexport) unsigned confirm(void){return FPAD_OK(0);}
__declspec(dllexport) unsigned scans(void){return Scans;}
""".replace('for(int i=0;i<4;i++)','int i;for(i=0;i<4;i++)')
  (d/'test.c').write_text(pre+macros+body+repeat+exports,encoding='utf-8');env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/gcc.exe','-std=gnu89','-O2','-shared','-static',str(d/'test.c'),'-o',str(d/'test.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)));cls.lib.sample.argtypes=[C.c_uint,C.c_uint,C.c_int,C.c_int]
 def setUp(self):self.lib.reset()
 def test_update_and_button_queries_match_fetched_upstream(self):
  self.assertEqual(hashlib.sha256(self.body.encode()).hexdigest(),EXPECTED)
 def test_native_down_event_is_kept_when_held_is_empty(self):
  self.lib.sample(0,4,0,0);self.assertEqual(self.lib.move(),1);self.assertEqual(self.lib.scans(),1)
 def test_release_then_new_tap_rearms(self):
  for _ in range(4):
   self.lib.sample(4,4,0,0);self.assertEqual(self.lib.move(),1)
   self.lib.sample(0,0,0,0);self.assertEqual(self.lib.move(),0)
 def test_stock_hold_delay_and_repeat(self):
  events=[]
  for i in range(15):
   self.lib.sample(4,4 if i==0 else 0,0,0)
   if self.lib.move():events.append(i)
  self.assertEqual(events,[0,11,12,13,14])
 def test_confirm_waits_for_release(self):
  self.lib.sample(256,256,0,0);self.assertEqual(self.lib.confirm(),1)
  self.lib.sample(256,0,0,0);self.assertEqual(self.lib.confirm(),0)
  self.lib.sample(0,0,0,0);self.lib.sample(256,256,0,0);self.assertEqual(self.lib.confirm(),1)
 def test_idle_poll_does_not_request_expensive_redraw(self):
  self.lib.sample(0,0,0,0);self.assertEqual(self.lib.move(),0);self.assertEqual(self.lib.redraw(),0)
  self.lib.sample(4,4,0,0);self.assertEqual(self.lib.move(),1);self.assertEqual(self.lib.redraw(),1)
 def test_each_launcher_page_polls_before_conditional_draw(self):
  t=(ROOT/'launcher/loader/source/SusamuneMenu.c').read_text(encoding='utf-8')
  self.assertEqual(t.count('VIDEO_WaitVSync();\n\t\tFPAD_Update();'),5)
  self.assertEqual(t.count('if (!held.redraw) continue;'),5)
if __name__=='__main__':unittest.main()
