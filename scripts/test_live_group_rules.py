"""Three/four-player drafts and results through the production rules engine."""
import ctypes as C
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Config(C.Structure):
    _fields_ = [("players", C.c_ubyte), ("bestOf", C.c_ubyte), ("setBestOf", C.c_ubyte),
                ("draft", C.c_bool), ("freeRoam", C.c_bool)]

class State(C.Structure):
    _fields_ = [("config", Config), ("generation", C.c_uint), ("revision", C.c_uint), ("round", C.c_uint),
                ("candidates", C.c_ushort * 5), ("selected", C.c_ushort), ("times", C.c_int * 4),
                ("phase", C.c_ubyte), ("readyMask", C.c_ubyte), ("resultMask", C.c_ubyte), ("eligibleMask", C.c_ubyte),
                ("bannedMask", C.c_ubyte), ("bans", C.c_ubyte), ("rotation", C.c_ubyte), ("winner", C.c_ubyte),
                ("roundWins", C.c_ubyte * 4), ("setWins", C.c_ubyte * 4)]

class GroupRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name) / "group.cpp"
        path.write_text(r'''
#include "susamune/live_group_rules.hxx"
using namespace LiveGroupRules;
extern "C" void*memset(void*p,int c,__SIZE_TYPE__ n){unsigned char*b=(unsigned char*)p;while(n--)*b++=c;return p;}
#define API extern "C" __declspec(dllexport)
API unsigned size(){return sizeof(State);}
API bool beginRoom(State*s,unsigned n,unsigned draft){return begin(*s,Config{(unsigned char)n,3,3,draft!=0,false},23,7);}
API bool choices(State*s,unsigned count){const unsigned short a[]={10,20,30,40,50};return candidates(*s,a,count,token(*s));}
API unsigned actorOf(State*s){return actor(*s);}
API bool strike(State*s,unsigned who,unsigned at,unsigned revision){return ban(*s,who,at,Token{s->generation,revision});}
API bool readyPlayer(State*s,unsigned who,unsigned gen){return ready(*s,who,true,gen);}
API bool startRace(State*s,unsigned mask){return start(*s,mask);}
API bool finish(State*s,unsigned who,int time,unsigned gen,unsigned round){return result(*s,who,time,time>=0,gen,round);}
API bool next(State*s){return advance(*s);}
''')
        dll = path.with_suffix('.dll')
        subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
                        '-shared', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Wl,/noentry', '-O2',
                        '-I', str(ROOT / 'include'), str(path), str(ROOT / 'src/live_group_rules.cpp'),
                        '-o', str(dll)], check=True, capture_output=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: FreeLibrary(cls.lib._handle))
        for name, count in [('beginRoom', 2), ('choices', 1), ('actorOf', 0), ('strike', 3),
                            ('readyPlayer', 2), ('startRace', 1), ('finish', 4), ('next', 0)]:
            fn = getattr(cls.lib, name)
            fn.argtypes = [C.POINTER(State)] + [C.c_uint] * count
            fn.restype = C.c_uint if name == 'actorOf' else C.c_bool
        assert cls.lib.size() == C.sizeof(State)

    def new(self, players=4, draft=True):
        s = State()
        self.assertTrue(self.lib.beginRoom(C.byref(s), players, draft))
        return s

    def draft(self, s):
        n = s.config.players
        self.assertFalse(self.lib.choices(C.byref(s), n))
        self.assertTrue(self.lib.choices(C.byref(s), n + 1))
        old = s.revision
        for i in range(n):
            actor = (s.rotation + i) % n
            self.assertEqual(self.lib.actorOf(C.byref(s)), actor)
            self.assertFalse(self.lib.strike(C.byref(s), (actor + 1) % n, i, s.revision))
            if i:
                before = bytes(s)
                self.assertFalse(self.lib.strike(C.byref(s), actor, i, old))
                self.assertEqual(bytes(s), before)
            self.assertTrue(self.lib.strike(C.byref(s), actor, i, s.revision))
        self.assertEqual(s.selected, (n + 1) * 10)
        self.assertEqual(s.phase, 2)

    def race(self, s, times):
        n = s.config.players
        for i in range(n):
            self.assertFalse(self.lib.startRace(C.byref(s), (1 << n) - 1))
            self.assertTrue(self.lib.readyPlayer(C.byref(s), i, 23))
        self.assertFalse(self.lib.startRace(C.byref(s), (1 << n) - 2))
        self.assertTrue(self.lib.startRace(C.byref(s), (1 << n) - 1))
        for i in reversed(range(n)):
            self.assertFalse(self.lib.finish(C.byref(s), i, times[i], 23, s.round - 1))
            self.assertTrue(self.lib.finish(C.byref(s), i, times[i], 23, s.round))
            self.assertFalse(self.lib.finish(C.byref(s), i, times[i], 23, s.round))

    def test_three_and_four_player_drafts_rotate_between_il_matches(self):
        for n in (3, 4):
            s = self.new(n)
            self.draft(s)
            for _ in range(2):
                self.race(s, list(range(100, 100 + n)))
                self.assertTrue(self.lib.next(C.byref(s)))
            self.assertEqual((s.phase, s.rotation, s.setWins[0]), (5, 1, 1))
            self.draft(s)
            for attempt in range(2):
                self.race(s, list(range(100, 100 + n)))
                if not attempt: self.assertTrue(self.lib.next(C.byref(s)))
            self.assertEqual((s.phase, s.setWins[0]), (6, 2))

    def test_ties_and_assisted_attempts_never_award_a_win(self):
        for times in ([100, 100, 101, 102], [100, 101, -1, 102]):
            s = self.new(draft=False)
            self.race(s, times)
            self.assertEqual((s.phase, s.winner), (4, 255))
            self.assertEqual(list(s.roundWins), [0] * 4)
            self.assertTrue(self.lib.next(C.byref(s)))
            self.assertEqual((s.readyMask, s.resultMask, s.eligibleMask), (0, 0, 0))

    def test_wrong_generation_and_invalid_players_do_not_change_state(self):
        s = self.new(draft=False)
        before = bytes(s)
        self.assertFalse(self.lib.readyPlayer(C.byref(s), 0, 24))
        self.assertFalse(self.lib.readyPlayer(C.byref(s), 4, 23))
        self.assertFalse(self.lib.beginRoom(C.byref(s), 5, 1))
        self.assertEqual(bytes(s), before)

if __name__ == '__main__':
    unittest.main()
