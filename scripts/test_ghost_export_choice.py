"""Exercise actual export chooser handlers without storage/network side effects."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
from test_nested_menu_focus import function
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ExportChoiceTests(unittest.TestCase):
 def test_destination_and_identity_guards(self):
  source=(ROOT/'src/menu.cpp').read_text()
  code=r'''using u16=unsigned short;using s16=short;
namespace JUTGamePad {enum{A=1,B=2,Y=4,Z=8};}
enum{SUSAMUNE_GHOST_IMPORTED_PROFILE=4,GHOST_ACCOUNT_STATUS=0};
namespace GhostStorage {
struct Identity {int id,profile;};bool blocked,fresh=true,draft=true,local=true;int exports,accounts,drafts,last;
bool identityValid(const Identity&i){return i.id>0;}bool busy(){return blocked;}
bool exportShare(const Identity&i){++exports;last=i.id;return local;}
bool beginUploadDraft(){++drafts;return draft;}bool accountAction(int){++accounts;return true;}
}
struct Menu {int toasts;void toast(const char*){++toasts;}};
struct Input {u16 press,wait;u16 update(){u16 p=press;press=0;return p;}void begin(u16 p){wait=p;}void clear(){wait=0;}};
struct Tab {enum {CHOICE_NONE,CHOICE_ACTION,CHOICE_EXPORT,CHOICE_WEB_UPLOAD};int mChoice=CHOICE_NONE,mSel=12;
struct Ref {GhostStorage::Identity identity{77,0};s16 selection=12;}mPrimaryRef;Input mPromptInput{};
bool refStillValid(const Ref&){return GhostStorage::fresh;}const char*storageStatus(){return "status";}
'''
  code+=function(source,'void beginExportChoice(')+function(source,'void updateExportChoice(')+'};\n'
  code+=r'''
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
extern "C" __declspec(dllexport) unsigned run(){using namespace GhostStorage;Menu m{};
Tab a;a.beginExportChoice(&m);CHECK(a.mChoice==Tab::CHOICE_EXPORT&&exports==0&&accounts==0&&a.mPromptInput.wait==15);
a.mPromptInput.press=JUTGamePad::B;a.updateExportChoice(&m);CHECK(a.mChoice==Tab::CHOICE_NONE&&a.mSel==12&&!exports);
Tab b;b.mPrimaryRef.identity.profile=4;b.beginExportChoice(&m);CHECK(b.mChoice==Tab::CHOICE_NONE&&!exports);
Tab c;c.beginExportChoice(&m);c.mPromptInput.press=JUTGamePad::A;c.updateExportChoice(&m);CHECK(exports==1&&last==77&&c.mSel==12&&c.mChoice==Tab::CHOICE_NONE);
Tab d;d.beginExportChoice(&m);d.mPromptInput.press=JUTGamePad::Y;d.updateExportChoice(&m);CHECK(d.mChoice==Tab::CHOICE_WEB_UPLOAD&&d.mSel==0&&drafts==1&&accounts==1&&exports==1);
Tab e;e.beginExportChoice(&m);blocked=true;e.mPromptInput.press=JUTGamePad::A;e.updateExportChoice(&m);CHECK(exports==1&&e.mChoice==Tab::CHOICE_EXPORT);blocked=false;
fresh=false;e.mPromptInput.press=JUTGamePad::Y;e.updateExportChoice(&m);CHECK(e.mChoice==Tab::CHOICE_NONE&&accounts==1);fresh=true;
Tab f;f.beginExportChoice(&m);draft=false;f.mPromptInput.press=JUTGamePad::Y;f.updateExportChoice(&m);CHECK(f.mChoice==Tab::CHOICE_EXPORT&&accounts==1);draft=true;
return 0;}
'''
  with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='export-choice-') as d:
   p=pathlib.Path(d);(p/'test.cpp').write_text(code);dll=p/'test.dll'
   subprocess.run([str(ROOT/'toolchain/clang++.exe'),'--target=x86_64-pc-windows-msvc','-std=c++17','-O2','-fno-builtin','-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry',str(p/'test.cpp'),'-o',str(dll)],check=True,capture_output=True)
   lib=C.CDLL(str(dll))
   try:self.assertEqual(lib.run(),0)
   finally:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle))
if __name__=='__main__':unittest.main()
