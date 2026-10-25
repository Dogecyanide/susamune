"""Check the production shortcut's settings commits and input ownership."""
import ctypes
from _ctypes import FreeLibrary
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SlowdownBindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="slowdown-bind-", dir=ROOT / "build")
        cls.addClassCleanup(cls.folder.cleanup)
        folder = Path(cls.folder.name)
        stubs = folder / "include/susamune"
        stubs.mkdir(parents=True)
        (stubs / "binds.hxx").write_text('''
#pragma once
enum { BIND_SLOWDOWN_TOGGLE };
struct Binds { bool edge; bool wasPressed(int) const { return edge; } };
extern Binds gBinds;
''')
        (stubs / "settings.hxx").write_text('''
#pragma once
enum { SETTING_GAMEPLAY_SPEED, SETTING_SLOWDOWN_PRESET };
struct Settings { unsigned value[2], writes;
    unsigned get(int id) const { return value[id]; }
    void set(int id,unsigned v) { value[id]=v; ++writes; }
};
extern Settings gSettings;
''')
        (stubs / "practice_session.hxx").write_text('''
#pragma once
namespace PracticeSession { void resetGameplaySpeed(); }
''')
        (stubs / "menu.hxx").write_text('''
#pragma once
struct Menu { void toast(const char *) {} };
extern Menu *gMenu;
''')
        wrapper = folder / "wrapper.cpp"
        wrapper.write_text('''
#include "susamune/binds.hxx"
#include "susamune/settings.hxx"
#include "susamune/menu.hxx"
#include "susamune/slowdown_bind.hxx"
#include "Dolphin/printf.h"
Binds gBinds;
Settings gSettings;
Menu *gMenu;
unsigned resets;
namespace PracticeSession { void resetGameplaySpeed() { ++resets; } }
extern "C" int snprintf(char *,size_t,const char *,...) { return 0; }
extern "C" __declspec(dllexport) void init(unsigned active,unsigned preset) {
    gSettings.value[0]=active;gSettings.value[1]=preset;gSettings.writes=0;resets=0;
}
extern "C" __declspec(dllexport) void sample(unsigned edge,unsigned allowed) {
    gBinds.edge=edge;SlowdownBind::update(allowed);
}
extern "C" __declspec(dllexport) unsigned value(unsigned field) {
    if(field<2) return gSettings.value[field];
    return field==2?gSettings.writes:resets;
}
''')
        library = folder / "bind.dll"
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-std=c++17", "-O2", "-fno-exceptions", "-fno-rtti", "-ffreestanding",
            "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
            "-I", str(stubs.parent), "-I", str(ROOT / "include"),
            str(ROOT / "src/slowdown_bind.cpp"), str(wrapper), "-o", str(library),
        ], check=True, env={**os.environ, "TMP": str(folder), "TEMP": str(folder)})
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.dll._handle)

    def test_toggle_uses_preset_then_returns_to_normal(self):
        for preset in (1, 25, 50, 99):
            self.dll.init(0, preset)
            self.dll.sample(1, 1)
            self.assertEqual(self.dll.value(0), preset)
            self.dll.sample(0, 1)
            self.assertEqual(self.dll.value(2), 1)
            self.dll.sample(1, 1)
            self.assertEqual(self.dll.value(0), 0)
            self.assertEqual(self.dll.value(1), preset)
            self.assertEqual(self.dll.value(3), 2)

    def test_modal_suppression_and_unpressed_bind_do_not_touch_gameplay(self):
        for active in (0, 50):
            self.dll.init(active, 25)
            self.dll.sample(1, 0)
            self.dll.sample(0, 1)
            self.assertEqual(self.dll.value(0), active)
            self.assertEqual(self.dll.value(2), 0)
            self.assertEqual(self.dll.value(3), 0)

    def test_current_manual_slowdown_also_toggles_off(self):
        self.dll.init(35, 50)
        self.dll.sample(1, 1)
        self.assertEqual(self.dll.value(0), 0)
        self.dll.sample(1, 1)
        self.assertEqual(self.dll.value(0), 50)


if __name__ == "__main__":
    unittest.main()
