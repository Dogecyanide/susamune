"""Extended-input decoder proof using production code and exact PPC streams.

Against pre-integration sources it changes only checkSource's input limit in
a private copy. --production requires the integrated 257-input bound. Neither
mode is a gameplay restore or a Wii timing measurement.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import zlib

from elftools.elf.elffile import ELFFile
from mod_transport import encode_quick
from test_state_codec import Guarded, Span, DirectPolicy
from timewarp_state_measure import FRAME, BLOCK_BYTES, quick_blocks

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 257


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(argv, folder):
    result = subprocess.run([str(x) for x in argv], cwd=folder, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


SHIM = r'''
extern "C" {
void *memcpy(void*d,const void*s,__SIZE_TYPE__ n) {
 unsigned char*a=(unsigned char*)d;const unsigned char*b=(const unsigned char*)s;
 while(n--)*a++=*b++;return d;
}
void *memset(void*d,int v,__SIZE_TYPE__ n) {
 unsigned char*a=(unsigned char*)d;while(n--)*a++=(unsigned char)v;return d;
}
void *memmove(void*d,const void*s,__SIZE_TYPE__ n) {
 unsigned char*a=(unsigned char*)d;const unsigned char*b=(const unsigned char*)s;
 if(a<b){for(__SIZE_TYPE__ i=0;i<n;++i)a[i]=b[i];}else{while(n){--n;a[n]=b[n];}}return d;
}
int memcmp(const void*a,const void*b,__SIZE_TYPE__ n) {
 const unsigned char*x=(const unsigned char*)a,*y=(const unsigned char*)b;
 while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;
}
struct Policy {__UINTPTR_TYPE__ copies,bytes,queries,allowed,first,last;};
bool direct(void*p,void*d,unsigned n) {
 Policy*q=(Policy*)p;++q->queries;__UINTPTR_TYPE__ a=(__UINTPTR_TYPE__)d;
 if(q->last>a&&q->first<a+n)return false;++q->allowed;return true;
}
void copy(void*p,void*d,const void*s,unsigned n) {
 Policy*q=(Policy*)p;++q->copies;q->bytes+=n;
 unsigned char*a=(unsigned char*)d;const unsigned char*b=(const unsigned char*)s;
 for(unsigned i=0;i<n;++i){__UINTPTR_TYPE__ x=(__UINTPTR_TYPE__)(a+i);
  if(x<q->first||x>=q->last)a[i]=b[i];}
}
__declspec(dllexport) unsigned workspace(){return StateCodec::workspaceSize();}
__declspec(dllexport) int check(void*w,unsigned ws,const StateCodec::ReadSpan*s,
 unsigned n,unsigned raw,unsigned adler){return StateCodec::validate(w,ws,s,n,raw,adler);}
__declspec(dllexport) int unpack(void*w,unsigned ws,const StateCodec::ReadSpan*s,
 unsigned n,const StateCodec::WriteSpan*d,unsigned dn,unsigned raw,unsigned adler,
 Policy*p,unsigned verified) {
 return verified?StateCodec::decompressVerified(w,ws,s,n,d,dn,raw,adler,copy,p,direct):
  StateCodec::decompress(w,ws,s,n,d,dn,raw,adler,copy,p);
}
}
'''


class Codec:
    def __init__(self, folder, source):
        shim = folder / 'harness.cpp'
        shim.write_text('#include "' + source.as_posix() + '"\n' + SHIM)
        library = folder / 'harness.dll'
        run([ROOT / 'toolchain/clang++.exe', '--target=x86_64-pc-windows-msvc',
             '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2',
             '-fno-builtin', '-fno-exceptions', '-mno-stack-arg-probe', '-I', ROOT / 'include',
             shim, '-o', library], folder)
        self.lib = C.CDLL(str(library))
        self.lib.workspace.restype = C.c_uint
        self.lib.check.argtypes = [C.c_void_p, C.c_uint, C.POINTER(Span), C.c_uint, C.c_uint, C.c_uint]
        self.lib.unpack.argtypes = [C.c_void_p, C.c_uint, C.POINTER(Span), C.c_uint,
            C.POINTER(Span), C.c_uint, C.c_uint, C.c_uint, C.POINTER(DirectPolicy), C.c_uint]
        self.work = Guarded(self.lib.workspace())
        assert self.work.size <= 0x4e000

    def close(self):
        C.windll.kernel32.FreeLibrary(C.c_void_p(self.lib._handle))

    def check(self, source, raw, adler):
        return self.lib.check(self.work.ptr, self.work.size, source, len(source), raw, adler)

    def unpack(self, source, output, raw, adler, policy, verified=True):
        return self.lib.unpack(self.work.ptr, self.work.size, source, len(source), output,
            len(output), raw, adler, C.byref(policy), verified)


def spans(parts):
    buffers = [Guarded(len(p)) for p in parts]
    for buffer, data in zip(buffers, parts):
        C.memmove(buffer.ptr, bytes(data), len(data))
    descriptors = (Span * len(parts))(*(Span(b.ptr, b.size) for b in buffers))
    return buffers, descriptors


def decode_case(codec, packed, raw, parts, preserve=False, split=False):
    buffers, source = spans(parts)
    before = [b.data() for b in buffers]
    destination = Guarded(len(raw))
    untouched = destination.data()
    if split:
        cut = BLOCK_BYTES + 17
        output = (Span * 2)(Span(destination.ptr, cut), Span(destination.ptr + cut, len(raw) - cut))
    else:
        output = (Span * 1)(Span(destination.ptr, len(raw)))
    policy = DirectPolicy()
    expected = bytearray(raw)
    if preserve:
        first = min(BLOCK_BYTES * 2 + 13, len(raw) // 2)
        size = min(31, len(raw) - first)
        policy.first, policy.last = destination.ptr + first, destination.ptr + first + size
        expected[first:first + size] = untouched[first:first + size]
    adler = zlib.adler32(raw)
    assert codec.check(source, len(raw), adler) == 0
    assert codec.unpack(source, output, len(raw), adler, policy) == 0
    assert destination.data() == expected and destination.guards() and codec.work.guards()
    assert all(b.guards() and b.data() == initial for b, initial in zip(buffers, before))
    return dict(copies=policy.copies, copied_bytes=policy.copied_bytes,
                direct_queries=policy.queries, direct_blocks=policy.allowed)


def boundaries(codec):
    block = bytes(BLOCK_BYTES)
    encoded = encode_quick(block)[8:]
    buffers, two = spans([FRAME, encoded])
    source = (Span * LIMIT)(two[0], *(two[1] for _ in range(256)))
    raw = bytes(BLOCK_BYTES * 256)
    out = Guarded(len(raw))
    target = (Span * 1)(Span(out.ptr, out.size))
    policy = DirectPolicy()
    assert codec.check(source, len(raw), zlib.adler32(raw)) == 0
    assert codec.unpack(source, target, len(raw), zlib.adler32(raw), policy) == 0
    assert out.data() == raw and out.guards() and policy.allowed == 256
    oversized = (Span * (LIMIT + 1))(*source, two[1])
    assert codec.check(oversized, len(raw), zlib.adler32(raw)) == 1
    output65 = (Span * 65)(*(Span(out.ptr + i, 1) for i in range(65)))
    assert codec.unpack(source, output65, len(raw), zlib.adler32(raw), policy) == 1
    alias = (Span * 1)(Span(buffers[1].ptr, len(raw)))
    assert codec.unpack(source, alias, len(raw), zlib.adler32(raw), policy) == 1
    bad = bytearray(encoded)
    bad[0] ^= 1
    corrupt_buffers, corrupt = spans([FRAME] + [encoded] * 255 + [bad])
    C.memset(out.ptr, 0xa7, out.size)
    assert codec.unpack(corrupt, target, len(raw), zlib.adler32(raw), policy, False) == 4
    assert out.data() == bytes([0xa7]) * out.size and out.guards() and codec.work.guards()
    assert all(b.guards() for b in buffers + corrupt_buffers)
    legacy_raw = (bytes(range(256)) * 4096) + b'old Deflate'
    legacy = zlib.compress(legacy_raw)
    cuts = [legacy[i * len(legacy) // 100:(i + 1) * len(legacy) // 100] for i in range(100)]
    a = decode_case(codec, legacy, legacy_raw, [legacy], preserve=True)
    b = decode_case(codec, legacy, legacy_raw, cuts, preserve=True)
    assert a['copied_bytes'] == b['copied_bytes'] == len(legacy_raw)
    assert a['direct_blocks'] == b['direct_blocks'] == 0
    return dict(max_257_inputs=True, repeated_shared_input=True, input_258_refused=True,
                output_limit_64=True, alias_refused=True, late_corruption_atomic=True,
                legacy_deflate_exact=True, codec_workspace_bytes=codec.work.size)


def allocated(path):
    with path.open('rb') as stream:
        return {(i, s.name): (s['sh_size'], s.data()) for i, s in enumerate(ELFFile(stream).iter_sections())
                if s['sh_flags'] & 2}


def ppc_delta(folder, generated):
    rows = []
    for target in ('console', 'emu'):
        base = ROOT / ('build/baseline-' + target)
        commands = json.loads((base / 'compile_commands.json').read_text())
        for region in ('jp', 'us', 'pal'):
            entry = next(e for e in commands if Path(e['file']).name == 'state_codec.cpp'
                         and 'susamune_obj_' + region + '.dir' in e['output'])
            args = [x.strip('"') for x in shlex.split(entry['command'], posix=False)]
            output = folder / (target + '-' + region + '.o')
            args[args.index('-o') + 1] = str(output)
            args[args.index('-c') + 1] = str(generated)
            run(args, folder)
            original = base / ('CMakeFiles/susamune_obj_' + region + '.dir/src/state_codec.cpp.obj')
            a, b = allocated(original), allocated(output)
            assert a.keys() == b.keys()
            changes = []
            for name in a:
                assert a[name][0] == b[name][0], (target, region, name)
                for offset in range(0, len(a[name][1]), 4):
                    before, after = a[name][1][offset:offset + 4], b[name][1][offset:offset + 4]
                    if before != after:
                        changes.append(dict(section_index=name[0], section=name[1], offset=offset, before=before.hex(), after=after.hex()))
            assert len(changes) == 1 and changes[0]['before'][:4] == changes[0]['after'][:4], changes
            # Clang lowers count<=N to (count-1)<=N-1.
            assert changes[0]['before'][4:] == '003f' and changes[0]['after'][4:] == '0100', changes
            rows.append(dict(target=target, region=region, source_sha256=sha(generated.read_bytes()),
                             object_sha256=sha(output.read_bytes()), allocated_sizes_unchanged=True, changes=changes))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/timewarp-chunk-codec')
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / 'build').resolve()):
        parser.error('Output must remain in this task build directory')
    folder.mkdir(parents=True, exist_ok=True)
    production = ROOT / 'src/state_codec.cpp'
    original = production.read_text()
    if args.production:
        assert original.count('!count || count > kMaxReadSpans ||') == 1
        assert 'kMaxReadSpans = 257;' in (ROOT / 'include/susamune/state_codec.hxx').read_text()
        modified = original
    else:
        needle = '!count || count > kMaxSpans ||'
        assert original.count(needle) == 1, 'Use --production for integrated sources'
        modified = original.replace(needle, '!count || count > 257u ||')
    modified = modified.replace('"../vendor/', '"' + (ROOT / 'vendor').as_posix() + '/')
    generated = folder / 'state_codec.cpp'
    generated.write_text(modified)
    source_sha = sha(production.read_bytes())
    ppc = ppc_delta(folder, generated)
    codec = Codec(folder, generated)
    try:
        limits = boundaries(codec)
        rows = []
        for name in ('build/timewarp-state-measure/ppc-receipt.json', 'build/cross-level/current-ppc/receipt.json'):
            receipt = json.loads((ROOT / name).read_text())
            for group in receipt['sets']:
                for slot in group['slots']:
                    raw = Path(slot['raw_path']).read_bytes()
                    packed = Path(slot['ppc_quick']['path']).read_bytes()
                    assert sha(raw) == slot['raw_sha256'] and sha(packed) == slot['ppc_quick']['sha256']
                    blocks = quick_blocks(packed, raw)
                    policies = []
                    for preserve, split in ((False, False), (True, False), (True, True)):
                        contiguous = decode_case(codec, packed, raw, [packed], preserve, split)
                        scattered = decode_case(codec, packed, raw, [FRAME] + blocks, preserve, split)
                        assert contiguous == scattered
                        policies.append(dict(preserved_range=preserve, split_output=split, **scattered))
                    rows.append(dict(set=group['name'], slot=slot['slot'], raw_sha256=sha(raw),
                        packed_sha256=sha(packed), input_spans=len(blocks) + 1,
                        byte_exact=True, immutable_inputs=True, policies=policies))
                    print(f"{group['name']} slot {slot['slot']}: {len(blocks) + 1} spans exact; direct policy unchanged", flush=True)
    finally:
        codec.close()
    assert sha(production.read_bytes()) == source_sha
    result = dict(scope='Production decoder input-limit proof.' if args.production else
                  'Private copied production codec with a single extended input-count bound; no production source edit.',
                  limitations='Native decode and PPC object-size proof, not integrated pool metadata/reader or gameplay/Wii timings.',
                  source_sha256=source_sha, source_input_limit=LIMIT if args.production else 64,
                  decoded_input_limit=LIMIT,
                  output_limit=64, ppc_objects=ppc, boundaries=limits, streams=rows)
    (folder / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
