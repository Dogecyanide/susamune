"""A queued warp must wait for its exact protected PB to be saved."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class GhostAutoSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        source = (ROOT / "src/warp_wheel.cpp").read_text(encoding="utf-8")
        update = function(source, "void updateAutoSave()")
        shim = r'''
typedef unsigned u32;
namespace JUTGamePad {enum {B=2,A=1};}
enum {PROMPT_AUTO_OFF,PROMPT_AUTO_PREPARE,PROMPT_AUTO_SAVE_PENDING};
static int sPromptAutoSave, fallback, executed, saved, toasts;
static u32 unsaved, replacement, saveToken;
struct {u32 token;} sPrompt;
struct Input {int buttons;int update(){int b=buttons;buttons=0;return b;}void begin(int){}} sPromptInput;
struct Menu {void toast(const char*){toasts++;}} menu, *gMenu=&menu;
namespace Ghost {
bool hasUnsavedPBToken(u32 token){return token && token==unsaved;}
}
namespace GhostStorage {
static bool active, timeout, ready, success;
bool timedOut(){return timeout;}bool busy(){return active;}bool available(){return ready;}
const char *statusText(){return "storage";}
bool saveNew(u32 token){saved++;saveToken=token;return success;}
}
void fallBackToPBPrompt(const char*){fallback++;sPromptAutoSave=PROMPT_AUTO_OFF;}
bool refreshPromptPB(){if(!replacement)return false;sPrompt.token=unsaved=replacement;replacement=0;return true;}
void executePromptAction(){executed++;sPromptAutoSave=PROMPT_AUTO_OFF;}
'''
        wrapper = r'''
extern "C" __declspec(dllexport) int run(int scenario){
 fallback=executed=saved=toasts=0;unsaved=sPrompt.token=37;replacement=saveToken=0;
 sPromptAutoSave=PROMPT_AUTO_PREPARE;sPromptInput.buttons=0;
 GhostStorage::active=GhostStorage::timeout=false;GhostStorage::ready=GhostStorage::success=true;
 if(scenario==0){
   updateAutoSave();if(saved!=1||saveToken!=37||executed||sPromptAutoSave!=PROMPT_AUTO_SAVE_PENDING)return 1;
   GhostStorage::active=true;updateAutoSave();if(saved!=1||executed||fallback)return 2;
   GhostStorage::active=false;unsaved=0;updateAutoSave();return executed==1&&!fallback?0:3;
 }
 if(scenario==1){updateAutoSave();updateAutoSave();return fallback==1&&!executed&&saved==1?0:4;}
 if(scenario==2){GhostStorage::timeout=true;updateAutoSave();return fallback==1&&!executed&&!saved?0:5;}
 if(scenario==3){GhostStorage::active=true;sPromptInput.buttons=JUTGamePad::B;updateAutoSave();return fallback==1&&!executed&&!saved?0:6;}
 if(scenario==4){unsaved=0;replacement=49;updateAutoSave();return saved==1&&saveToken==49&&!executed&&!fallback?0:7;}
 if(scenario==5){GhostStorage::success=false;updateAutoSave();return fallback==1&&!executed?0:8;}
 if(scenario==6){GhostStorage::ready=false;updateAutoSave();return fallback==1&&!executed&&!saved?0:9;}
 return 10;
}
'''
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        (path / "test.cpp").write_text(shim + update + wrapper)
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(path / "test.cpp"), "-o", str(path / "test.dll")], check=True)
        cls.dll = C.CDLL(str(path / "test.dll"))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.dll._handle)))
        cls.dll.run.argtypes = [C.c_int]
        cls.dll.run.restype = C.c_int

    def test_exact_token_ack_releases_warp(self):
        self.assertEqual(self.dll.run(0), 0)

    def test_failed_or_unavailable_storage_keeps_pb_prompt(self):
        for scenario in (1, 2, 5, 6):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.dll.run(scenario), 0)

    def test_cancel_pending_save_does_not_warp(self):
        self.assertEqual(self.dll.run(3), 0)

    def test_new_protected_pb_gets_its_own_save(self):
        self.assertEqual(self.dll.run(4), 0)


if __name__ == "__main__":
    unittest.main()
