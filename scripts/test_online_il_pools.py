"""Check online pool membership against the real 133-entry IL catalogue."""

import ctypes as C
from _ctypes import FreeLibrary
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function


ROOT = Path(__file__).resolve().parents[1]
ANY, ALL, NON_ANY = range(3)
BANNED = {"Noki 5", "Pianta 2", "Gelato 5", "Bianco II Enter", "Noki Enter"}
ANY_ENTRIES = {
    "Bianco 2", "Bianco 3 (Full)", "Bianco 3 (Secret)", "Bianco 4", "Bianco 5",
    "Bianco 6 (Full)", "Bianco 6 (Secret)", "Bianco 7",
    "Ricco 1", "Ricco 2 (Full)", "Ricco 3", "Ricco 4 (Full)", "Ricco 4 (Secret)",
    "Ricco 5", "Ricco 6", "Ricco 7", "Gelato GBS", "Gelato 7",
    "Pinna 1", "Pinna 2 (Full)", "Pinna 2 (Secret)", "Pinna 3", "Pinna 4",
    "Pinna Park EYG", "Pinna 6 (Secret)", "Pinna 7",
    "Sirena 1", "Sirena 2 (Full)", "Sirena 2 (Secret)", "Sirena 3",
    "Sirena 4 (Full)", "Sirena 4 (Secret)", "Sirena 5", "Sirena 6", "Sirena 7",
    "Noki 1", "Noki 2", "Noki 3", "Noki 4", "Noki 6 (Full)", "Noki 6 (Secret)", "Noki 7",
    "Pianta 1", "Pianta 3", "Pianta 4", "Pianta 5 (Full)", "Pianta 5 (Secret)",
    "Pianta 6", "Pianta 7", "Airstrip 1", "Corona Mountain",
    "Bianco Plant", "Delfino Shadow Mario", "Travel Skip", "Gelato Plant", "Pianta Enter",
    "Honey Skip", "Ricco Enter", "Sirena Enter", "Corona Enter",
}


class OnlineILPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="online-il-pools-", dir=ROOT / "build")
        cls.addClassCleanup(cls.folder.cleanup)
        source = (ROOT / "src/iling.cpp").read_text()
        sequence = (ROOT / "include/SMS/System/GameSequence.hxx").read_text()
        warp = (ROOT / "src/warp_wheel.cpp").read_text()
        entries = (ROOT / "src/iling_entries.inc").read_text()
        cls.labels = re.findall(r'^\w+\("([^"]+)"', entries, re.M)
        code = '#define TIMEWARP_LIVE_RACING 1\n#include "susamune/iling.hxx"\n#include "susamune/iling_episodes.h"\n'
        code += "struct TGameSequence {" + sequence[sequence.index("    enum Area {"):
                                                    sequence.index("    void set(")] + "};\n"
        code += "namespace LevelWarp {struct Dest {enum {POST_CORONA=0x80};u8 area,episode,gameInt3;};u8 parentArea(u8);}\n"
        code += "namespace StageLoader {bool fastAnyStart(int){return false;}}\n"
        code += re.search(r"(?:constexpr|const) u8 kParentAreas\[\].*?\n};", warp, re.S).group(0)
        code += function(warp, "LevelWarp::parentArea")
        code += source[source.index("enum FinishKind {"):source.index("constexpr u8 kGroupFirst")]
        code += re.search(r"const u8 kAnyPercentTheorySlots\[\] = \{.*?\n};", source, re.S).group(0)
        code += "u8 sEpisodeChoices[SUSAMUNE_IL_EPISODE_COUNT];\n"
        code += "LevelWarp::Dest sAttemptStart,sOnlineStart;bool sOnlineStartValid;int sOnlineEntry;\n"
        code += re.search(r"const int kEntryNoki3Inside = \d+;", source).group(0)
        for name in ("validEntry", "pbSlot", "episodeChoiceIndex", "parentOrSelf", "selectedStart"):
            code += function(source, name)
        code += "namespace ILing {\n"
        code += "bool start(int entry){sAttemptStart=selectedStart(entry);return true;}\n"
        code += "bool copyWarpDiscardName(int,char*,u32,u32*){return false;}\n"
        for name in ("onlinePoolContains", "canChooseEpisode", "choosesPlazaState", "onlineDefaultEpisode", "startOnline"):
            code += function(source, name)
        code += "}\n"
        code += r'''
#define API extern "C" __declspec(dllexport)
API unsigned contains(int entry,unsigned pool){return ILing::onlinePoolContains(entry,pool);}
API unsigned count(){return kEntryCount;}
API int defaultEpisode(int entry){return ILing::onlineDefaultEpisode(entry);}
API unsigned original(int entry){const auto d=kEntries[entry].start;return (d.area<<16)|(d.episode<<8)|d.gameInt3;}
API unsigned defaultRoute(int entry,unsigned previous){
    for(auto &choice:sEpisodeChoices)choice=previous;
    if(!ILing::startOnline(entry,ILing::onlineDefaultEpisode(entry)))return ~0u;
    for(auto choice:sEpisodeChoices)if(choice!=previous)return ~0u;
    if(!sOnlineStartValid||sOnlineEntry!=entry)return ~0u;
    const auto d=sOnlineStart;return (d.area<<16)|(d.episode<<8)|d.gameInt3;
}
'''
        path = Path(cls.folder.name) / "pools.cpp"
        path.write_text(code, encoding="ascii")
        library = path.with_suffix(".dll")
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-std=c++17", "-O2", "-fno-exceptions", "-fno-rtti", "-ffreestanding",
            "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
            "-I", str(ROOT / "include"), "-I", str(ROOT / "src"), str(path), "-o", str(library),
        ], check=True)
        cls.dll = C.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.dll._handle)
        cls.dll.contains.argtypes = [C.c_int, C.c_uint]
        cls.dll.contains.restype = C.c_uint
        cls.dll.defaultRoute.argtypes = [C.c_int, C.c_uint]
        cls.dll.defaultRoute.restype = C.c_uint

    def pool(self, pool):
        return {label for entry, label in enumerate(self.labels) if self.dll.contains(entry, pool)}

    def test_complete_catalogue_membership(self):
        self.assertEqual((self.dll.count(), len(self.labels)), (133, 133))
        self.assertEqual(self.pool(ANY), ANY_ENTRIES)
        self.assertEqual(self.pool(ALL), set(self.labels) - BANNED)
        self.assertEqual(self.pool(NON_ANY), set(self.labels) - BANNED - ANY_ENTRIES)
        self.assertEqual([len(self.pool(pool)) for pool in (ANY, ALL, NON_ANY)], [60, 128, 68])

    def test_shared_bans_and_invalid_values(self):
        for label in BANNED:
            for pool in (ANY, ALL, NON_ANY):
                self.assertFalse(self.dll.contains(self.labels.index(label), pool), (label, pool))
        for entry in (-1, 133, 1000):
            for pool in (ANY, ALL, NON_ANY):
                self.assertFalse(self.dll.contains(entry, pool))
        for pool in (3, 255, 0xffffffff):
            for entry in range(133):
                self.assertFalse(self.dll.contains(entry, pool))

    def test_any_and_non_any_partition_all_without_leaking_movement(self):
        any_entries, all_entries, non_any = self.pool(ANY), self.pool(ALL), self.pool(NON_ANY)
        self.assertFalse(any_entries & non_any)
        self.assertEqual(any_entries | non_any, all_entries)
        for label in ("Bianco Plant", "Delfino Shadow Mario", "Travel Skip", "Gelato Plant",
                      "Pianta Enter", "Honey Skip", "Ricco Enter", "Sirena Enter", "Corona Enter"):
            self.assertIn(label, any_entries)
            self.assertNotIn(label, non_any)
        self.assertIn("Gelato Enter", non_any)

    def test_only_secret_variants_extend_exact_any_route(self):
        secrets = {label for label in self.labels if label.endswith("(Secret)")}
        self.assertEqual(self.pool(ANY) & secrets, secrets - {"Gelato 1 (Secret)"})
        self.assertIn("Pinna Park EYG", self.pool(ANY))
        self.assertIn("Pinna 6 (Secret)", self.pool(ANY))
        self.assertIn("Gelato GBS", self.pool(ANY))
        for label in ("Pinna 6 (Full)", "Gelato 8", "Ricco 2 (Race)", "Noki 4 (Eel Only)",
                      "Bowser", "Gelato 1 (Full)", "Gelato 1 (Secret)", "Pinna 5"):
            self.assertNotIn(label, self.pool(ANY))
            self.assertIn(label, self.pool(NON_ANY))

    def test_bonus_and_full_reds_do_not_inherit_the_parent_secret(self):
        for label in self.labels:
            if "Reds" in label or "100" in label or "Hidden" in label:
                self.assertNotIn(label, self.pool(ANY))
                self.assertIn(label, self.pool(NON_ANY))

    def test_default_online_start_preserves_every_catalogue_destination_and_saved_choice(self):
        for entry, label in enumerate(self.labels):
            for previous in range(9):
                self.assertEqual(self.dll.defaultRoute(entry, previous), self.dll.original(entry),
                                 (label, previous))
        self.assertEqual(self.dll.defaultEpisode(self.labels.index("Bianco 100 (E6)")), 5)
        self.assertEqual(self.dll.defaultEpisode(self.labels.index("Bianco 3 Full Reds")), 2)
        self.assertEqual(self.dll.defaultEpisode(self.labels.index("Pinna 6 Full Reds")), 5)
        self.assertEqual(self.dll.defaultEpisode(self.labels.index("Gelato Enter")), 3)
        for invalid in (-1, 133, 1000):
            self.assertEqual(self.dll.defaultEpisode(invalid), -1)
            self.assertEqual(self.dll.defaultRoute(invalid, 8), 0xffffffff)


if __name__ == "__main__":
    unittest.main()
