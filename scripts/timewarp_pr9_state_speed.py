"""PR8/current shared-store A/B with the shipped per-module compiler flags."""
import argparse
import json
from pathlib import Path
import shlex
import sys
import zlib

from timewarp_shared_speed import capture_tree, adapter, command, timed
from timewarp_pool_ppc import ROOT, PoolPilot, sha
from timewarp_replay_ppc import captured


def compile_bench(folder, tree, commands, extra_pool=0, stage_tail=False):
    entry = adapter(tree, True)
    pool = tree/'scripts/timewarp/ppc_pool_bench.cpp'
    text = pool.read_text()
    if stage_tail:
        assert not extra_pool
        text = text.replace('(unsigned char*)0x71100000,(unsigned char*)0x71b00000,0}',
                            '(unsigned char*)0x71500000,(unsigned char*)0x71b00000,(unsigned char*)0x71d00000}')
        text = text.replace('{0xff0000,0x200000,0xc2000,0x13e000,0},4}',
                            '{0xff0000,0x200000,0x2c2000,0x13e000,0x70000},5}')
        text = text.replace('(unsigned char*)0x71200000,0x2f0000}',
                            '(unsigned char*)0x71200000,0xf0000}')
    if extra_pool:
        old = '0xc2000,0x13e000,0},4}'
        assert text.count(old) == 1
        text = text.replace(old, '0xc2000,'+hex(0x13e000+extra_pool)+',0},4}')
    for module in ('state_codec', 'state_crc'):
        text = text.replace(f'#include "../../src/{module}.cpp"', '')
    pool.write_text(text)
    store = tree/'scripts/timewarp/ppc_store_bench.cpp'
    text = store.read_text()
    if stage_tail:
        text = text.replace('0x71500000, ReplayScratchBytes', '0x71400000, ReplayScratchBytes')
    for module in ('state_store', 'state_import', 'state_quick_replay'):
        text = text.replace(f'#include "../../src/{module}.cpp"', f'#include "susamune/{module}.hxx"')
    store.write_text(text)
    objects, invocations = [], []
    for module in ('state_codec', 'state_crc', 'state_store', 'state_import', 'state_quick_replay', 'bench'):
        key = 'state_store' if module == 'bench' else module
        original = next(e for e in commands if Path(e['file']).name == key+'.cpp' and 'VERSION_PAL' in e['command'])
        argv = [x.strip('"') for x in shlex.split(original['command'], posix=False)]
        obj = folder/(module+'.o')
        argv[argv.index('-o')+1] = str(obj)
        argv[argv.index('-c')+1] = str(entry if module == 'bench' else tree/'src'/(module+'.cpp'))
        for i, value in enumerate(argv):
            if value.startswith('-I'):
                argv[i] = '-I'+str(tree/Path(value[2:]).resolve().relative_to(ROOT))
        if module == 'bench':
            argv.append('-fno-builtin')
        command(argv)
        objects.append(obj); invocations.append(argv)
    script = folder/'bench.ld'
    script.write_text('ENTRY(_start)\nSECTIONS { . = 0x80004000; '
        '.text : { *(.text.start) *(.text*) *(.foxtrot.text*) . = ALIGN(32); } '
        '.rodata : { *(.rodata*) *(.foxtrot.rodata*) . = ALIGN(32); } '
        '.data : { *(.data*) *(.foxtrot.data*) *(.got*) . = ALIGN(32); } '
        '.bss : { *(.bss*) *(.foxtrot.bss*) *(COMMON) . = ALIGN(32); } '
        'ASSERT(. < 0x80080000, "bench overlaps captured input") '
        '/DISCARD/ : { *(.eh_frame*) *(.comment*) } }\n')
    elf, dol = folder/'bench.elf', folder/'bench.dol'
    command([ROOT/'toolchain/ld.lld.exe', '--gc-sections', '-T', script, *objects, '-o', elf])
    command([sys.executable, ROOT/'scripts/elf2dol.py', elf, dol])
    return dol, {'commands': invocations, 'elf_sha256': sha(elf), 'dol_sha256': sha(dol),
                 'adapter_sha256': {str(p.relative_to(tree)): sha(p) for p in (entry, pool, store)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--baseline-receipt', type=Path)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT/'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    baseline = ROOT/'build/timewarp-online-source-19'
    checkpoint = ROOT/'build/timewarp-online-checkpoint-19'
    frozen = json.loads((baseline/'receipt.json').read_text())
    commands_file = checkpoint/'console/compile_commands.json'
    commands = json.loads(commands_file.read_text())
    input_file = ROOT/'build/timewarp-heap-gap-measure/receipt.json'
    inputs = json.loads(input_file.read_text())
    states = [captured(inputs, 'pinna3/slot'+str(n)) for n in (1, 2, 3)]
    report = {'passed': False,
        'scope': 'One game-free actual-PPC A/B of shared-store save/load components with '
                 'the exact PR8 per-module optimization flags. Isolated fake-VMEM banks, '
                 'synthetic admission and scalar fixture memory functions; no Wii cache, '
                 'ARM, gameplay, display barrier or freeze-to-Mario timing.',
        'baseline_identity_sha256': sha(checkpoint/'identity.json'),
        'baseline_source_receipt_sha256': sha(baseline/'receipt.json'),
        'compile_commands_sha256': sha(commands_file), 'input_receipt_sha256': sha(input_file),
        'adapter_sha256': sha(Path(__file__)), 'inputs': [s['input'] for s in states], 'variants': {}}
    pilot = None
    try:
        if args.baseline_receipt:
            prior = json.loads(args.baseline_receipt.read_text())
            assert prior['passed']
            for key in ('baseline_identity_sha256', 'baseline_source_receipt_sha256',
                        'compile_commands_sha256', 'input_receipt_sha256', 'inputs'):
                assert prior[key] == report[key]
            report['variants']['pr8'] = prior['variants']['pr8']
            report['reused_baseline_receipt_sha256'] = sha(args.baseline_receipt)
        for name, source in (('pr8', baseline), ('current', ROOT)):
            if name == 'pr8' and args.baseline_receipt:
                continue
            directory = folder/name; directory.mkdir()
            tree = directory/'tree'
            row = {'source_sha256': capture_tree(source, tree, frozen['files'] if name == 'pr8' else None),
                   'saves': [], 'loads': [], 'overwrites': []}
            report['variants'][name] = row
            dol, row['build'] = compile_bench(directory, tree, commands)
            pilot = PoolPilot(args.dolphin, directory, dol, row.setdefault('runtime', {}), 1)
            with pilot:
                pilot.command(1)
                for operation, opcode in (('saves', 20), ('loads', 21), ('overwrites', 20)):
                    for slot, state in enumerate(states):
                        pilot.write(pilot.INPUT, state['raw'] if opcode == 20 else b'\xa7'*len(state['raw']))
                        measured = timed(pilot, opcode, slot, len(state['raw']) if opcode == 20 else 0)
                        assert pilot.read(pilot.INPUT, len(state['raw'])) == state['raw']
                        if opcode == 20:
                            assert (measured['packed'], measured['raw'], measured['adler'], measured['crc']) == (
                                len(state['packed']), len(state['raw']), zlib.adler32(state['raw']), zlib.crc32(state['packed']))
                            measured['exact_stream'] = pilot.encoded(slot, state)['exact']
                        measured['exact_input_or_decoded_bytes'] = True
                        row[operation].append(measured)
                row['canaries_intact'] = True
            row['owned_process_stopped'] = pilot.process.poll() is not None
            assert row['source_sha256'] == {p: sha(tree/p) for p in row['source_sha256']}
            print(json.dumps({'variant': name, **{op: [r['guest_ticks'] for r in row[op]]
                for op in ('saves', 'loads', 'overwrites')}}), flush=True)
        before, after = report['variants']['pr8'], report['variants']['current']
        report['comparison'] = {op: [{'slot': i+1, 'before_ticks': a['guest_ticks'], 'after_ticks': b['guest_ticks'],
            'reduction_percent': 100*(1-b['guest_ticks']/a['guest_ticks'])}
            for i, (a,b) in enumerate(zip(before[op], after[op]))] for op in ('saves', 'loads', 'overwrites')}
        report['passed'] = True
    finally:
        if pilot and pilot.process and pilot.process.poll() is None:
            pilot.__exit__()
        (folder/'receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'passed': True, 'comparison': report['comparison']}), flush=True)


if __name__ == '__main__':
    main()
