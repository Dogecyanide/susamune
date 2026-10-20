"""Exercise the production draft/set engine through its bounded public API."""

import ctypes as C
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
NONE = 0xff
NO_ENTRY = 0xffff
HOST_BAN, GUEST_BANS, HOST_PICK, IL_MATCH, NEED, WINNER_BAN, LOSER_PICK, DONE = range(1, 9)


class State(C.Structure):
    _fields_ = [("generation", C.c_uint), ("revision", C.c_uint),
                ("candidates", C.c_ushort * 5), ("selected", C.c_ushort),
                ("phase", C.c_ubyte), ("bannedMask", C.c_ubyte),
                ("roundWins", C.c_ubyte * 2), ("setWins", C.c_ubyte * 2),
                ("bestOf", C.c_ubyte), ("previousWinner", C.c_ubyte)]


class DraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="live-draft-", dir=ROOT / "build")
        cls.addClassCleanup(cls.folder.cleanup)
        source = Path(cls.folder.name) / "draft.cpp"
        source.write_text(r'''
#include "susamune/live_draft.hxx"
extern "C" void* memset(void*p,int c,unsigned long long n){auto*b=(u8*)p;while(n--)*b++=(u8)c;return p;}
extern "C" void* memcpy(void*p,const void*q,unsigned long long n){auto*b=(u8*)p;auto*a=(const u8*)q;while(n--)*b++=*a++;return p;}
using namespace LiveDraft;
#define API extern "C" __declspec(dllexport) unsigned
API start(State*s,unsigned generation,unsigned best,const u16*c){return begin(*s,generation,best,c);}
API strike(State*s,unsigned actor,unsigned index,unsigned generation,unsigned revision){return ban(*s,actor,index,{generation,revision});}
API choose(State*s,unsigned actor,unsigned index,unsigned generation,unsigned revision){return pick(*s,actor,index,{generation,revision});}
API result(State*s,unsigned winner,unsigned generation,unsigned revision){return recordRound(*s,winner,{generation,revision});}
API candidates(State*s,const u16*c,unsigned generation,unsigned revision){return nextCandidates(*s,c,{generation,revision});}
API actor(const State*s){return currentActor(*s);}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-std=c++17", "-O2", "-fno-exceptions", "-fno-rtti", "-ffreestanding",
            "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
            "-I", str(ROOT / "include"), str(source), str(ROOT / "src/live_draft.cpp"),
            "-o", str(library),
        ], check=True)
        cls.dll = C.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.dll._handle)
        sp = C.POINTER(State)
        cp = C.POINTER(C.c_ushort)
        for name, args in {
            "start": [sp, C.c_uint, C.c_uint, cp],
            "strike": [sp] + [C.c_uint] * 4,
            "choose": [sp] + [C.c_uint] * 4,
            "result": [sp] + [C.c_uint] * 3,
            "candidates": [sp, cp, C.c_uint, C.c_uint],
            "actor": [sp],
        }.items():
            function = getattr(cls.dll, name)
            function.argtypes = args
            function.restype = C.c_uint

    @staticmethod
    def batch(values=(10, 20, 30, 40, 50)):
        return (C.c_ushort * 5)(*values)

    def new(self, best=3, generation=7):
        state = State()
        self.assertTrue(self.dll.start(C.byref(state), generation, best, self.batch()))
        self.assertEqual(C.sizeof(state), 28)
        self.assertEqual((state.selected, state.previousWinner), (NO_ENTRY, NONE))
        return state

    def act(self, method, state, *args, expected=None):
        token = expected if expected is not None else (state.generation, state.revision)
        return getattr(self.dll, method)(C.byref(state), *args, *token)

    def reject(self, method, state, *args, **kwargs):
        before = bytes(state)
        self.assertFalse(self.act(method, state, *args, **kwargs))
        self.assertEqual(bytes(state), before)

    def opening(self, state):
        self.assertTrue(self.act("strike", state, 0, 0))
        self.assertTrue(self.act("strike", state, 1, 1))
        self.assertTrue(self.act("strike", state, 1, 2))
        self.assertTrue(self.act("choose", state, 0, 3))
        self.assertEqual((state.phase, state.selected), (IL_MATCH, 40))

    def counter(self, state):
        self.assertEqual(state.phase, NEED)
        winner = state.previousWinner
        self.assertTrue(self.act("candidates", state, self.batch((60, 70, 80, 90, 100))))
        self.assertEqual((state.phase, self.dll.actor(C.byref(state))), (WINNER_BAN, winner))
        self.reject("choose", state, winner ^ 1, 1)
        self.reject("strike", state, winner ^ 1, 0)
        self.assertTrue(self.act("strike", state, winner, 0))
        self.assertEqual((state.phase, self.dll.actor(C.byref(state))), (LOSER_PICK, winner ^ 1))
        self.reject("choose", state, winner, 1)
        self.reject("choose", state, winner ^ 1, 0)
        self.assertTrue(self.act("choose", state, winner ^ 1, 1))
        self.assertEqual(list(state.roundWins), [0, 0])

    def test_opening_turns_and_atomic_rejections(self):
        state = self.new()
        self.assertEqual(self.dll.actor(C.byref(state)), 0)
        for method, actor, index in (("strike", 1, 0), ("choose", 0, 0),
                                      ("strike", 0, 5), ("strike", NONE, 0)):
            self.reject(method, state, actor, index)
        self.assertTrue(self.act("strike", state, 0, 2))
        self.assertEqual((state.phase, self.dll.actor(C.byref(state))), (GUEST_BANS, 1))
        self.reject("strike", state, 1, 2)
        self.assertTrue(self.act("strike", state, 1, 0))
        self.assertEqual(state.phase, GUEST_BANS)
        self.reject("choose", state, 0, 1)
        self.assertTrue(self.act("strike", state, 1, 4))
        self.assertEqual((state.phase, self.dll.actor(C.byref(state))), (HOST_PICK, 0))
        self.reject("strike", state, 0, 1)
        self.reject("choose", state, 1, 1)
        self.assertTrue(self.act("choose", state, 0, 1))
        self.assertEqual((state.phase, state.selected, self.dll.actor(C.byref(state))),
                         (IL_MATCH, 20, NONE))
        self.reject("strike", state, 0, 3)
        self.reject("choose", state, 0, 3)

    def test_every_legal_opening_leaves_exactly_two_picks(self):
        for first in range(5):
            for second in range(5):
                if second == first:
                    continue
                for third in range(5):
                    if third in (first, second):
                        continue
                    for chosen in set(range(5)) - {first, second, third}:
                        state = self.new()
                        for actor, index in ((0, first), (1, second), (1, third)):
                            self.assertTrue(self.act("strike", state, actor, index))
                        self.assertTrue(self.act("choose", state, 0, chosen))
                        self.assertEqual(state.selected, (chosen + 1) * 10)

    def test_each_il_is_first_to_two_with_no_contest_rounds(self):
        state = self.new(5)
        self.opening(state)
        for winner, scores in ((NONE, (0, 0)), (1, (0, 1)), (NONE, (0, 1)),
                               (0, (1, 1)), (NONE, (1, 1)), (1, (1, 2))):
            before = state.revision
            self.assertTrue(self.act("result", state, winner))
            self.assertEqual(tuple(state.roundWins), scores)
            self.assertEqual(state.revision, before + 1)
        self.assertEqual((state.phase, state.previousWinner, tuple(state.setWins)), (NEED, 1, (0, 1)))
        self.reject("result", state, 1)

    def test_full_bo3_and_bo5_sets_change_counterpicker(self):
        for best, winners in ((3, (1, 0, 1)), (5, (0, 1, 0, 1, 0))):
            state = self.new(best)
            self.opening(state)
            for index, winner in enumerate(winners):
                self.assertTrue(self.act("result", state, winner))
                self.assertEqual(state.phase, IL_MATCH)
                self.assertTrue(self.act("result", state, winner))
                if index < len(winners) - 1:
                    self.counter(state)
            self.assertEqual(state.phase, DONE)
            self.assertEqual(state.setWins[winners[-1]], best // 2 + 1)
            self.assertEqual(self.dll.actor(C.byref(state)), NONE)
            for method, args in (("candidates", (self.batch(),)), ("result", (0,)),
                                 ("strike", (0, 0)), ("choose", (1, 1))):
                self.reject(method, state, *args)

    def test_invalid_candidate_batches_never_change_state(self):
        state = self.new()
        before = bytes(state)
        for generation, best, values in ((0, 3, self.batch()), (3, 1, self.batch()),
                                         (3, 4, self.batch()), (3, 3, None),
                                         (3, 3, self.batch((1, 2, 1, 4, 5))),
                                         (3, 3, self.batch((1, 2, 3, 4, NO_ENTRY)))):
            self.assertFalse(self.dll.start(C.byref(state), generation, best, values))
            self.assertEqual(bytes(state), before)
        self.reject("candidates", state, self.batch())
        self.opening(state)
        self.act("result", state, 0)
        self.act("result", state, 0)
        for values in (None, self.batch((1, 2, 3, 4, 4)), self.batch((1, 2, 3, NO_ENTRY, 5))):
            self.reject("candidates", state, values)

    def test_old_revisions_and_generations_cannot_replay_commands(self):
        state = self.new()
        old = (state.generation, state.revision)
        self.assertTrue(self.act("strike", state, 0, 0))
        self.reject("strike", state, 1, 1, expected=old)
        self.reject("strike", state, 1, 1, expected=(8, state.revision))
        self.act("strike", state, 1, 1)
        self.act("strike", state, 1, 2)
        self.act("choose", state, 0, 3)
        old = (state.generation, state.revision)
        self.assertTrue(self.act("result", state, 0))
        self.reject("result", state, 0, expected=old)
        self.assertEqual(tuple(state.roundWins), (1, 0))
        self.reject("result", state, 2)
        self.reject("result", state, 0, expected=(state.generation, state.revision + 1))

    def test_revision_exhaustion_stops_without_wrapping(self):
        state = self.new()
        self.opening(state)
        state.revision = 0xfffffffe
        self.assertTrue(self.act("result", state, NONE))
        self.assertEqual(state.revision, 0xffffffff)
        self.reject("result", state, 0)

    def test_two_replicas_produce_identical_state_after_every_action(self):
        states = [self.new(5, 1234), self.new(5, 1234)]
        for method, args in (("strike", (0, 0)), ("strike", (1, 1)),
                             ("strike", (1, 2)), ("choose", (0, 3)),
                             ("result", (0,)), ("result", (NONE,)), ("result", (0,)),
                             ("candidates", (self.batch((6, 7, 8, 9, 10)),)),
                             ("strike", (0, 4)), ("choose", (1, 2))):
            expected = (states[0].generation, states[0].revision)
            for state in states:
                self.assertTrue(self.act(method, state, *args, expected=expected))
            self.assertEqual(bytes(states[0]), bytes(states[1]))


if __name__ == "__main__":
    unittest.main()
