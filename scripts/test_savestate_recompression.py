"""Use the production codec and save commit helper at temporary capacity limits."""

import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import zlib

from test_native_timer_creation import function
from test_state_codec import Guarded, Span, Result
from test_state_slot_pool import Pool, Entry, metadata
from test_state_pool_memory import Memory

ROOT = Path(__file__).resolve().parents[1]


class SavestateRecompressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-recompress-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "commit.cpp"
        production = (ROOT / "src/savestate.cpp").read_text()
        helper = function(production, "commitPackedState")
        # A trap remains fatal in production; record it here without crashing
        # the host so the test can inspect that no slot was published afterward.
        helper = helper.replace("__builtin_trap()", "return trapped()")
        helper = helper.replace("StateCodec::compress(", "testCompress(")
        source.write_text(r'''
#include "susamune/state_codec.hxx"
#include "susamune/state_slot_pool.h"
#include "susamune/state_pool_memory.h"
typedef unsigned int u32;typedef unsigned char u8;
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int c,__SIZE_TYPE__ n){u8*a=(u8*)d;while(n--)*a++=(u8)c;return d;}
extern "C" int memcmp(const void*a,const void*b,__SIZE_TYPE__ n){const u8*x=(const u8*)a,*y=(const u8*)b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;}
u32 capacity,stagingSize;
#define SUSAMUNE_STATE_POOL_SIZE capacity
#define SUSAMUNE_STATE_STAGING_SIZE stagingSize
#define SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE 0x50000u
StateSlotPool sPool;StatePoolMemory sPoolMemory;u8 *staging;void *work;
#define kStagingBase staging
void *codecWorkspace(){return work;}
int fault,trapCount,secondCalls;
bool trapped(){++trapCount;return false;}
StateCodec::Result testCompress(void*w,u32 n,const StateCodec::ReadSpan*s,u32 count,const StateCodec::WriteSpan*d){
 ++secondCalls;StateCodec::Result r=StateCodec::compress(w,n,s,count,d);
 if(fault==1)r.status=StateCodec::CODEC_ERROR;
 if(fault==2)++r.rawBytes;
 if(fault==3)++r.compressedBytes;
 if(fault==4)r.adler32^=1;
 return r;
}
''' + function(production, "poolCapacity") + function(production, "poolWriteSpans") + helper + r'''
extern "C" __declspec(dllexport) int run(StateSlotPool*p,StatePoolMemory*m,u32 cap,u8*t,u32 ts,
 void*w,const StateCodec::ReadSpan*s,u32 count,u32 raw,u32 slot,int bad,StateCodec::Result*out,int*calls){
 sPool=*p;sPoolMemory=*m;capacity=cap;staging=t;stagingSize=ts;work=w;fault=bad;trapCount=secondCalls=0;
 StateCodec::WriteSpan destination[3]={{t,ts},{0,0},{0,0}};
 poolWriteSpans(p->used,cap-p->used,destination+1);
 *out=StateCodec::compress(w,SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE,s,count,destination,3);
 bool ok=commitPackedState(s,count,raw,slot,*out);
 *p=sPool;*calls=secondCalls;return trapCount?-1:ok;
}
''', encoding="ascii")
        dll = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-fno-builtin", "-mno-stack-arg-probe", "-I", str(ROOT / "include"),
                        str(source), str(ROOT / "src/state_codec.cpp"), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        from _ctypes import FreeLibrary
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)
        cls.lib.run.argtypes = [C.POINTER(Pool), C.POINTER(Memory), C.c_uint, C.c_void_p,
            C.c_uint, C.c_void_p, C.POINTER(Span), C.c_uint, C.c_uint, C.c_uint,
            C.c_int, C.POINTER(Result), C.POINTER(C.c_int)]

    def execute(self, size, slot=1, fault=0, raw_offset=0):
        capacity = 220000
        pool = Pool((Entry * 3)(Entry(0, 70000), Entry(70000, 70000), Entry(140000, 70000)), 210000)
        buffers = [Guarded(150000), Guarded(70000)]
        memory = Memory((C.c_void_p * 2)(*[b.ptr for b in buffers]), (C.c_uint * 2)(150000, 70000))
        staging, work = Guarded(4096), Guarded(0x50000)
        originals = [bytes([31 + i * 29]) * 70000 for i in range(3)]
        initial = b"".join(originals) + bytes(10000)
        C.memmove(buffers[0].ptr, initial[:150000], 150000)
        C.memmove(buffers[1].ptr, initial[150000:], 70000)
        def read(offset, size):
            return b"".join(b.data() for b in buffers)[offset:offset + size]
        old = metadata(pool), read(0, pool.used)
        data = random.Random(173).randbytes(size)
        owner = C.create_string_buffer(data)
        source = (Span * 2)(Span(C.addressof(owner), size // 2),
                            Span(C.addressof(owner) + size // 2, size - size // 2))
        result, calls = Result(), C.c_int()
        status = self.lib.run(C.byref(pool), C.byref(memory), capacity, staging.ptr, staging.size,
                             work.ptr, source, 2, len(data) + raw_offset, slot, fault,
                             C.byref(result), C.byref(calls))
        self.assertTrue(all(b.guards() for b in buffers) and staging.guards() and work.guards())
        self.assertEqual(result.raw, len(data))
        self.assertEqual(result.adler, zlib.adler32(data))
        if status == 1:
            selected = pool.slots[slot]
            self.assertEqual(selected.size, result.compressed)
            self.assertEqual(zlib.decompress(read(selected.offset, selected.size)), data)
        else:
            if status == 0:
                self.assertEqual((metadata(pool), read(0, pool.used)), old)
            else:
                self.assertEqual(pool.slots[slot].size, 0)
        for i, entry in enumerate(pool.slots):
            if i != slot:
                self.assertEqual(read(entry.offset, entry.size), originals[i])
        return status, calls.value, result.status

    def test_full_temporary_buffer_recompresses_into_replaced_slot_for_each_slot(self):
        for slot in range(3):
            self.assertEqual(self.execute(65000, slot), (1, 1, 3))

    def test_staged_success_uses_one_pass(self):
        self.assertEqual(self.execute(1000), (1, 0, 0))

    def test_true_capacity_or_incomplete_count_failure_keeps_all_original_states(self):
        self.assertEqual(self.execute(90000), (0, 0, 3))
        self.assertEqual(self.execute(65000, raw_offset=1), (0, 0, 3))

    def test_second_pass_status_size_raw_and_checksum_mismatch_trap_without_publication(self):
        for fault in range(1, 5):
            self.assertEqual(self.execute(65000, fault=fault), (-1, 1, 3))


if __name__ == "__main__":
    unittest.main()
