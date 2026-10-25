"""One captured Pinna 3 A/B of Test2 and current shared save/load components."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

from timewarp_pool_ppc import ROOT, PoolPilot, sha
from timewarp_replay_ppc import captured


SOURCES = ('state_codec.cpp', 'state_crc.cpp', 'state_store.cpp',
           'state_import.cpp', 'state_quick_replay.cpp', 'qft_timer.cpp')


def command(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def capture_tree(source, destination, frozen=None):
    paths = [source/'src'/name for name in SOURCES]
    paths += [p for name in ('include', 'vendor') for p in (source/name).rglob('*') if p.is_file()]
    before = {p.relative_to(source).as_posix(): sha(p) for p in paths}
    if frozen is not None:
        assert all(frozen.get(name) == value for name, value in before.items())
    for name in before:
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
    assert before == {name: sha(source/name) for name in before}
    assert before == {name: sha(destination/name) for name in before}
    return before


def adapter(tree, current):
    directory = tree/'scripts/timewarp'
    directory.mkdir(parents=True)
    pool = (ROOT/'scripts/timewarp/ppc_pool_bench.cpp').read_text()
    assert '#include "../../src/state_crc.cpp"' in pool
    (directory/'ppc_pool_bench.cpp').write_text(pool)
    store = (ROOT/'scripts/timewarp/ppc_store_bench.cpp').read_text()
    timing = '''static unsigned guestTicks() {
    unsigned value;
    asm volatile("sync\\nisync\\nmftb %0" : "=r"(value) :: "memory");
    return value;
}
'''
    store = replace(store, 'static unsigned storeRun(', timing + 'static unsigned storeRun(')
    load = '''
        return StateStore::restoreSlot(Store, slot, identity, (void *)Work, 0x4e000,
            &output, 1, copy, nullptr, direct);
''' if current else '''
        const unsigned pin = StateStore::pin(Store, slot, identity);
        if (!pin) return 122;
        const unsigned status = StateStore::restore(Store, pin, identity, (void *)Work, 0x4e000,
            &output, 1, copy, nullptr, direct);
        return StateStore::unpin(Store, pin) ? status : 123;
'''
    operations = '''    if (command == 20) {
        const unsigned start = guestTicks();
        unsigned status = storeRun(11, slot, size, tag);
        const unsigned prepared = guestTicks();
        if (!status) status = storeRun(12, slot, 0, 0);
        const unsigned committed = guestTicks();
        Box[30] = prepared - start; Box[31] = committed - prepared;
        return status;
    }
    if (command == 21) {
        if (slot >= 3) return 120;
        const StateStore::Identity identity = Store.roots[slot];
        if (!identity.raw || identity.raw > InputLimit) return 121;
        StateCodec::WriteSpan output = {(void *)Input, identity.raw};
        ProtectFirst = ProtectLast = 0;
        Box[5] = identity.packed; Box[6] = identity.raw;
        Box[7] = identity.adler; Box[8] = identity.checksum;
''' + load + '''    }
'''
    store = replace(store, '    if (command == 1) return resetStore() ? 0 : 90;',
                    operations + '    if (command == 1) return resetStore() ? 0 : 90;')
    store = replace(store, '        Box[4] = storeRun(Box[2], Box[12], Box[13], Box[14]);',
                    '''        const unsigned started = guestTicks();
        Box[4] = storeRun(Box[2], Box[12], Box[13], Box[14]);
        Box[23] = guestTicks() - started;''')
    (directory/'ppc_store_bench.cpp').write_text(store)
    entry = tree/'bench.cpp'
    entry.write_text('#define TIMEWARP_QUICK_REPLAY 1\n#include "scripts/timewarp/ppc_store_bench.cpp"\n')
    return entry


def build(folder, source):
    script = folder/'bench.ld'
    script.write_text('ENTRY(_start)\nSECTIONS { . = 0x80004000; '
        '.text : { *(.text.start) *(.text*) *(.foxtrot.text*) . = ALIGN(32); } '
        '.rodata : { *(.rodata*) *(.foxtrot.rodata*) . = ALIGN(32); } '
        '.data : { *(.data*) *(.foxtrot.data*) *(.got*) . = ALIGN(32); } '
        '.bss : { *(.bss*) *(.foxtrot.bss*) *(COMMON) . = ALIGN(32); } '
        'ASSERT(. < 0x80080000, "bench overlaps captured input") '
        '/DISCARD/ : { *(.eh_frame*) *(.comment*) } }\n')
    obj, elf, dol = [folder/('bench.'+ext) for ext in ('o', 'elf', 'dol')]
    flags = ['--target=powerpc-gecko-ibm-kuribo-eabi', '-Oz', '-Xclang', '-fmerge-functions',
             '-fsigned-char', '-ffast-math', '-fno-exceptions', '-fno-rtti', '-fno-builtin',
             '-ffunction-sections', '-fdata-sections', '-fno-unwind-tables', '-nostdlib',
             '-DIS_EMULATOR=0', '-DSUSAMUNE_VERSION_PAL=1', '-DTIMEWARP_SHARED_STORE=1',
             '-DTIMEWARP_HEAP_GAP=1', '-DTIMEWARP_QUICK_REPLAY=1']
    commands = [[ROOT/'toolchain/clang++.exe', *flags, '-I', source.parent/'include',
                 '-c', source, '-o', obj],
                [ROOT/'toolchain/ld.lld.exe', '--gc-sections', '-T', script, obj, '-o', elf],
                [sys.executable, ROOT/'scripts/elf2dol.py', elf, dol]]
    for args in commands:
        command(args)
    return dol, {'commands': [[str(a) for a in c] for c in commands],
                 'elf_sha256': sha(elf), 'dol_sha256': sha(dol)}


def timed(pilot, opcode, slot, size=0):
    row = pilot.command(opcode, slot, size)
    row.pop('host_seconds_to_ack')
    row['guest_ticks'] = struct.unpack('>I', pilot.read(pilot.CONTROL+92, 4))[0]
    if opcode == 20:
        values = struct.unpack('>8I', pilot.read(pilot.CONTROL+96, 32))
        row.update(dict(zip(('cached_bytes', 'spilled_blocks', 'replayed_raw_bytes', 'moved_bytes',
                             'scratch_bytes', 'encode_calls', 'prepare_ticks', 'commit_ticks'), values)))
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dolphin', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT/'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    snapshot = ROOT/'build/timewarp-integrated-source-snapshot-8'
    frozen = json.loads((snapshot/'receipt.json').read_text())['files']
    input_receipt = ROOT/'build/timewarp-heap-gap-measure/receipt.json'
    inputs = json.loads(input_receipt.read_text())
    states = [captured(inputs, 'pinna3/slot'+str(n)) for n in (1, 2, 3)]
    report = {'passed': False, 'scope': 'One actual-PPC guest-timebase A/B of isolated shared RAM '
        'replay save and restore components on three identical captured Pinna 3 states. '
        'Game-free owned Dolphin, synthetic admission, isolated fake-VMEM banks; no Wii '
        'freeze-to-Mario latency, ARM/cache/game barriers or 2.3.3 comparison.',
        'source_snapshot_receipt_sha256': sha(snapshot/'receipt.json'),
        'input_receipt_sha256': sha(input_receipt), 'inputs': [s['input'] for s in states],
        'adapter_sha256': sha(Path(__file__)), 'variants': {}}
    pilot = None
    try:
        for name, source in (('test2', snapshot), ('current', ROOT)):
            directory = folder/name; directory.mkdir()
            tree = directory/'tree'
            row = {'source_sha256': capture_tree(source, tree, frozen if name == 'test2' else None),
                   'saves': [], 'loads': []}
            report['variants'][name] = row
            entry = adapter(tree, name == 'current')
            row['adapter_sha256'] = {p.relative_to(tree).as_posix(): sha(p)
                for p in (entry, tree/'scripts/timewarp/ppc_pool_bench.cpp', tree/'scripts/timewarp/ppc_store_bench.cpp')}
        print(json.dumps({'immutable_source_captures_complete': True}), flush=True)
        for name in ('test2', 'current'):
            directory = folder/name; tree = directory/'tree'; entry = tree/'bench.cpp'
            row = report['variants'][name]
            dol, row['build'] = build(directory, entry)
            pilot = PoolPilot(args.dolphin, directory, dol, row, 1)
            row['runtime'] = pilot.evidence
            with pilot:
                for slot, state in enumerate(states):
                    pilot.write(pilot.INPUT, state['raw'])
                    saved = timed(pilot, 20, slot, len(state['raw']))
                    assert (saved['packed'], saved['raw'], saved['adler'], saved['crc']) == (
                        len(state['packed']), len(state['raw']), zlib.adler32(state['raw']), zlib.crc32(state['packed']))
                    assert pilot.read(pilot.INPUT, len(state['raw'])) == state['raw']
                    assert saved['generations'] == list(range(1, slot+2)) + [0]*(2-slot)
                    saved['exact_stream'] = pilot.encoded(slot, state)['exact']
                    row['saves'].append(saved)
                for slot, state in enumerate(states):
                    pilot.write(pilot.INPUT, b'\xa7'*len(state['raw']))
                    loaded = timed(pilot, 21, slot)
                    assert pilot.read(pilot.INPUT, len(state['raw'])) == state['raw']
                    loaded['exact_decoded_bytes'] = True
                    row['loads'].append(loaded)
                row['canaries_intact'] = True
            row['owned_process_stopped'] = pilot.process.poll() is not None
            assert row['source_sha256'] == {p: sha(tree/p) for p in row['source_sha256']}
            print(json.dumps({'variant': name, 'save_ticks': [x['guest_ticks'] for x in row['saves']],
                              'load_ticks': [x['guest_ticks'] for x in row['loads']]}), flush=True)
        old, new = report['variants']['test2'], report['variants']['current']
        report['comparison'] = {kind: [{'slot': i+1, 'test2_ticks': a['guest_ticks'],
            'current_ticks': b['guest_ticks'], 'speedup': a['guest_ticks']/b['guest_ticks'],
            'reduction_percent': 100*(1-b['guest_ticks']/a['guest_ticks'])}
            for i, (a, b) in enumerate(zip(old[kind], new[kind]))] for kind in ('saves', 'loads')}
        report['passed'] = True
    finally:
        if pilot and pilot.process and pilot.process.poll() is None:
            pilot.__exit__()
        (folder/'receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'passed': True, 'comparison': report['comparison'],
                      'receipt': str(folder/'receipt.json')}), flush=True)


if __name__ == '__main__':
    main()
