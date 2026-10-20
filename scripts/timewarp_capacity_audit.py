"""Exhaustive captured Quick triples and bounded sidecar capacity audit."""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import itertools
import json
from pathlib import Path
import random
import struct
import zlib

from test_state_codec import Guarded, Span, Result
from test_state_store import StoreCodec, StorePool, identity
from test_timewarp_staged_transaction import StageHarness
from timewarp_state_measure import quick_blocks
import timewarp_multibank_pool as measurement

ROOT = measurement.ROOT
BANKS = (0xFF0000, 0x200000, 0xC2000, 0x13E000)
CAPACITY = sum(BANKS)
INPUTS = (*measurement.INPUTS, ROOT / 'build/timewarp-stress-measure/receipt.json',
          ROOT / 'build/timewarp-noki1-measure/receipt.json')
FILES = ['src/state_store.cpp', 'src/state_codec.cpp', 'src/ghost.cpp',
         'src/practice_session.cpp', 'include/susamune/state_staged_transaction.h',
         'include/susamune/ghost_format.h', 'include/susamune/ghost_fludd.h',
         'include/susamune/ghost_teaching.h', 'include/susamune/tas_storage.h',
         'scripts/timewarp_capacity_audit.py']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_metadata(path, raw):
    metadata_path = path.with_suffix('.metadata')
    if not metadata_path.is_file():
        return {'metadata_available': False}
    metadata = metadata_path.read_bytes()
    count = struct.unpack_from('>I', metadata, 24)[0]
    regions = [struct.unpack_from('>III', metadata, 40 + 12 * i) for i in range(count)]
    assert 0 < count <= 24
    game = sum(size for _, size, _ in regions)
    assert max(offset + size for _, size, offset in regions) == game
    prefix = metadata.find(b'SGPF')
    result = {'metadata_available': True, 'metadata_path': str(metadata_path),
              'metadata_sha256': sha(metadata), 'scene': list(metadata[20:22]),
              'game_bytes': game, 'sidecar_payload_bytes': len(raw) - game}
    if prefix >= 0:
        assert metadata.find(b'SGPF', prefix + 1) < 0
        inputs = struct.unpack_from('>I', metadata, prefix + 20)[0]
        poses = struct.unpack_from('>I', metadata, prefix + 124)[0]
        segments, version = struct.unpack_from('>HH', metadata, prefix + 156)
        practice = struct.unpack_from('>16I', metadata, prefix + 512)
        assert version in (4, 5, 6) and poses <= 26974 and segments <= 64
        ghost_bytes = poses * 16 + segments * 32 + inputs * (24 if version == 6 else 16)
        practice_bytes = (236 if practice[1] & 1 else 0) + practice[2] * 16 + practice[14] * 16
        assert ghost_bytes + practice_bytes == len(raw) - game
        result.update(ghost_version=version, ghost_poses=poses, ghost_inputs=inputs,
                      ghost_segments=segments, ghost_bytes=ghost_bytes,
                      practice_frames=practice[2], practice_transitions=practice[14],
                      practice_bytes=practice_bytes)
    return result


def load(canonical=None):
    states, receipts, seen, intern, block_bytes = [], [], set(), {}, []
    for path in ([canonical] if canonical else INPUTS):
        receipt = json.loads(path.read_text())
        receipts.append({'path': str(path), 'sha256': sha(path.read_bytes())})
        for group in receipt['sets']:
            for original in group['slots']:
                row = ({'slot': original['name'].split('slot')[-1], 'raw_path': original['raw_path'],
                        'raw_sha256': original['filtered_raw_sha256'],
                        'ppc_quick': {'path': original['packed_path'], 'sha256': original['packed_sha256']}}
                       if canonical else original)
                if row['raw_sha256'] in seen:
                    continue
                seen.add(row['raw_sha256'])
                raw_path, packed_path = Path(row['raw_path']), Path(row['ppc_quick']['path'])
                raw, packed = raw_path.read_bytes(), packed_path.read_bytes()
                if canonical:
                    assert sha(raw) == original['raw_sha256']
                    offset, size = original['raw_offset'], original['free_bytes']
                    assert 0 <= offset < len(raw) and 0 < size <= len(raw) - offset
                    raw = raw[:offset] + bytes(size) + raw[offset + size:]
                assert sha(raw) == row['raw_sha256'] and sha(packed) == row['ppc_quick']['sha256']
                blocks = quick_blocks(packed, raw)
                ids = []
                for block in blocks:
                    if block not in intern:
                        intern[block] = len(block_bytes)
                        block_bytes.append(len(block))
                    ids.append(intern[block])
                meta = parse_metadata(raw_path, raw)
                info = {'name': f"{group['name']}/slot{row['slot']}", 'group': group['name'],
                        'raw_path': str(raw_path), 'raw_sha256': sha(raw),
                        'packed_path': str(packed_path), 'packed_sha256': sha(packed),
                        'raw_bytes': len(raw), 'packed_bytes': len(packed), **meta}
                if canonical:
                    info['gap_zeroed'] = {'offset': offset, 'size': size, 'original_raw_sha256': original['raw_sha256']}
                states.append({'info': info, 'raw': raw, 'packed': packed, 'blocks': blocks, 'ids': ids})
        print(json.dumps({'loaded': str(path), 'unique_captures': len(states)}), flush=True)
    return states, block_bytes, receipts


def placement(ids, sizes):
    cursor, bank, boundary, payload, rounded, seen = 0x8000, 0, BANKS[0], 0, 0, set()
    for value in ids:
        if value in seen:
            continue
        seen.add(value)
        length = sizes[value]
        size = (length + 31) & ~31
        payload += length
        rounded += size
        if cursor + size > boundary:
            cursor = boundary
            bank += 1
            boundary += BANKS[bank] if bank < len(BANKS) else 0x1000000
        cursor += size
    return {'occupied_bytes': cursor, 'free_bytes': CAPACITY - cursor,
            'unique_payload_bytes': payload, 'aligned_payload_bytes': rounded,
            'unique_blocks': len(seen), 'fits': cursor <= CAPACITY}


def screen(states, sizes):
    worst, mixed, stressed, failed, count, mixed_count = None, None, None, 0, 0, 0
    for indices in itertools.permutations(range(len(states)), 3):
        selected = [states[i] for i in indices]
        row = placement(itertools.chain.from_iterable(s['ids'] for s in selected), sizes)
        row['names'], row['indices'] = [s['info']['name'] for s in selected], list(indices)
        count += 1
        failed += not row['fits']
        if worst is None or row['occupied_bytes'] > worst['occupied_bytes']:
            worst = row
        areas = [s['info'].get('scene', [None])[0] for s in selected]
        if None not in areas and len(set(areas)) == 3:
            mixed_count += 1
            if mixed is None or row['occupied_bytes'] > mixed['occupied_bytes']:
                mixed = row
        if {s['info']['group'] for s in selected} == {'bianco5', 'pinna3', 'noki1'}:
            if stressed is None or row['occupied_bytes'] > stressed['occupied_bytes']:
                stressed = row
    return {'ordered_triples': count, 'over_capacity_triples': failed,
            'distinct_area_ordered_triples': mixed_count, 'worst': worst,
            'worst_distinct_areas': mixed, 'worst_bianco5_pinna3_noki1': stressed}


def exact(store):
    for slot, value in enumerate(store.roots):
        if value:
            store.decode(slot, True)


def append_candidate(store, slot, state, generation, commit=True):
    prior = [bytes(i) for i in store.identities]
    before = list(store.roots)
    assert store.begin(slot)
    accepted = store.append(state['packed'], 0)
    info = identity(state['raw'], state['packed'], generation, 0)
    sealed = accepted and store.seal(info)
    final_fits = bool(sealed and store.call('fit', C.byref(info)))
    committed = bool(commit and sealed and store.call('sc', C.byref(info)))
    if committed:
        store.identities[slot], store.roots[slot] = info, (state['raw'], state['packed'])
    else:
        assert store.call('sa')
        assert prior == [bytes(i) for i in store.identities] and before == store.roots
    exact(store)
    return {'appended': accepted, 'sealed': bool(sealed), 'committed': committed, 'final_fits': final_fits,
            'occupied_bytes': store.pool.directory.high_water,
            'free_bytes': CAPACITY - store.pool.directory.high_water,
            'stage_peak_bytes': store.pool.stage('stStat', 0),
            'all_roots_exact': True, 'old_roots_preserved_on_refusal': not committed}


def native(folder, states, screening):
    (folder / 'allocator').mkdir()
    extra = r'''extern "C" __declspec(dllexport) int fit(StateStore::Store*s,StateStore::Identity*i){
 return TWSPreflight(s->memory,s->transaction,i->raw,i->packed,i->checksum);}
extern "C" __declspec(dllexport) void pending(StateStore::Store*s,void*out,unsigned n){
 unsigned char*p=(unsigned char*)out;p[0]='M';p[1]='S';p[2]='L';p[3]='4';p[4]=0;p[5]=2;p[6]=p[7]=0;
 const TWChunkPool*d=TWChunkDirectory(s->memory->pool);unsigned offset=8;
 for(unsigned j=0;j<d->slots[3].count;++j){const TWChunk&c=d->chunks[d->slots[3].ids[j]-1];
  if(offset+c.size>n)__builtin_trap();memcpy(p+offset,TWSAddressUnchecked(s->memory,c.offset),c.size);offset+=c.size;}
 if(offset!=n)__builtin_trap();}
'''
    codec, harness = StoreCodec(folder, extra), StageHarness(folder / 'allocator')
    codec.work = Guarded(0x4e000)
    codec.lib.fit.argtypes = [C.c_void_p, C.c_void_p]
    codec.lib.pending.argtypes = [C.c_void_p, C.c_void_p, C.c_uint]
    report = {'exact_ppc_streams': [], 'host_producer_scope':
              'Native host LZ4 output differs from PPC; host producer rows are separate from exact PPC stream capacity.'}
    try:
        for label in ('worst', 'worst_distinct_areas', 'worst_bianco5_pinna3_noki1'):
            selected = [states[i] for i in screening[label]['indices']]
            store = StorePool(harness, codec, BANKS)
            row = {'name': label, 'states': screening[label]['names'], 'saves': []}
            for slot, state in enumerate(selected):
                row['saves'].append(append_candidate(store, slot, state, 100 + slot))
            if all(r['committed'] for r in row['saves']):
                assert store.pool.directory.high_water == screening[label]['occupied_bytes']
                row['replacement_abort'] = append_candidate(store, 1, selected[1], 401, False)
                row['same_capture_replacements'] = [append_candidate(store, slot, state, 501 + slot)
                    for slot, state in enumerate(selected)]
                alternatives = [max((s for s in states if s['info']['group'] == state['info']['group']
                    and s['info']['name'] != state['info']['name']), key=lambda s: s['info']['packed_bytes'],
                    default=state) for state in selected]
                row['other_capture_replacements'] = [dict(candidate=state['info']['name'],
                    **append_candidate(store, slot, state, 601 + slot)) for slot, state in enumerate(alternatives)]
            report['exact_ppc_streams'].append(row)
            print(json.dumps(row), flush=True)
        report['replacement_matrix'] = []
        for baseline in ('worst_bianco5_pinna3_noki1', 'worst'):
            if not screening[baseline]['fits']:
                continue
            selected = [states[i] for i in screening[baseline]['indices']]
            store = StorePool(harness, codec, BANKS)
            for slot, state in enumerate(selected):
                assert append_candidate(store, slot, state, 100 + slot)['committed']
            for slot in range(3):
                for state in states:
                    row = dict(baseline=baseline, slot=slot, candidate=state['info']['name'],
                               **append_candidate(store, slot, state, 700 + slot, False))
                    report['replacement_matrix'].append(row)
        report['replacement_summary'] = {
            'attempts': len(report['replacement_matrix']),
            'append_refusals': sum(not r['appended'] for r in report['replacement_matrix']),
            'final_capacity_refusals': sum(r['sealed'] and not r['final_fits'] for r in report['replacement_matrix']),
            'all_old_roots_preserved_and_decoded': True}
        print(json.dumps(report['replacement_summary']), flush=True)
        report['host_producer'] = []
        selected = [states[i] for i in screening['worst_bianco5_pinna3_noki1']['indices']]
        for kind, extra_bytes in [('capture', None), ('v6_maximum_sidecar_envelope', 17983 * 16 + 64 * 32 + 36000 * 24 + 236 + 4096 * 16 + 32 * 16)]:
            store = StorePool(harness, codec, BANKS)
            scenario = {'name': kind, 'saves': []}
            for slot, state in enumerate(selected):
                raw = state['raw'] if extra_bytes is None else state['raw'][:state['info']['game_bytes']] + random.Random(381 + slot).randbytes(extra_bytes)
                assert store.begin(slot)
                source = C.create_string_buffer(raw)
                spans, result = (Span * 1)(Span(C.addressof(source), len(raw))), Result()
                codec.lib.sz(store.storage.ptr, codec.work.ptr, codec.work.size, spans, 1, C.byref(result))
                success = result.status == 0
                encoded, committed = b'', False
                if success:
                    output = C.create_string_buffer(result.compressed)
                    store.call('pending', output, result.compressed)
                    encoded = output.raw
                    quick_blocks(encoded, raw)
                    info = identity(raw, encoded, 801 + slot, 0)
                    committed = store.seal(info) and bool(store.call('sc', C.byref(info)))
                if committed:
                    store.identities[slot], store.roots[slot] = info, (raw, encoded)
                else:
                    assert store.call('sa')
                exact(store)
                scenario['saves'].append({'slot': slot, 'raw_bytes': len(raw), 'packed_bytes': len(encoded),
                    'producer_status': result.status, 'committed': bool(committed),
                    'occupied_bytes': store.pool.directory.high_water,
                    'free_bytes': CAPACITY - store.pool.directory.high_water, 'all_old_roots_exact': True,
                    'equal_to_captured_ppc_stream': encoded == state['packed']})
            report['host_producer'].append(scenario)
            print(json.dumps(scenario), flush=True)
    finally:
        codec.close()
        harness.close()
    return report


def ppc(folder, dolphin, source):
    from timewarp_pool_ppc import PoolPilot, build
    from timewarp_store_ppc import produced
    receipt = json.loads(source.read_text())
    selected = [receipt['captures'][i] for i in receipt['screen']['worst']['indices']]
    def captured(row):
        raw = Path(row['raw_path']).read_bytes()
        if 'gap_zeroed' in row:
            gap = row['gap_zeroed']; offset, size = gap['offset'], gap['size']
            assert sha(raw) == gap['original_raw_sha256']
            raw = raw[:offset] + bytes(size) + raw[offset + size:]
        packed = Path(row['packed_path']).read_bytes()
        assert sha(raw) == row['raw_sha256'] and sha(packed) == row['packed_sha256']
        return {'raw': raw, 'packed': packed}
    states = [captured(row) for row in selected]
    report = {'scope': 'Actual PPC Store producer/codec, isolated game-free Dolphin; no Wii timing claim.',
              'input_receipt': str(source), 'input_receipt_sha256': sha(source.read_bytes()),
              'captures': selected, 'source_sha256': {f: sha((ROOT / f).read_bytes()) for f in FILES},
              'saves': [], 'passed': False}
    try:
        dol, report['build'] = build(folder, ROOT / 'scripts/timewarp/ppc_store_bench.cpp')
        pilot = PoolPilot(dolphin, folder, dol, report, 1)
        report['runtime'] = pilot.evidence
        with pilot:
            for slot, state in enumerate(states):
                row = {'produce': produced(pilot, slot, state),
                       'commit': pilot.command(4, slot, expected_status=95 if slot == 2 and not receipt['screen']['worst']['fits'] else 0)}
                if row['commit']['status']:
                    row['abort'] = pilot.command(5, slot)
                count = slot if row['commit']['status'] else slot + 1
                row['old_roots_exact'] = [{'encoded': pilot.encoded(i, old),
                    'decoded': pilot.decode(i, old, True)} for i, old in enumerate(states[:count])]
                report['saves'].append(row)
                print(json.dumps({'slot': slot, 'produce_status': row['produce']['status'],
                    'commit_status': row['commit']['status'], 'occupied': row['commit']['occupied'],
                    'stage_peak': row['commit']['stage_peak']}), flush=True)
            failures = [r for r in receipt.get('native', {}).get('replacement_matrix', [])
                        if not r['appended'] and r['slot'] == 2 and r['candidate'] == 'same-level/slot2'
                        and r.get('baseline', 'worst_bianco5_pinna3_noki1') == 'worst_bianco5_pinna3_noki1']
            if failures:
                row = failures[0]
                by_name = {r['name']: r for r in receipt['captures']}
                old_names = receipt['screen']['worst_bianco5_pinna3_noki1']['names']
                old = [captured(by_name[name]) for name in old_names]
                candidate = captured(by_name[row['candidate']])
                pilot.command(1)
                for slot, state in enumerate(old):
                    produced(pilot, slot, state)
                    pilot.command(4, slot)
                pilot.command(2, row['slot'])
                pilot.write(pilot.INPUT, candidate['raw'])
                replacement = {'old_names': old_names, 'slot': row['slot'], 'candidate': row['candidate'],
                    'produce': pilot.command(3, row['slot'], len(candidate['raw']), expected_status=3)}
                replacement['old_roots_before_abort'] = [pilot.encoded(i, state) for i, state in enumerate(old)]
                replacement['abort'] = pilot.command(5, row['slot'])
                replacement['old_roots_after_abort'] = [{'encoded': pilot.encoded(i, state),
                    'decoded': pilot.decode(i, state, True)} for i, state in enumerate(old)]
                final = list(old)
                final[row['slot']] = candidate
                pilot.command(1)
                replacement['same_final_roots_from_empty'] = []
                for slot, state in enumerate(final):
                    produced(pilot, slot, state)
                    replacement['same_final_roots_from_empty'].append(pilot.command(4, slot))
                replacement['final_roots_exact'] = [{'encoded': pilot.encoded(i, state),
                    'decoded': pilot.decode(i, state, True)} for i, state in enumerate(final)]
                report['replacement_only_refusal'] = replacement
                print(json.dumps({'replacement_refused': row['candidate'],
                    'old_roots_exact': True, 'same_final_roots_from_empty_fit': True,
                    'final_occupied_bytes': replacement['same_final_roots_from_empty'][-1]['occupied']}), flush=True)
        report['passed'] = True
    finally:
        (folder / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


def supplement(source, folder):
    prior = json.loads(source.read_text())
    intern, sizes, states = {}, [], {}
    for row in prior['captures']:
        packed = Path(row['packed_path']).read_bytes()
        assert sha(packed) == row['packed_sha256']
        ids, offset = [], 8
        while offset < len(packed):
            length = (struct.unpack_from('>I', packed, offset + 4)[0] & 0x7fffffff) + 8
            block = packed[offset:offset + length]
            assert len(block) == length
            if block not in intern:
                intern[block] = len(sizes)
                sizes.append(length)
            ids.append(intern[block])
            offset += length
        assert offset == len(packed)
        states[row['name']] = ids
    rows = []
    for result in prior['native']['replacement_matrix']:
        selected = prior['screen'][result.get('baseline', 'worst_bianco5_pinna3_noki1')]['names']
        old = list(dict.fromkeys(itertools.chain.from_iterable(states[n] for n in selected)))
        candidate = states[result['candidate']]
        referenced = set(candidate)
        for slot, name in enumerate(selected):
            if slot != result['slot']:
                referenced.update(states[name])
        final = [n for n in old if n in referenced] + [n for n in candidate if n not in old]
        projection = placement(final, sizes)
        peak = placement(itertools.chain(old, candidate), sizes)
        stage = max(0, peak['occupied_bytes'] - CAPACITY)
        if result['appended']:
            assert projection['fits'] == result['final_fits']
            assert stage <= 0x2f0000
        rows.append({**result, 'projected_final': projection,
                     'required_candidate_staging_bytes': stage,
                     'candidate_staging_shortfall_bytes': max(0, stage - 0x2f0000)})
    ghost_v6 = 17983 * 16 + 64 * 32 + 36000 * 24
    ghost_legacy = 26974 * 16 + 64 * 32 + 54000 * 16
    practice = 236 + 4096 * 16 + 32 * 16
    available = [s for s in prior['captures'] if s.get('metadata_available')]
    report = {'input_receipt': str(source), 'input_receipt_sha256': sha(source.read_bytes()),
              'script_sha256': sha(Path(__file__).read_bytes()), 'replacement_projection': rows,
              'summary': {'attempts': len(rows),
                'append_refusals_with_fitting_final_roots': sum(not r['appended'] and r['projected_final']['fits'] for r in rows),
                'maximum_required_candidate_staging_bytes': max(r['required_candidate_staging_bytes'] for r in rows),
                'maximum_candidate_staging_shortfall_bytes': max(r['candidate_staging_shortfall_bytes'] for r in rows)},
              'payload_bounds': {'fresh_v6_ghost_bytes': ghost_v6, 'legacy_ghost_prefix_bytes': ghost_legacy,
                'practice_pad_bytes': 236, 'practice_frames_bytes': 4096 * 16,
                'practice_transitions_bytes': 32 * 16, 'practice_total_bytes': practice,
                'fresh_v6_total_bytes': ghost_v6 + practice, 'legacy_total_bytes': ghost_legacy + practice,
                'metadata_available_captures': len(available),
                'captured_ghost_bytes_min': min(s['ghost_bytes'] for s in available),
                'captured_ghost_bytes_max': max(s['ghost_bytes'] for s in available),
                'captured_practice_frames_max': max(s['practice_frames'] for s in available),
                'scope': 'Raw snapshot span bounds, not packed-size predictions. Loaded playback is not snapshotted as a Ghost prefix. The synthetic maximum payload test uses arbitrary bytes and is not a legal gameplay capture.'}}
    (folder / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'summary': report['summary'], 'payload_bounds': report['payload_bounds']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--screen-only', action='store_true')
    parser.add_argument('--ppc-dolphin', type=Path)
    parser.add_argument('--ppc-input', type=Path)
    parser.add_argument('--summarize-input', type=Path)
    parser.add_argument('--canonical-input', type=Path)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT / 'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    if args.summarize_input:
        supplement(args.summarize_input, folder)
        return
    if args.ppc_dolphin and args.ppc_input:
        ppc(folder, args.ppc_dolphin, args.ppc_input)
        return
    report = {'scope': 'Exact historical PPC Quick streams; captured-data capacity and source payload bounds, not universal gameplay coverage or Wii timing.',
              'capacity_bytes': CAPACITY, 'bank_bytes': BANKS,
              'source_sha256': {f: sha((ROOT / f).read_bytes()) for f in FILES}}
    if args.canonical_input:
        report['scope'] = 'Private provisional zeroing of checked allocator free gaps; exact PPC streams and native Store, not a shipped implementation or live restoration proof.'
    states, sizes, report['input_receipts'] = load(args.canonical_input)
    report['captures'] = [s['info'] for s in states]
    report['screen'] = screen(states, sizes)
    print(json.dumps(report['screen']), flush=True)
    (folder / 'screen.json').write_text(json.dumps(report, indent=2) + '\n')
    if not args.screen_only:
        report['native'] = native(folder, states, report['screen'])
    (folder / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
