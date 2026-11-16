"""Semantic initial FlagManager decoding, bounded apply, and trusted restoration."""
import ctypes as C
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CARD_DEFAULTS = [0, 3, 3500, 3000, 3000] + [0] * 15 + [4000]
COUNTS = (948, 21, 29, 5, 100, 100)
TOTAL = sum(COUNTS)
HUMAN_CARD_BITS = (
    [900, 901, 902, 903, 914, 922, 925, 933, 934, 939, 942],
    [43, 900, 901, 902, 903, 914, 918, 922, 925, 933, 934, 939, 941, 942],
)

class Snapshot(C.Structure):
    _fields_ = [
        ("cardInts", C.c_int * 21), ("gameInts", C.c_int * 5),
        ("stageInts", C.c_int * 100), ("cardBools", C.c_ubyte * 119),
        ("gameBools", C.c_ubyte * 4), ("stageBools", C.c_ubyte * 13),
    ]

DRIVER = r'''
#include "susamune/ghost_trace_initial_flags.hxx"
#include <string.h>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif
namespace F = GhostTraceInitialFlags;
static int live[6][1024];
static unsigned reads, writes, invalid;
static unsigned counts[6] = {948,21,29,5,100,100};
static int* field(unsigned id) {
    unsigned group=(id>>16)-1,index=id&0xffffu;
    if(group>=6||index>=counts[group]) {++invalid;return nullptr;}
    return &live[group][index];
}
static int get(void*,unsigned id) {++reads;int*p=field(id);return p?*p:0;}
static void set(void*,unsigned id,int value) {++writes;int*p=field(id);if(p)*p=value;}
static F::Access access(unsigned mode) {return {nullptr,mode&1?nullptr:get,mode&2?nullptr:set};}
API void reset() {memset(live,0,sizeof(live));reads=writes=invalid=0;}
API void counters() {reads=writes=invalid=0;}
API unsigned counter(unsigned n) {return n==0?reads:n==1?writes:invalid;}
API void put(unsigned id,int value) {int*p=field(id);if(p)*p=value;}
API int peek(unsigned id) {int*p=field(id);return p?*p:0;}
API int decodeFlags(void*out,const void*raw,unsigned bytes,unsigned count) {
    return F::decode(*(F::Snapshot*)out,(const unsigned char*)raw,bytes,count);
}
API int matches(const void*p,unsigned bytes,unsigned mode){return F::matchesImage((const unsigned char*)p,bytes,access(mode));}
API int validFlags(const void*p,unsigned count) {return F::validate(*(const F::Snapshot*)p,count);}
API int captureFlags(void*out,unsigned mode) {return F::capture(*(F::Snapshot*)out,access(mode));}
API int applyFlags(const void*p,unsigned count,unsigned mode) {return F::apply(*(const F::Snapshot*)p,count,access(mode));}
API int restoreFlags(const void*p,unsigned mode) {return F::restore(*(const F::Snapshot*)p,access(mode));}
'''

def wire(noki=False):
    data = bytearray(896)
    struct.pack_into(">21i", data, 0x78, *CARD_DEFAULTS)
    struct.pack_into(">5i", data, 0xd0, int(noki), 0, 0, 3, 4)
    struct.pack_into(">i", data, 0xf4 + 3 * 4, 1)
    for bit in HUMAN_CARD_BITS[int(noki)]:
        data[bit >> 3] |= 1 << (bit & 7)
    for bit in ([0, 3, 6, 7, 9] if noki else [3, 6, 7, 9]):
        data[0xcc + (bit >> 3)] |= 1 << (bit & 7)
    return data

def set_bit(snapshot, name, bit):
    values = getattr(snapshot, name)
    values[bit >> 3] |= 1 << (bit & 7)

def expected(snapshot):
    result = {}
    for group, name, count in ((1, "cardBools", 948), (3, "gameBools", 29), (5, "stageBools", 100)):
        bits = getattr(snapshot, name)
        for i in range(count):
            result[(group << 16) + i] = (bits[i >> 3] >> (i & 7)) & 1
    for group, name in ((2, "cardInts"), (4, "gameInts"), (6, "stageInts")):
        for i, value in enumerate(getattr(snapshot, name)):
            result[(group << 16) + i] = value
    return result

class InitialFlagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pr59-flags-")
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        (directory / "driver.cpp").write_text(DRIVER)
        compiler = os.environ.get("CXX") or shutil.which("g++")
        if not compiler and Path("C:/msys64/mingw64/bin/g++.exe").exists():
            compiler = "C:/msys64/mingw64/bin/g++.exe"
        if not compiler:
            raise RuntimeError("C++ host compiler unavailable")
        output = directory / ("flags.dll" if os.name == "nt" else "flags.so")
        command = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-shared",
                   "-I", str(ROOT / "include"), str(directory / "driver.cpp"),
                   str(ROOT / "src/ghost_trace_initial_flags.cpp"), "-o", str(output)]
        command.insert(1, "-static" if os.name == "nt" else "-fPIC")
        environment = os.environ.copy()
        environment["PATH"] = str(Path(compiler).parent) + os.pathsep + environment.get("PATH", "")
        result = subprocess.run(command, capture_output=True, text=True, env=environment)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(output))
        if os.name == "nt":
            cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        for name in ("captureFlags", "restoreFlags"):
            getattr(cls.lib, name).argtypes = [C.c_void_p, C.c_uint]
        cls.lib.applyFlags.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
        cls.lib.matches.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
        cls.lib.validFlags.argtypes = [C.c_void_p, C.c_uint]
        cls.lib.decodeFlags.argtypes = [C.c_void_p, C.c_void_p, C.c_uint, C.c_uint]
        cls.lib.put.argtypes = [C.c_uint, C.c_int]
        cls.lib.peek.argtypes = [C.c_uint]
        cls.lib.counter.argtypes = [C.c_uint]
        cls.lib.counter.restype = C.c_uint

    def setUp(self):
        self.lib.reset()

    def decode(self, data=None, count=8):
        data = wire() if data is None else data
        snapshot = Snapshot()
        raw = C.create_string_buffer(bytes(data))
        self.assertEqual(self.lib.decodeFlags(C.byref(snapshot), raw, len(data), count), 1)
        return snapshot

    def assert_no_writes(self):
        self.assertEqual(self.lib.counter(1), 0)
        self.assertEqual(self.lib.counter(2), 0)

    def test_transition_comparison_ignores_only_wire_padding_and_never_writes(self):
        value=self.decode();self.assertTrue(self.lib.applyFlags(C.byref(value),8,0));self.lib.counters()
        data=wire();data[119]=255;data[0xcf]|=0xe0;data[0xf0]|=0xf0;data[0xf1:0xf4]=bytes([255]*3);data[0x284:]=bytes([255]*(896-0x284))
        self.assertTrue(self.lib.matches(bytes(data),896,0));self.assert_no_writes()
        self.lib.put(0x60063,123456);struct.pack_into('>i',data,0xf4+99*4,123456)
        self.assertTrue(self.lib.matches(bytes(data),896,0));self.assert_no_writes()
        data[0x10]^=1;self.assertFalse(self.lib.matches(bytes(data),896,0));self.assert_no_writes()
    def test_transition_comparison_rejects_missing_access_and_truncated_image(self):
        self.assertFalse(self.lib.matches(bytes(wire()),895,0));self.assertFalse(self.lib.matches(bytes(wire()),896,1));self.assert_no_writes()

    def test_human_sirena_and_noki_initial_projections(self):
        self.assertEqual(C.sizeof(Snapshot), 640)
        for noki in (False, True):
            value = self.decode(wire(noki))
            self.assertEqual(list(value.cardInts), CARD_DEFAULTS)
            self.assertEqual(list(value.gameInts), [int(noki), 0, 0, 3, 4])
            self.assertEqual([(i, x) for i, x in enumerate(value.stageInts) if x], [(3, 1)])
            self.assertEqual(self.lib.validFlags(C.byref(value), 8), 1)

    def test_exact_wire_length_null_and_failed_decode_keep_output(self):
        output = Snapshot()
        C.memset(C.byref(output), 0x5a, C.sizeof(output))
        before = bytes(output)
        raw = C.create_string_buffer(bytes(wire()) + b"x")
        for pointer, size in ((None, 896), (raw, 0), (raw, 895), (raw, 897)):
            self.assertEqual(self.lib.decodeFlags(C.byref(output), pointer, size, 8), 0)
            self.assertEqual(bytes(output), before)
        data = wire()
        struct.pack_into(">i", data, 0xf4 + 99 * 4, -1)
        raw = C.create_string_buffer(bytes(data))
        self.assertEqual(self.lib.decodeFlags(C.byref(output), raw, 896, 8), 0)
        self.assertEqual(bytes(output), before)
        self.assert_no_writes()

    def test_wire_padding_options_timestamps_and_backups_are_ignored(self):
        normal = self.decode()
        data = wire()
        data[0x77] = 0xff
        data[0x76] |= 0xf0
        data[0xcf] |= 0xe0
        data[0xf0] |= 0xf0
        data[0xf1:0xf4] = b"\xff" * 3
        data[0x284:] = b"\xff" * (896 - 0x284)
        self.assertEqual(bytes(self.decode(data)), bytes(normal))

    def test_native_apply_uses_only_exact_audited_ids(self):
        value = self.decode(wire(True))
        set_bit(value, "cardBools", 947)
        set_bit(value, "gameBools", 28)
        set_bit(value, "stageBools", 99)
        for id in expected(value):
            self.lib.put(id, 7)
        self.lib.counters()
        self.assertEqual(self.lib.applyFlags(C.byref(value), 8, 1), 1)
        self.assertEqual(self.lib.counter(1), TOTAL)
        self.assertEqual(self.lib.counter(0), 0)
        self.assertEqual(self.lib.counter(2), 0)
        for id, data in expected(value).items():
            self.assertEqual(self.lib.peek(id), data, hex(id))

    def test_validate_whole_candidate_before_first_setter(self):
        value = self.decode()
        value.stageInts[99] = 1
        self.assertEqual(self.lib.applyFlags(C.byref(value), 8, 0), 0)
        self.assert_no_writes()
        self.assertEqual(self.lib.counter(0), 0)

    def test_semantic_padding_is_rejected_on_apply(self):
        for name, last, mask in (("cardBools", 118, 0x10), ("gameBools", 3, 0x20), ("stageBools", 12, 0x10)):
            value = self.decode()
            getattr(value, name)[last] |= mask
            self.assertEqual(self.lib.applyFlags(C.byref(value), 8, 0), 0)
            self.assert_no_writes()

    def test_saved_record_values_and_lives_are_bounded(self):
        limits=[0x7ffffffe,99,3500,3000,3000]+[999]*15+[4000]
        for index,limit in enumerate(limits):
            for amount,valid in ((0,1),(limit,1),(-1,0),(limit+1,0)):
                value=self.decode();value.cardInts[index]=amount
                self.assertEqual(self.lib.validFlags(C.byref(value),8),valid,(index,amount))

    def test_real_saved_records_do_not_require_new_file_defaults(self):
        data=wire();records=(4,5,3500,1984,3000,0,1,3,19,0,4,0,2,1,0,0,0,0,0,0,1985)
        struct.pack_into('>21i',data,0x78,*records)
        value=self.decode(data)
        self.assertEqual(tuple(value.cardInts),records)
        self.assertEqual(self.lib.applyFlags(C.byref(value),8,0),1)
        self.assertEqual(self.lib.counter(2),0)

    def test_stage_integers_admit_only_audited_initial_values(self):
        for index in range(100):
            if index in (0, 3):
                continue
            value = self.decode()
            value.stageInts[index] = 1
            self.assertEqual(self.lib.validFlags(C.byref(value), 8), 0, index)
        value = self.decode()
        for stage, valid in ((-1, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 0), (2**31 - 1, 0)):
            value.stageInts[3] = stage
            self.assertEqual(self.lib.validFlags(C.byref(value), 8), valid)

    def test_caller_scenario_bound_is_required_and_not_guessed(self):
        value = self.decode()
        for count, valid in ((0, 0), (3, 0), (4, 1), (8, 1), (256, 1), (257, 0)):
            self.assertEqual(self.lib.validFlags(C.byref(value), count), valid)
        value.gameInts[3] = 9
        self.assertEqual(self.lib.validFlags(C.byref(value), 8), 0)
        self.assertEqual(self.lib.validFlags(C.byref(value), 10), 1)
        value.gameInts[3] = 0
        self.assertEqual(self.lib.validFlags(C.byref(value), 1), 1)
        value.gameInts[3] = -1
        self.assertEqual(self.lib.validFlags(C.byref(value), 10), 0)

    def test_previous_red_coin_count_and_underwater_nozzle_are_valid_at_entry(self):
        raw=wire(True)
        struct.pack_into(">i",raw,0xd0+4*4,2)
        struct.pack_into(">i",raw,0xf4,2)
        value=self.decode(raw)
        self.assertEqual((value.gameInts[4],value.stageInts[0]),(2,2))
        for count,valid in ((0,1),(8,1),(-1,0),(9,0)):
            value.stageInts[0]=count
            self.assertEqual(self.lib.validFlags(C.byref(value),8),valid)

    def test_nozzle_admission_excludes_unchecked_and_yoshi_entries(self):
        value = self.decode()
        for nozzle in range(-1, 9):
            value.gameInts[4] = nozzle
            self.assertEqual(self.lib.validFlags(C.byref(value), 8), int(nozzle in (0, 1, 2, 4, 5)), nozzle)

    def test_coin_limit_and_signed_big_endian_admission(self):
        value = self.decode()
        for coins, valid in ((-2**31, 0), (-1, 0), (0, 1), (999, 1), (1000, 0), (2**31 - 1, 0)):
            value.gameInts[2] = coins
            self.assertEqual(self.lib.validFlags(C.byref(value), 8), valid)
        for offset in (0x78, 0xd0, 0xf4):
            data = wire()
            struct.pack_into(">I", data, offset, 0x80000000)
            output = Snapshot()
            raw = C.create_string_buffer(bytes(data))
            self.assertEqual(self.lib.decodeFlags(C.byref(output), raw, len(data), 8), 0)

    def test_counters_are_bounded_independently_of_respawned_flags(self):
        value = self.decode()
        for bit in range(870):
            set_bit(value, "cardBools", bit)
        value.gameInts[0], value.gameInts[1] = 120, 750
        self.assertEqual(self.lib.validFlags(C.byref(value), 8), 1)
        for bit in (870, 947):
            set_bit(value, "cardBools", bit)
        self.assertEqual(self.lib.validFlags(C.byref(value), 8), 1)
        for index, changed in ((0, 121), (1, 751), (0, -1), (1, -1)):
            original = value.gameInts[index]
            value.gameInts[index] = changed
            self.assertEqual(self.lib.validFlags(C.byref(value), 8), 0)
            value.gameInts[index] = original

    def test_respawned_shine_keeps_the_recorded_total(self):
        value=self.decode()
        for bit in range(45):set_bit(value,"cardBools",bit)
        value.gameInts[0]=46
        self.assertEqual(self.lib.applyFlags(C.byref(value),8,0),1)
        self.assertEqual(self.lib.peek(0x40000),46)
        self.assertEqual(self.lib.peek(0x1002d),0)

    def test_capture_and_restore_preserve_trusted_values_outside_admission(self):
        incoming = self.decode()
        trusted = expected(incoming)
        for id in trusted:
            group, index = id >> 16, id & 0xffff
            if group & 1:
                trusted[id] = (group + index) & 1
            else:
                trusted[id] = (-2**31, -1, 2**31 - 1, 123456789)[index % 4]
            self.lib.put(id, trusted[id])
        self.lib.counters()
        backup = Snapshot()
        self.assertEqual(self.lib.captureFlags(C.byref(backup), 2), 1)
        self.assertEqual(self.lib.counter(0), TOTAL)
        self.assert_no_writes()
        self.assertEqual(self.lib.validFlags(C.byref(backup), 8), 0)
        self.assertEqual(self.lib.applyFlags(C.byref(incoming), 8, 0), 1)
        self.lib.counters()
        self.assertEqual(self.lib.restoreFlags(C.byref(backup), 1), 1)
        self.assertEqual(self.lib.counter(1), TOTAL)
        self.assertEqual(self.lib.counter(2), 0)
        for id, data in trusted.items():
            self.assertEqual(self.lib.peek(id), data, hex(id))

    def test_callback_admission_does_not_mutate_output_or_live_values(self):
        value = self.decode()
        output = Snapshot()
        C.memset(C.byref(output), 0xa5, C.sizeof(output))
        before = bytes(output)
        self.assertEqual(self.lib.captureFlags(C.byref(output), 1), 0)
        self.assertEqual(bytes(output), before)
        self.assertEqual(self.lib.applyFlags(C.byref(value), 8, 2), 0)
        self.assertEqual(self.lib.restoreFlags(C.byref(value), 2), 0)
        self.assert_no_writes()
        self.lib.put(0x50063, 2)
        self.lib.counters()
        self.assertEqual(self.lib.captureFlags(C.byref(output), 0), 0)
        self.assertEqual(bytes(output), before)
        self.assert_no_writes()

if __name__ == "__main__":
    unittest.main()
