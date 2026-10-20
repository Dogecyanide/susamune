"""Prove direct Quick producer admission and decoding; capacity uses exact PPC streams."""
import argparse
import ctypes as C
import json
from pathlib import Path
import struct
import zlib

from test_state_codec import Guarded, Span, Result
from test_timewarp_staged_transaction import StageHarness, StagePool, StageMemory, Token
from timewarp_root_codec import RootCodec, ppc_budget
from timewarp_state_measure import FRAME, quick_blocks
import timewarp_multibank_pool as measurement

ROOT = measurement.ROOT
EXTRA = r'''
#include "susamune/state_quick_producer.hxx"
struct Reject { TWQuickProducer producer; unsigned count, stop; };
static bool rejectEmit(void *ctx,const StateCodec::ReadSpan(&s)[2]) {
 Reject *r=(Reject*)ctx;
 return r->count++ != r->stop && TWQuickEmit(&r->producer,s);
}
extern "C" {
__declspec(dllexport) int parts(TWStageMemory*m,TWStageToken*t,const unsigned char*h,unsigned hn,const unsigned char*p,unsigned pn) {
 return TWRAppendParts(m,*t,h,hn,p,pn);
}
__declspec(dllexport) void produce(TWStageMemory*m,TWStageToken*t,void*w,unsigned wn,const StateCodec::ReadSpan*s,unsigned sn,unsigned stop,StateCodec::Result*out,unsigned*calls) {
 if(stop==~0u) {*out=TWQuickProduce(m,*t,w,wn,s,sn);*calls=TWChunkDirectory(m->pool)->slots[3].count;return;}
 StateCodec::WriteSpan dst[TW_BANK_MAX+1];unsigned n=m->pool->count;
 for(unsigned i=0;i<n;++i)dst[i]={m->pool->banks[i],m->pool->sizes[i]};
 if(m->size)dst[n++]={m->staging,m->size};
 Reject context={{m,*t},0,stop};
 *out=StateCodec::compressQuickBlocks(w,wn,s,sn,dst,n,rejectEmit,&context);*calls=context.count;
}
__declspec(dllexport) void whole(void*w,unsigned wn,const StateCodec::ReadSpan*s,unsigned sn,const StateCodec::WriteSpan*d,unsigned dn,StateCodec::Result*out) {
 *out=StateCodec::compress(w,wn,s,sn,d,dn,false,true);
}
}
'''


class ProducerCodec(RootCodec):
    def __init__(self, folder):
        super().__init__(folder, EXTRA)
        ptr, u, spans = C.c_void_p, C.c_uint, C.POINTER(Span)
        self.lib.parts.argtypes = [C.POINTER(StageMemory), C.POINTER(Token), ptr, u, ptr, u]
        self.lib.produce.argtypes = [C.POINTER(StageMemory), C.POINTER(Token), ptr, u, spans, u, u,
                                    C.POINTER(Result), C.POINTER(u)]
        self.lib.whole.argtypes = [ptr, u, spans, u, spans, u, C.POINTER(Result)]

    def parts(self, pool, block):
        header, payload = C.create_string_buffer(block[:8]), C.create_string_buffer(block[8:])
        return self.call(pool, "parts", C.byref(pool.token), header, 8, payload, len(block) - 8)

    def encode(self, pool, raw, tag, stop=0xffffffff):
        source = Guarded(len(raw))
        C.memmove(source.ptr, raw, len(raw))
        cut = min(len(raw) // 2, 0x20000 + 31)
        spans = (Span * 2)(Span(source.ptr, cut), Span(source.ptr + cut, len(raw) - cut))
        result, calls = Result(), C.c_uint()
        self.call(pool, "produce", C.byref(pool.token), self.work.ptr, self.work.size, spans, 2,
                  stop, C.byref(result), C.byref(calls))
        assert source.data() == raw and source.guards() and self.work.guards()
        pool.canaries()
        if result.status:
            assert not result.compressed and not result.adler
            return result, calls.value, None
        pending = pool.directory.slots[3]
        blocks = [pool.block(i - 1) for i in pending.ids[:pending.count]]
        encoded = FRAME + b"".join(blocks)
        assert (result.raw, result.compressed, result.adler) == (len(raw), len(encoded), zlib.adler32(raw))
        output = Guarded(len(raw) + 8 * ((len(raw) + 0x1ffff) // 0x20000) + 8)
        target = (Span * 1)(Span(output.ptr, output.size))
        baseline = Result()
        self.lib.whole(self.work.ptr, self.work.size, spans, 2, target, 1, C.byref(baseline))
        assert baseline.status == 0 and encoded == output.data()[:baseline.compressed]
        assert output.guards() and self.work.guards() and source.data() == raw
        quick_blocks(encoded, raw)
        return result, calls.value, {"raw": raw, "blocks": blocks, "expected": (encoded, tag, len(raw))}


def create(harness, config, states):
    pool = StagePool(harness, sizes=[b["size"] for b in config["banks"]],
                     guest_bases=[b["ppc_address"] for b in config["banks"]])
    for slot, state in enumerate(states): assert pool.put(slot, state["blocks"], state["expected"][1])
    return pool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-pool-producer/validated")
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()) or folder.exists():
        parser.error("Use a fresh private build directory")
    folder.mkdir(parents=True)
    (folder / "allocator").mkdir()
    names = [f"include/susamune/{name}" for name in ("state_multibank_memory.h", "state_chunk_pool.h",
        "state_staged_transaction.h", "state_root_reader.h", "state_quick_producer.hxx", "state_codec.hxx")]
    names += ["src/state_codec.cpp", "src/qft_timer.cpp", "scripts/timewarp_pool_producer.py",
              "scripts/timewarp_root_codec.py"]
    before = {name: measurement.sha(ROOT / name) for name in names}
    codec, harness = ProducerCodec(folder), StageHarness(folder / "allocator")
    report = {"scope": "Production encoder-to-pool-to-decoder composition on native host; native encoded sizes are not PPC ratios. Bank capacity and split-parts transaction replay use the exact measured PPC streams separately. No game owner restore, activation, ARM cache or Wii speed proof.",
              "source_sha256": before, "capacity": [], "PPC_replacements": [], "native_producers": []}
    try:
        report["PPC_directory_budget"] = ppc_budget(folder)
        measurement.INPUTS = (*measurement.INPUTS, ROOT / "build/timewarp-stress-measure/receipt.json",
                              ROOT / "build/timewarp-noki1-measure/receipt.json")
        groups, report["input_receipts"] = measurement.inputs()
        configs, report["transaction"] = measurement.banks(harness)
        report["bank_layouts"] = configs
        config = configs[1]
        for group in groups:
            for layout in configs:
                row = measurement.replay(harness, layout, group, [])
                report["capacity"].append(row)
            print(json.dumps({"capacity": group["name"], "four_bank_extent": report["capacity"][-2]["compacted"]["occupied_extent_bytes"]}), flush=True)
            # Same-slot native replacements exercise the production callback and reader.
            pool = create(harness, config, group["states"])
            current = list(group["states"])
            for target, original in enumerate(group["states"]):
                old = pool.states()
                assert codec.guarded_begin(pool, target)
                result, calls, candidate = codec.encode(pool, original["raw"], original["expected"][1])
                assert pool.states() == old
                accepted = False
                checks = []
                if candidate:
                    checks = codec.decode(pool, 3, candidate, test_guards=True)
                    accepted = bool(codec.guarded_commit(pool, candidate))
                if accepted: current[target] = candidate
                else: assert codec.call(pool, "gx", C.byref(pool.token))
                final_checks = [codec.decode(pool, slot, state) for slot, state in enumerate(current)]
                report["native_producers"].append({"set": group["name"], "target": target, "callbacks": calls,
                    "status": result.status, "candidate_complete": bool(candidate), "committed": accepted,
                    "candidate_checks": checks, "all_three_after": final_checks,
                    "old_roots_preserved_until_commit": True, "no_extra_block_buffer": True})
                print(json.dumps({"native_producer": group["name"], "target": target, "status": result.status, "committed": accepted}), flush=True)
        named = {g["name"]: g for g in groups}
        cases = [(named["mixed"], f"late-Gelato-{i+1}", named["same-level"]["states"][i]) for i in (1, 2)]
        cases += [(g, groups[(i+1) % len(groups)]["name"], groups[(i+1) % len(groups)]["states"][0])
                  for i, g in enumerate(groups) if g["name"] != "mixed"]
        cases += [(named[a], b, named[b]["states"][0]) for a, b in
                  (("bianco5", "pinna3"), ("pinna3", "bianco5"), ("noki1", "bianco5"))]
        for group, label, candidate in cases:
            for layout in configs[1:]:
                for target in range(3):
                    pool = create(harness, layout, group["states"])
                    old = pool.states()
                    for after in range(len(candidate["blocks"]) + 1):
                        assert codec.guarded_begin(pool, target)
                        for block in candidate["blocks"][:after]:
                            if not codec.parts(pool, block): break
                        assert codec.call(pool, "gx", C.byref(pool.token))
                        assert pool.states() == old
                        pool.canaries()
                    assert codec.guarded_begin(pool, target)
                    complete = all(codec.parts(pool, block) for block in candidate["blocks"])
                    checks = codec.decode(pool, 3, candidate) if complete else []
                    accepted = complete and bool(codec.guarded_commit(pool, candidate))
                    states = list(group["states"])
                    if accepted: states[target] = candidate
                    else: assert codec.call(pool, "gx", C.byref(pool.token))
                    final_checks = [codec.decode(pool, slot, state) for slot, state in enumerate(states)]
                    report["PPC_replacements"].append({"set": group["name"], "candidate": label, "target": target,
                        "layout": layout["name"], "complete": complete, "accepted": bool(accepted),
                        "abort_boundaries": len(candidate["blocks"]) + 1, "stage_peak": pool.stage("stStat", 0),
                        "after": measurement.stats(pool), "candidate_checks": checks, "all_three_after": final_checks})
                    print(json.dumps({"split_PPC_replacement": group["name"], "candidate": label, "target": target,
                                      "layout": layout["name"], "accepted": bool(accepted)}), flush=True)
        assert before == {name: measurement.sha(ROOT / name) for name in names}
        report["passed"] = True
    finally:
        codec.close(); harness.close()
        (folder / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__": main()
