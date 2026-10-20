"""Capture selected stress stages after all three RAM slots are occupied.

Uses a read-only historical PAL fixture in an owned Dolphin process. Captures
and codec choices are capacity evidence, never substitutes for Wii timings.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import time

from timewarp_cross_level_slots import Slots, ROOT, digest

CASES = {'bianco5': ('Bianco 5', 2, 4, 4), 'pinna3': ('Pinna 3', 13, 1, 2),
         'noki1': ('Noki 1', 9, 0, 0)}


def shine_addresses(capture, symbols):
    raw = Path(capture['path']).read_bytes()
    metadata = Path(capture['metadata_path']).read_bytes()
    count = struct.unpack_from('>I', metadata, 24)[0]
    spans = [struct.unpack_from('>III', metadata, 40 + i * 12) for i in range(count)]

    def read(address, size):
        matches = [offset + address - base for base, length, offset in spans
                   if base <= address and size <= base + length - address]
        if len(matches) != 1:
            raise ValueError('Shine probe address is outside one saved region')
        return raw[matches[0]:matches[0] + size]

    word = lambda address: struct.unpack('>I', read(address, 4))[0]
    heap, size = struct.unpack_from('>2I', metadata, 12)
    heap_bytes = read(heap, size)
    marker = struct.pack('>I', symbols['__vt__6TShine'])
    shines, at = [], heap_bytes.find(marker)
    while at >= 0:
        address = heap + at
        if not address % 4:
            manager = word(address + 0x70)
            if word(manager) != symbols['__vt__18TMapObjBaseManager']:
                raise ValueError('Shine candidate has an unexpected owner vtable')
            capacity, objects, array = struct.unpack('>3I', read(manager + 0x10, 12))
            if not 0 < objects <= capacity <= 4096:
                raise ValueError('Shine manager count exceeds the bounded probe')
            pointers = struct.unpack('>' + 'I' * objects, read(array, objects * 4))
            if address not in pointers or word(address + 0x4c) != 0x20000013:
                raise ValueError('Shine candidate is not a registered shine actor')
            shines.append(dict(address=hex(address), manager=hex(manager), manager_objects=objects))
        at = heap_bytes.find(marker, at + 1)
    return dict(scope='Saved heap TShine objects checked against manager membership and actor type; not a whole-game allocation maximum.',
                shines=shines, highest_shine=hex(max(int(s['address'], 16) for s in shines)) if shines else None,
                heap_first=hex(heap), heap_end=hex(heap + size), checked_shines=len(shines))


def entry_index(label):
    labels = re.findall(r'^[A-Z_]+\("([^"]+)"', (ROOT / 'src/iling_entries.inc').read_text(), re.M)
    if labels.count(label) != 1:
        raise ValueError('Ambiguous IL entry: ' + label)
    return labels.index(label)


def check_loads(game, saved):
    manager = struct.unpack('>I', game.read(game.symbols['gSavestateMgr'], 4))[0]
    position_address = struct.unpack('>I', game.read(game.symbols['gpMarioPos'], 4))[0]
    def position():
        return struct.unpack('>3f', game.read(position_address, 12))
    rows = []
    for slot, metadata in enumerate(saved):
        expected = metadata['mario_position']
        game.feed(x=90, duration=0.5)
        before = position()
        distance = lambda p: sum((a-b)**2 for a, b in zip(p, expected))
        if distance(before) < 100:
            raise RuntimeError('Movement did not distinguish the saved position')
        if game.call('selectLoadSlot__16SavestateManagerFUl', manager, slot) != 1:
            raise RuntimeError('Load selection refused')
        game.feed(2, duration=0.08)
        deadline = time.monotonic() + 60
        while distance(position()) > 25:
            game.alive(deadline)
            time.sleep(0.01)
        rows.append(dict(slot=slot+1, expected_position=expected, before_position=before,
                         restored_position=position(), position_tolerance_units=5,
                         scope='Ordinary D-right restore and saved position check; not whole-state or timing equality.'))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/timewarp-stress-slots')
    parser.add_argument('--stages', nargs='+', choices=tuple(CASES), default=['bianco5', 'pinna3'])
    args = parser.parse_args()
    folder, fixture = args.out.resolve(), args.fixture.resolve()
    if not folder.is_relative_to((ROOT / 'build').resolve()) or folder.is_relative_to(fixture):
        parser.error('Outputs must be private to this task build directory')
    folder.mkdir(parents=True, exist_ok=True)
    receipt = dict(scope='Historical PAL Snapshot17 actual save fallback after three occupied slots; no Wii timing claim.',
                   fixture_sha256=digest(fixture / 'input.iso'), cases=[])
    timer_before = digest(ROOT / 'src/qft_timer.cpp')
    try:
        for name in args.stages:
            label, area, episode, parent = CASES[name]
            case = dict(name=name, label=label, requested_scene=[area, episode, parent])
            receipt['cases'].append(case)
            game = Slots(args.dolphin, folder / name, fixture)
            case['runtime'] = game.evidence
            with game:
                deadline = time.monotonic() + 180
                while game.state()['scene'] != 0xf00 or game.state()['state'] != 4:
                    game.alive(deadline)
                    game.feed(0x1000)
                time.sleep(3)
                index = entry_index(label)
                case['entry_index'] = index
                if game.call('start__5ILingFiUl', index, 0) != 1:
                    raise RuntimeError('IL start refused: ' + label)
                game.wait(lambda s: s['scene'] == area << 8 | episode and s['state'] == 4,
                          skip_movie=True, timeout=180)
                time.sleep(1)
                for slot in range(3):
                    if slot:
                        game.feed(x=60 if slot == 1 else -60, y=20, duration=0.5)
                    game.save(folder / name / 'initial' / f'slot{slot+1}.raw',
                              label + f' initial slot {slot+1}', area, episode, slot)
                    if game.rows[-1]['parent_episode'] != parent:
                        raise RuntimeError('Captured parent episode mismatch')
                for slot in range(3):
                    game.save(folder / name / 'occupied' / f'slot{slot+1}.raw',
                              label + f' after third save slot {slot+1}', area, episode, slot, False)
                saved = game.rows[-3:]
                case['shine_probe'] = shine_addresses(saved[0], game.symbols)
                case['occupied_loads'] = check_loads(game, saved)
                case['replacements'] = []
                for slot in range(3):
                    game.feed(x=-60, y=30, duration=0.5)
                    game.save(folder / name / 'replacement' / f'slot{slot+1}.raw',
                              label + f' replacement slot {slot+1}', area, episode, slot)
                    saved[slot] = game.rows[-1]
                    case['replacements'].append(dict(slot=slot+1, loads=check_loads(game, saved)))
                case['captures'] = game.rows
                case['completed'] = True
    except Exception as error:
        receipt['error'] = str(error)
        raise
    finally:
        receipt['timer_source_unchanged'] = digest(ROOT / 'src/qft_timer.cpp') == timer_before
        (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
