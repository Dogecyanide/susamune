"""Decode immutable allocator roots with the unchanged production codec."""
import argparse
import ctypes as C
import json
from pathlib import Path
import struct
import zlib

from elftools.elf.elffile import ELFFile
from test_state_codec import Guarded, Span, DirectPolicy
from test_timewarp_staged_transaction import StageHarness, StageMemory, StagePool, Token
from timewarp_chunk_codec import Codec, run
import timewarp_multibank_pool as measurement

ROOT = measurement.ROOT


class RootCodec(Codec):
    def __init__(self, folder, extra_source=""):
        wrapper = folder / "root.cpp"
        wrapper.write_text('#include "' + (ROOT / 'src/state_codec.cpp').as_posix() + '"\n' +
                           '#include "' + (ROOT / 'src/state_crc.cpp').as_posix() + '"\n' +
                           '#include "' + (ROOT / 'scripts/timewarp/state_root_reader.h').as_posix() + '"\n' + r'''
extern "C" {
__declspec(dllexport) unsigned rb(TWStageMemory*m,unsigned s,unsigned g,unsigned t,unsigned r,unsigned p,unsigned a,unsigned c,TWStageToken*k,void*b,unsigned n){return TWRBuild(m,s,g,t,r,p,a,c,*k,b,n);}
__declspec(dllexport) int rc(TWStageMemory*m,unsigned s,unsigned a,void*b,unsigned n){return TWRCheck(m,s,a,b,n);}
__declspec(dllexport) int rr(TWStageMemory*m,unsigned s){return TWRRelease(m,s);}
__declspec(dllexport) unsigned rn(TWStageMemory*m){return TWRControl(m)->spanCount;}
__declspec(dllexport) unsigned rt(){return TWR_TABLE_BYTES;}
__declspec(dllexport) int gb(TWStageMemory*m,unsigned s,unsigned g,unsigned t,TWStageToken*k){return TWRBegin(m,s,g,t,k);}
__declspec(dllexport) int ga(TWStageMemory*m,TWStageToken*k,const unsigned char*b,unsigned n){return TWRAppend(m,*k,b,n);}
__declspec(dllexport) int gc(TWStageMemory*m,TWStageToken*k,unsigned r,unsigned p,unsigned c,unsigned t){return TWRCommit(m,*k,r,p,c,t);}
__declspec(dllexport) int gx(TWStageMemory*m,TWStageToken*k){return TWRAbort(m,*k);}
__declspec(dllexport) int gm(TWStageMemory*m){return TWRCompact(m);}
__declspec(dllexport) int gd(TWStageMemory*m,unsigned s,unsigned g,unsigned t){return TWRClear(m,s,g,t);}
__declspec(dllexport) int vr(void*w,unsigned n,const StateCodec::ReadSpan*s,unsigned sc,const StateCodec::WriteSpan*d,unsigned dc,unsigned raw,unsigned adler){return StateCodec::validateRestore(w,n,s,sc,d,dc,raw,adler);}
}
''' + extra_source)
        super().__init__(folder, wrapper)
        mem, tok, u, ptr = C.POINTER(StageMemory), C.POINTER(Token), C.c_uint, C.c_void_p
        signatures = {"rb": [mem] + [u] * 7 + [tok, ptr, u], "rc": [mem, u, u, ptr, u],
                      "rr": [mem, u], "rn": [mem], "gb": [mem, u, u, u, tok],
                      "ga": [mem, tok, ptr, u], "gc": [mem, tok, u, u, u, u],
                      "gx": [mem, tok], "gm": [mem], "gd": [mem, u, u, u],
                      "vr": [ptr, u, C.POINTER(Span), u, C.POINTER(Span), u, u, u]}
        for name, args in signatures.items(): getattr(self.lib, name).argtypes = args
        self.table = Guarded(self.lib.rt())

    def call(self, pool, name, *args):
        return getattr(self.lib, name)(C.byref(pool.stage_memory), *args)

    def borrow(self, pool, slot, state):
        packed, tag, raw_size = state["expected"]
        generation = pool.token.generation + 1 if slot == 3 else pool.stage("stGeneration", slot)
        return self.call(pool, "rb", slot, generation, tag, raw_size, len(packed),
                         zlib.adler32(state["raw"]), zlib.crc32(packed), C.byref(pool.token),
                         self.table.ptr, self.table.size)

    def guarded_begin(self, pool, slot):
        return self.call(pool, "gb", slot, pool.stage("stGeneration", slot),
                         pool.directory.slots[slot].tag, C.byref(pool.token))

    def guarded_append(self, pool, block):
        buffer = C.create_string_buffer(block)
        return self.call(pool, "ga", C.byref(pool.token), buffer, len(block))

    def guarded_commit(self, pool, candidate):
        packed, tag, raw = candidate["expected"]
        return self.call(pool, "gc", C.byref(pool.token), raw, len(packed), zlib.crc32(packed), tag)

    def decode(self, pool, slot, state, test_guards=False):
        old_roots = pool.states()
        sequence = self.borrow(pool, slot, state)
        assert sequence
        count = self.call(pool, "rn")
        source = (Span * count).from_address(self.table.ptr)
        packed, tag, raw_bytes = state["expected"]
        raw, adler = state["raw"], zlib.adler32(state["raw"])
        assert b"".join(C.string_at(s.data, s.size) for s in source) == packed
        descriptors = C.string_at(self.table.ptr, self.table.size)
        checks = []
        if test_guards:
            assert not self.call(pool, "gm")
            assert not self.call(pool, "gd", 0, pool.stage("stGeneration", 0), pool.directory.slots[0].tag)
            token = Token()
            assert not self.call(pool, "gb", 0, pool.stage("stGeneration", 0), pool.directory.slots[0].tag, C.byref(token))
            assert not self.borrow(pool, slot, state)
            assert not self.call(pool, "rc", sequence, adler ^ 1, self.table.ptr, self.table.size)
            saved = source[1].size
            source[1].size += 1
            assert not self.call(pool, "rc", sequence, adler, self.table.ptr, self.table.size)
            source[1].size = saved
            if slot == 3:
                assert not self.guarded_commit(pool, state)
                assert not self.call(pool, "gx", C.byref(pool.token))
                assert not self.guarded_append(pool, state["blocks"][0])
        for preserve in (False, True):
            assert self.call(pool, "rc", sequence, adler, self.table.ptr, self.table.size)
            destination = Guarded(raw_bytes)
            before = destination.data()
            cut = 0x20000 + 17
            output = (Span * 2)(Span(destination.ptr, cut), Span(destination.ptr + cut, raw_bytes - cut))
            policy = DirectPolicy()
            expected = bytearray(raw)
            if preserve:
                first, length = min(2 * 0x20000 + 13, raw_bytes // 2), 31
                policy.first, policy.last = destination.ptr + first, destination.ptr + first + length
                expected[first:first + length] = before[first:first + length]
            assert self.lib.vr(self.work.ptr, self.work.size, source, count, output, 2, raw_bytes, adler) == 0
            assert destination.data() == before
            assert self.call(pool, "rc", sequence, adler, self.table.ptr, self.table.size)
            assert self.unpack(source, output, raw_bytes, adler, policy) == 0
            assert destination.data() == expected and destination.guards() and self.work.guards()
            assert C.string_at(self.table.ptr, self.table.size) == descriptors
            checks.append({"protected_range": preserve, "direct_blocks": policy.allowed,
                           "copied_bytes": policy.copied_bytes, "source_spans": count,
                           "exact_output": True, "table_and_source_immutable": True})
        assert pool.states() == old_roots
        assert self.call(pool, "rr", sequence)
        assert not self.call(pool, "rr", sequence)
        assert not self.call(pool, "rc", sequence, adler, self.table.ptr, self.table.size)
        pool.canaries()
        assert self.table.guards()
        return checks


def ppc_budget(folder):
    source, obj = folder / "reader-layout.cpp", folder / "reader-layout.o"
    source.write_text('#include "' + (ROOT / 'scripts/timewarp/state_root_reader.h').as_posix() + '"\n' +
        'extern "C" const unsigned layout[]={sizeof(StateCodec::ReadSpan),TWR_TABLE_BYTES,TWS_INPUT_BYTES,TWR_CONTROL_OFFSET,TWR_CONTROL_BYTES,TW_CHUNK_DIRECTORY_BYTES};\n')
    run([ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", source,
         "-I", ROOT / "include", "-o", obj], folder)
    with obj.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = next(s for s in elf.get_section_by_name(".symtab").iter_symbols() if s.name == "layout")
        values = struct.unpack_from(">6I", elf.get_section(symbol["st_shndx"]).data(), symbol["st_value"])
    assert values == (8, 2064, 2080, 30976, 128, 32768)
    return {"read_span_bytes": values[0], "table_and_frame_bytes": values[1], "table_reservation_bytes": values[2],
            "reader_control_offset": values[3], "reader_control_reserved_bytes": values[4],
            "directory_bytes": values[5], "spare_directory_bytes": values[5] - values[3] - values[4]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-root-codec")
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()): parser.error("Use a private build folder")
    folder.mkdir(parents=True, exist_ok=True)
    files = ("scripts/timewarp/state_root_reader.h", "scripts/timewarp_root_codec.py",
             "scripts/timewarp/state_staged_transaction.h", "scripts/timewarp/state_chunk_pool.h",
             "src/state_codec.cpp", "include/susamune/state_codec.hxx", "src/qft_timer.cpp")
    before = {name: measurement.sha(ROOT / name) for name in files}
    layout = ppc_budget(folder)
    codec = RootCodec(folder)
    harness_folder = folder / "allocator"
    harness_folder.mkdir(exist_ok=True)
    harness = StageHarness(harness_folder)
    initial, replacements = [], []
    try:
        measurement.INPUTS = (*measurement.INPUTS, ROOT / "build/timewarp-stress-measure/receipt.json")
        groups, receipts = measurement.inputs()
        configs, transaction = measurement.banks(harness)
        config = configs[1]
        def create(group):
            pool = StagePool(harness, sizes=[b["size"] for b in config["banks"]],
                             guest_bases=[b["ppc_address"] for b in config["banks"]])
            for slot, state in enumerate(group["states"]): assert pool.put(slot, state["blocks"], state["expected"][1])
            return pool
        for group in groups:
            pool = create(group)
            for slot, state in enumerate(group["states"]):
                checks = codec.decode(pool, slot, state, test_guards=True)
                initial.append({"set": group["name"], "slot": slot, "checks": checks})
            print(json.dumps({"all_three_decoded_from_real_pool": group["name"]}), flush=True)
        named = {g["name"]: g for g in groups}
        cases = [(named["mixed"], f"late-Gelato-{i + 1}", named["same-level"]["states"][i]) for i in (1, 2)]
        cases += [(named[a], b, named[b]["states"][0]) for a, b in (("bianco5", "pinna3"), ("pinna3", "bianco5"))]
        for group, label, candidate in cases:
            for target in range(3):
                pool = create(group)
                assert codec.guarded_begin(pool, target)
                for block in candidate["blocks"]: assert codec.guarded_append(pool, block)
                candidate_checks = codec.decode(pool, 3, candidate, test_guards=True)
                assert codec.guarded_commit(pool, candidate)
                expected = list(group["states"])
                expected[target] = candidate
                checks = [codec.decode(pool, slot, state, test_guards=True) for slot, state in enumerate(expected)]
                replacements.append({"set": group["name"], "candidate": label, "target": target,
                                     "candidate_checks_before_commit": candidate_checks,
                                     "all_three_checks_after_commit": checks, "stage_peak_bytes": pool.stage("stStat", 0)})
                print(json.dumps({"candidate_and_all_three_after_commit": group["name"], "candidate": label, "target": target}), flush=True)
    finally:
        harness.close()
        codec.close()
    assert before == {name: measurement.sha(ROOT / name) for name in files}
    receipt = {"scope": "Private checked allocator-root ReadSpans consumed by the unchanged production decoder on native host. PPC compiler verifies descriptor/directory sizes, not PPC runtime speed or gameplay restore. All low-level mutations must remain inside the same exclusive owner and use pin guards while borrowed.",
               "source_sha256": before, "input_receipts": receipts, "PPC_directory_budget": layout,
               "native_descriptor_only_test_scratch_bytes": 257 * C.sizeof(Span) + 8,
               "encoded_payload_copies_for_reader": 0, "initial_roots": initial, "replacements": replacements,
               "limits": "Full StoredState owner compatibility, real output-address policy, ARM lease/cache/runtime wiring, reset retirement and Wii speed remain integration gates."}
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__": main()
