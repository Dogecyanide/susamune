"""The menu-close chord must release before B/Start can exit Watch."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WatchExitTests(unittest.TestCase):
    def test_held_menu_close_chord_is_not_a_watch_exit(self):
        source = (ROOT / 'src/ghost.cpp').read_text()
        start = source.index('        const bool menuOwnsExit =')
        end = source.index('        if (actionsFastForwardActive())', start)
        code = r'''
using u16=unsigned short;
namespace JUTGamePad { enum{B=0x200,START=0x1000};struct Pad{u16 mButton;};Pad mPadStatus[1];}
struct Menu{bool open;bool shown(){return open;}} menu,*gMenu=&menu;
enum{BIND_MENU_TOGGLE};
struct Binds{bool edge;int suppressed;bool wasPressedRaw(int){return edge;}
 void suppressUntilRelease(){++suppressed;}}gBinds;
bool sObserverExitArmed,exited;
void endObserver(bool,const char*){exited=true;}
void tick(){
''' + source[start:end] + r'''
}
#define API extern "C" __declspec(dllexport)
API void reset(){sObserverExitArmed=false;exited=false;gBinds.suppressed=0;}
API int frame(unsigned buttons,int open,int edge){JUTGamePad::mPadStatus[0].mButton=(u16)buttons;menu.open=open;gBinds.edge=edge;exited=false;tick();return exited;}
API int armed(){return sObserverExitArmed;}
API int suppressed(){return gBinds.suppressed;}
'''
        directory = ROOT / 'build/pr11-camera-check'
        directory.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            cpp, dll = Path(temp) / 'exit.cpp', Path(temp) / 'exit.dll'
            cpp.write_text(code)
            result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'),
                '--target=x86_64-pc-windows-msvc', '-shared', '-nostdlib',
                '-fuse-ld=lld', '-Wl,/noentry', str(cpp), '-o', str(dll)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            lib = C.CDLL(str(dll))
            try:
                for chord in (0x1800, 0x600):  # default Start+Y; a menu chord containing B
                    lib.reset()
                    self.assertEqual(lib.frame(0, 0, 0), 0)
                    self.assertEqual(lib.armed(), 1)
                    for held, opened, edge in ((chord, 1, 1), (chord, 1, 0),
                                              (0, 1, 0), (chord, 0, 1),
                                              (chord, 0, 0), (chord, 0, 0)):
                        self.assertEqual(lib.frame(held, opened, edge), 0)
                        self.assertEqual(lib.armed(), 0)
                    self.assertEqual(lib.frame(0, 0, 0), 0)
                    self.assertEqual(lib.armed(), 1)
                    self.assertEqual(lib.frame(0x200, 0, 0), 1)
                    self.assertEqual(lib.suppressed(), 1)
            finally:
                _ctypes.FreeLibrary(lib._handle)


if __name__ == '__main__':
    unittest.main()
