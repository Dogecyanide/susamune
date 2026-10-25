"""Replay measured streams through the mixed store without changing game consumers."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import zlib

from elftools.elf.elffile import ELFFile
from test_state_store import StoreCodec, StorePool, Identity, identity
from test_timewarp_staged_transaction import StageHarness
from timewarp_chunk_codec import run
import timewarp_multibank_pool as measurement

ROOT = measurement.ROOT
FILES = ['src/state_store.cpp', 'include/susamune/state_store.hxx',
         'src/state_crc.cpp', 'include/susamune/state_crc.h', 'include/susamune/state_crc.hxx',
         'include/susamune/state_chunk_pool.h', 'include/susamune/state_staged_transaction.h',
         'include/susamune/state_root_reader.h', 'include/susamune/state_quick_producer.hxx',
         'include/susamune/state_export_plan.h', 'src/state_codec.cpp', 'src/qft_timer.cpp',
         'scripts/test_state_store.py', 'scripts/timewarp_state_store.py']


def budget(folder):
    source = folder / 'layout.cpp'; obj = folder / 'layout.o'
    source.write_text('#include "susamune/state_store.hxx"\nextern "C" const unsigned layout[]={'
        'sizeof(StateStore::Store),sizeof(StateStore::Identity),sizeof(TWChunkPool),'
        'TWS_INPUT_OFFSET,TWS_INPUT_BYTES,TWR_CONTROL_OFFSET,TWR_CONTROL_BYTES};\n')
    flags = [ROOT / 'toolchain/clang++.exe', '--target=powerpc-gecko-ibm-kuribo-eabi',
             '-std=c++17', '-Oz', '-fno-exceptions', '-fno-rtti', '-fno-builtin',
             '-ffunction-sections', '-fdata-sections', '-I', ROOT / 'include']
    run([*flags, '-c', source, '-o', obj], folder)
    with obj.open('rb') as file:
        elf = ELFFile(file)
        sym = next(s for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name == 'layout')
        values = struct.unpack_from('>7I', elf.get_section(sym['st_shndx']).data(), sym['st_value'])
    run([*flags, '-c', ROOT / 'src/state_store.cpp', '-o', folder / 'state_store.o'], folder)
    with (folder / 'state_store.o').open('rb') as file:
        elf = ELFFile(file)
        text = sum(s['sh_size'] for s in elf.iter_sections() if s['sh_flags'] & 4)
        initialized = sum(s['sh_size'] for s in elf.iter_sections()
                          if s['sh_flags'] & 2 and not s['sh_flags'] & 4 and s['sh_type'] != 'SHT_NOBITS')
    return dict(zip(('store_context_bytes', 'identity_bytes', 'directory_struct_bytes',
        'reader_table_offset', 'reader_table_reserved_bytes', 'reader_control_offset',
        'reader_control_reserved_bytes'), values), isolated_object_code_bytes=text,
        isolated_object_initialized_data_bytes=initialized,
        scope='PPC compile only; object totals before final link GC and shared-helper folding.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/timewarp-state-store')
    args = parser.parse_args(); folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT / 'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True); (folder / 'allocator').mkdir()
    before = {f: measurement.sha(ROOT / f) for f in FILES}
    report = {'scope': 'Native execution of production mixed-store/codec with exact measured PPC streams and captured Deflate archives. No game owner restore, activation, ARM cache or Wii timing claim.',
              'source_sha256': before, 'budget': budget(folder), 'sets': [], 'legacy': []}
    codec = StoreCodec(folder); harness = StageHarness(folder / 'allocator')
    try:
        measurement.INPUTS = (*measurement.INPUTS, ROOT / 'build/timewarp-stress-measure/receipt.json',
                              ROOT / 'build/timewarp-noki1-measure/receipt.json')
        groups, report['input_receipts'] = measurement.inputs()
        sizes = [0xFF0000, 0x200000, 0xC2000, 0x13E000]
        for group in groups:
            pool = StorePool(harness, codec, sizes)
            for slot, state in enumerate(group['states']):
                assert pool.put(slot, state['raw'], state['expected'][0], 1001 + slot * 71, 0)
            row = {'name': group['name'], 'quick_occupied_bytes': pool.pool.directory.high_water,
                   'quick_free_bytes': sum(sizes) - pool.pool.directory.high_water, 'legacy_replacements': []}
            for slot in range(3): pool.decode(slot, True)
            historical = []
            for slot, state in enumerate(group['states']):
                path = Path(state['input']['raw_path']).with_suffix('.packed')
                if not path.is_file(): continue
                encoded = path.read_bytes()
                kind = int(encoded[:4] != b'MSL4')
                if not kind: continue
                assert zlib.decompress(encoded) == state['raw']
                historical.append((slot, state, path, encoded))
                info = identity(state['raw'], encoded, 78291 + slot, kind)
                assert pool.begin(slot)
                appended = pool.append(encoded, kind)
                sealed = appended and pool.seal(info)
                committed = sealed and bool(pool.call('sc', C.byref(info)))
                if committed:
                    pool.identities[slot], pool.roots[slot] = info, (state['raw'], encoded)
                else: assert pool.call('sa')
                for n in range(3): pool.decode(n, True)
                row['legacy_replacements'].append({'slot': slot, 'path': str(path),
                    'sha256': hashlib.sha256(encoded).hexdigest(), 'bytes': len(encoded),
                    'appended': appended, 'sealed': sealed, 'committed': committed,
                    'old_roots_preserved_on_refusal': not committed, 'all_roots_decode': True,
                    'occupied_bytes': pool.pool.directory.high_water})
            # Also prove all actual captured Deflate streams can be retained independently.
            for slot, state, path, encoded in historical:
                single = StorePool(harness, codec, sizes)
                assert single.put(slot, state['raw'], encoded, 908731, 1)
                single.decode(slot, True)
                report['legacy'].append({'path': str(path), 'bytes': len(encoded),
                    'opaque_chunks': single.pool.directory.slots[slot].count,
                    'exact_stored_stream': True, 'ordinary_and_protected_decode': True})
            report['sets'].append(row)
            print(json.dumps(row), flush=True)
        report['passed'] = True
    finally:
        codec.close(); harness.close()
    assert before == {f: measurement.sha(ROOT / f) for f in FILES}
    (folder / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
