"""Private free-gap restore pilot using a historical PAL game fixture.

Only the owned process is edited. The checked saved stream, not live free RAM,
is canonicalized. This isolates heap lifetime from a future encoder change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import time
import zlib

from timewarp_cross_level_slots import Slots, ROOT, digest
from timewarp_heap_gap_measure import gap
from timewarp_stress_slots import entry_index, CASES


def tag(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


class Pilot(Slots):
    def u32(self, address):
        return struct.unpack('>I', self.read(address, 4))[0]

    def call(self, name, *args):
        if name not in ('alloc__12JKRSolidHeapFUli', 'freeTail__12JKRSolidHeapFv',
                        'check__12JKRSolidHeapFv'):
            return super().call(name, *args)
        if self.u32(self.callbox) or len(args) > 3:
            raise RuntimeError('Private callbox busy')
        values = [value & 0xffffffff for value in args] + [0] * (3 - len(args))
        self.write(self.callbox + 4, struct.pack('>4I', *values, 0xffffffff))
        self.write(self.callbox, struct.pack('>I', self.symbols[name]))
        deadline = time.monotonic() + 10
        while self.u32(self.callbox):
            self.alive(deadline)
            time.sleep(0.02)
        return self.u32(self.callbox + 16)

    def heap(self):
        address = self.u32(self.symbols['gpApplication'] + 0x40)
        data = self.read(address, 0x78)
        start, end, size = struct.unpack_from('>3I', data, 0x30)
        free, head, tail = struct.unpack_from('>3I', data, 0x68)
        assert self.u32(address) == self.symbols['__vt__12JKRSolidHeap']
        assert address < start <= head <= tail <= end and size == end - start
        assert free == tail - head and self.call('check__12JKRSolidHeapFv', address) == 1
        return dict(address=address, start=start, end=end, free=free, head=head, tail=tail)

    def enter(self, name):
        label, area, episode, _ = CASES[name]
        assert self.call('start__5ILingFiUl', entry_index(label), 0) == 1
        self.wait(lambda s: s['scene'] == area << 8 | episode and s['state'] == 4,
                  skip_movie=True, timeout=180)
        time.sleep(0.5)

    def allocate(self, size, alignment):
        before = self.heap()
        pointer = self.call('alloc__12JKRSolidHeapFUli', before['address'], size, alignment)
        assert before['head'] <= pointer and pointer + size <= before['tail']
        assert pointer % abs(alignment) == 0
        after = self.heap()
        assert after['free'] < before['free'] and before['end'] == after['end']
        return pointer

    def install(self, raw_path):
        original = raw_path.read_bytes()
        metadata = bytearray(raw_path.with_suffix('.metadata').read_bytes())
        assert len(metadata) == 6936 and tag(metadata[:-4]) == struct.unpack_from('>I', metadata, 6932)[0]
        filtered, info = gap(original, metadata)
        packed = zlib.compress(filtered, 1)
        assert zlib.decompress(packed) == filtered
        pool = self.read(self.symbols['sPool__0'], 28)
        offset, size, off1, size1, off2, size2, used = struct.unpack('>7I', pool)
        assert (offset, off1, size1, off2, size2) == (0, 0, 0, 0, 0) and size == used
        assert len(packed) <= size
        banks = struct.unpack('>4I', self.read(self.symbols['sPoolMemory__0'], 16))
        assert size <= banks[2]
        current = self.heap()
        first = int(info['allocated_head_end'], 16)
        free_before = self.read(first, info['free_bytes'])
        assert current['head'] == first and current['tail'] == int(info['allocated_tail_start'], 16)
        # Slot zero is the only root, so shortening it needs no pool relocation.
        self.write(0x712D2F00, bytes(4))
        self.write(banks[0], packed)
        self.write(self.symbols['sPool__0'], struct.pack('>7I', 0, len(packed), 0, 0, 0, 0, len(packed)))
        struct.pack_into('>2I', metadata, 6920, len(packed), zlib.adler32(filtered))
        struct.pack_into('>I', metadata, 6932, tag(metadata[:-4]))
        self.write(self.symbols['sPackedChecksums__0'], struct.pack('>I', zlib.crc32(packed)))
        self.write(0x712D2F00, bytes(metadata))
        assert self.read(banks[0], len(packed)) == packed
        assert self.read(0x712D2F00, 6936) == metadata
        assert self.read(first, info['free_bytes']) == free_before
        return dict(**info, packed_bytes=len(packed), live_free_bytes_unchanged_before_load=True,
                    allocated_snapshot_bytes_unchanged=True,
                    canonical_raw_sha256=hashlib.sha256(filtered).hexdigest())

    def restore(self, expected_heap, canaries, position):
        self.feed(x=85, duration=0.45)
        pointer = self.u32(self.symbols['gpMarioPos'])
        before = struct.unpack('>3f', self.read(pointer, 12))
        assert sum((a - b) ** 2 for a, b in zip(before, position)) > 100
        for address, data in canaries:
            self.write(address, bytes([0xa5]) * len(data))
        manager = self.u32(self.symbols['gSavestateMgr'])
        assert self.call('selectLoadSlot__16SavestateManagerFUl', manager, 0) == 1
        self.feed(2, duration=0.08)
        deadline = time.monotonic() + 30
        while any(self.read(address, len(data)) != data for address, data in canaries):
            self.alive(deadline)
            time.sleep(0.02)
        restored = struct.unpack('>3f', self.read(pointer, 12))
        assert sum((a - b) ** 2 for a, b in zip(restored, position)) < 25
        assert self.heap() == expected_heap
        free = self.read(expected_heap['head'], expected_heap['free'])
        assert free == bytes(len(free))
        return dict(before_position=before, restored_position=restored,
                    allocated_head_tail_canaries_restored=True, heap_cursors_restored=True,
                    entire_free_interval_zero=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT / 'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    report = dict(passed=False, scope='One focused historical PAL game pilot: canonical-gap Deflate stream installed in private RAM slot, real D-right restores, retail head/tail allocations and stage transitions. Not production encoder, shared store, Wii, determinism or universal uninitialized-read proof.')
    game = Pilot(args.dolphin, folder, args.fixture.resolve())
    report['runtime'] = game.evidence
    timer_before = digest(ROOT / 'src/qft_timer.cpp')
    try:
        with game:
            deadline = time.monotonic() + 100
            while game.state()['scene'] != 0xf00 or game.state()['state'] != 4:
                game.alive(deadline)
                game.feed(0x1000)
            time.sleep(2)
            game.enter('pinna3')
            initial = game.heap()
            assert initial['tail'] == initial['end'] and initial['free'] > 0x40000
            rng = random.Random(0x48504150)
            canaries = [(game.allocate(4096, 32), rng.randbytes(4096)),
                        (game.allocate(4096, -32), rng.randbytes(4096))]
            for address, data in canaries:
                game.write(address, data)
            expected = game.heap()
            path = folder / 'before.raw'
            game.save(path, 'Pinna 3 with allocated head and tail canaries', 13, 1)
            position = game.rows[-1]['mario_position']
            report['gap'] = game.install(path)
            report['restores'] = [game.restore(expected, canaries, position)]
            # Both frontiers advance after the save, then rewind on restore.
            late = [game.allocate(4096, 64), game.allocate(4096, -64)]
            for address in late:
                game.write(address, bytes([0x5a]) * 4096)
            report['late_allocations'] = late
            report['restores'].append(game.restore(expected, canaries, position))
            game.call('freeTail__12JKRSolidHeapFv', expected['address'])
            assert game.heap()['tail'] == expected['end']
            report['restores'].append(game.restore(expected, canaries, position))
            # Continued input exercises gameplay between restore and stage teardown.
            for buttons, x, y in ((0x100, 45, 0), (0x20, 0, 50), (0x100, -45, 0)):
                game.feed(buttons, x=x, y=y, duration=0.8)
            assert game.state()['scene'] == 0xd01 and game.state()['stage_setup']
            report['gameplay_heap_check'] = game.heap()
            report['transitions'] = []
            for name in ('bianco5', 'noki1'):
                game.enter(name)
                report['transitions'].append(dict(stage=name, state=game.state(), heap=game.heap()))
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['protected_timer_source_unchanged'] = digest(ROOT / 'src/qft_timer.cpp') == timer_before
        (folder / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
