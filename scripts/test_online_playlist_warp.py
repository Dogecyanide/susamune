"""A PB must defer online playlist progression without losing its episode."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_iling_attempt_lifecycle import function
ROOT = Path(__file__).resolve().parents[1]
class PlaylistWarpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='moonshine-playlist-warp-')
        cls.addClassCleanup(cls.tmp.cleanup)
        wheel = (ROOT/'src/warp_wheel.cpp').read_text()
        stage = (ROOT/'src/stage_loader.cpp').read_text()
        code = r'''
#define TIMEWARP_LIVE_RACING 1
using u8=unsigned char; using s32=int;
bool unsaved, disabled; int started, episodeSeen, sArmedILIndex;
enum {SETTING_DISABLE_WARPS};
struct Settings {bool getBool(int){return disabled;}}gSettings;
namespace LevelWarp {struct Dest{u8 area,episode,gameInt3;};
void warpToGuarded(Dest,int,bool){} void restart(bool){} void restartFull(){}
void restartAfterSave(bool){} void restartFullAfterSave(){}}
enum PromptAction {PROMPT_NONE,PROMPT_WARP,PROMPT_IL,PROMPT_ONLINE_IL,PROMPT_ONLINE_MENU,PROMPT_EXIT_AREA,PROMPT_TITLE,PROMPT_RESTART_KEEP,PROMPT_RESTART_FULL,PROMPT_RESTART_SAVE_KEEP,PROMPT_RESTART_SAVE_FULL,PROMPT_SAVESTATE_LOAD,PROMPT_NATURAL_DEPARTURE};
struct PromptState{PromptAction action;LevelWarp::Dest dest;int detail;}sPrompt;
bool sPromptSaving,sPendingTitleExit,sSavestateLoadApproved,sHoldNaturalDeparture;
void clearPrompt(){sPrompt={};} void armExitAreaWarp(LevelWarp::Dest){}
struct Binds{void suppressUntilRelease(){}}gBinds;
struct Menu{bool shown(){return false;}void hide(){} void toast(const char*){} bool openOnline(){return true;}}menu,*gMenu=&menu;
namespace ILing{int count(){return 100;}bool start(int,int){return true;}
bool startOnline(int entry,int episode){if(unsaved||disabled)return false;started=entry;episodeSeen=episode;return true;}}
bool beginPrompt(PromptAction action,LevelWarp::Dest dest,int detail){if(!unsaved)return false;sPrompt={action,dest,detail};return true;}
namespace WarpWheel{
''' + function(wheel,'requestOnlineILStart') + r'''
bool requestILStart(int){return true;}}
''' + function(wheel,'executeOnlinePrompt') + function(wheel,'executePromptAction') + r'''
enum{STATE_REQUESTING=1,STATE_BLOCKED,STATE_WAITING,STATE_WAITING_POST_SAVE,OUTCOME_WARPS_DISABLED};
struct {int state,outcome,lastEntry,lastQf,displayFrames,holdingDeparture,activeIndex;}sRuntime;
const int kResultDisplayFrames=120;
struct Plan {struct {u8 episode;}items[1];}plan,*sOnlinePlan=&plan;
int expectedStartEntry(){return 3;}
''' + function(stage,'requestCurrent') + function(stage,'requestCurrentPostSave') + r'''
extern "C" __declspec(dllexport) int run(int postSave,int pb,int episode){
 sRuntime={};sPrompt={};started=-1;episodeSeen=-1;disabled=false;unsaved=pb;plan.items[0].episode=episode|0x80;
 bool ok=postSave?requestCurrentPostSave():requestCurrent();
 if(!ok||sRuntime.state!=(postSave?STATE_WAITING_POST_SAVE:STATE_WAITING))return 1;
 if(pb){if(started!=-1||sPrompt.action!=PROMPT_ONLINE_IL)return 2;unsaved=false;executePromptAction();}
 return started==3&&episodeSeen==episode&&sArmedILIndex==3?0:3;
}
'''
        path=Path(cls.tmp.name)/'playlist.cpp';path.write_text(code)
        result=subprocess.run([str(ROOT/'toolchain/clang++.exe'),'--target=x86_64-pc-windows-msvc','-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry','-O2',str(path),'-o',str(path.with_suffix('.dll'))],capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        cls.lib=C.CDLL(str(path.with_suffix('.dll')))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
    def test_progression_retains_episode_across_pb_and_save_dialog(self):
        for post in (0,1):
            for pb in (0,1):
                for episode in range(8):
                    self.assertEqual(self.lib.run(post,pb,episode),0,(post,pb,episode))
if __name__=='__main__':unittest.main()
