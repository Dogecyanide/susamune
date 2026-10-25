"""Verify actual opt-in builds against the released hot images and shared installer."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import tempfile

from elftools.elf.elffile import ELFFile

from gen_mod_bin import build_mod_bin
from mod_transport import ROOT, GAMES, BASES
from test_timewarp_mod_v4 import Harness, REGION_BYTES, SENTINEL
from timewarp_timer_guard import verify


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_hot_delta(manifest, original, elf_path, extended_input):
    changes = []
    for actual, prior in zip(manifest['segments'], original['segments']):
        assert actual['offset'] == prior['offset'] and actual['memory_size'] == prior['memory_size']
        a, b = bytes.fromhex(prior['code']), bytes.fromhex(actual['code'])
        assert len(a) == len(b)
        for i in range(0, len(a), 4):
            if a[i:i+4] != b[i:i+4]:
                changes.append(dict(address=manifest['base_addr'] + actual['offset'] + i,
                                    before=a[i:i+4].hex(), after=b[i:i+4].hex()))
    if not extended_input:
        assert not changes
        return changes
    assert len(changes) == 1 and changes[0]['before'] == '2808003f' and changes[0]['after'] == '28080100'
    with elf_path.open('rb') as stream:
        symbols = [s for s in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()
                   if 'checkSource' in s.name and s['st_size']]
        assert len(symbols) == 1
        start, size = symbols[0]['st_value'], symbols[0]['st_size']
        assert start <= changes[0]['address'] < start + size
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/timewarp-transport-integration/receipt.json')
    parser.add_argument('--extended-input', action='store_true',
                        help='Admit only the checked 64-to-257 decoder source-count compare change')
    args = parser.parse_args()
    paths = [ROOT / p for p in (
        'include/susamune/mod_bin.h', 'include/susamune/mod_quick.h', 'include/susamune/mod_v4.h',
        'include/susamune/mod_boot.h', 'scripts/gen_mod_bin.py', 'scripts/mod_transport.py',
        'launcher/kernel/Patch.c', 'launcher/kernel/asm/FakeEntryLoad.S',
        'launcher/loader/source/SusamuneMod.c', 'scripts/timewarp_timer_guard.py',
        'scripts/test_timewarp_mod_v4.py', 'scripts/timewarp_transport_integration.py',
        'src/state_codec.cpp', 'include/susamune/state_codec.hxx')]
    sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
    baseline = json.loads((ROOT / 'doc/timewarp-timer-baseline.json').read_text())
    rows = []
    with tempfile.TemporaryDirectory(prefix='timewarp-integrated-') as temporary:
        harness = Harness(temporary)
        try:
            for target in ('console', 'emu'):
                build = ROOT / f'build/timewarp-{target}'
                verify(baseline, build, target, ('jp', 'us', 'pal'))
                for region in ('jp', 'us', 'pal'):
                    released = ROOT / f'build/baseline-{target}'
                    manifest = json.loads((build / f'susamune_manifest_{region}.json').read_text())
                    original = json.loads((released / f'susamune_manifest_{region}.json').read_text())
                    changes = check_hot_delta(manifest, original, build / f'susamune_{region}.o', args.extended_input)
                    assert manifest['writes'] == original['writes']
                    image = build / f'mod_{region}.bin'
                    encoded = image.read_bytes()
                    assert encoded == build_mod_bin(manifest, format_version=4)
                    assert build_mod_bin(original) == (released / image.name).read_bytes()
                    expected = bytearray([SENTINEL]) * (REGION_BYTES + 128)
                    for segment in manifest['segments']:
                        start = 64 + segment['offset']
                        raw = bytes.fromhex(segment['code'])
                        expected[start:start + len(raw)] = raw
                        expected[start + len(raw):start + segment['memory_size']] = bytes(segment['memory_size'] - len(raw))
                    source = C.create_string_buffer(encoded)
                    memory = C.create_string_buffer(bytes([SENTINEL]) * (REGION_BYTES + 128))
                    game = GAMES[region]
                    for repeat in range(2):
                        if repeat:
                            # Reinstall after mutable hot bytes changed, preserving the protected gaps.
                            for segment in manifest['segments']:
                                C.memset(C.addressof(memory) + 64 + segment['offset'], 0xCC, segment['memory_size'])
                        status = harness.lib.production_install(source, game, len(encoded),
                            C.addressof(memory) + 64, REGION_BYTES, BASES[game])
                        assert status == 0 and memory.raw[:-1] == expected
                        assert source.raw[:len(encoded)] == encoded
                    bad = bytearray(encoded)
                    bad[-1] ^= 1
                    rejected = C.create_string_buffer(bytes(bad))
                    before = memory.raw
                    assert harness.lib.production_install(rejected, game, len(bad),
                        C.addressof(memory) + 64, REGION_BYTES, BASES[game]) != 0
                    assert memory.raw == before
                    rows.append(dict(target=target, region=region, container_bytes=len(encoded),
                        container_sha256=sha(image), linked_elf_sha256=sha(build / f'susamune_{region}.o'),
                        baseline_container_sha256=sha(released / image.name),
                        expected_source_changes=changes,
                        initialized_bytes_bss_hooks_exact=True, source_immutable=True,
                        protected_holes_preserved=True, reinstall_exact=True,
                        corrupt_file_refused_before_writes=True, timer_symbols_unchanged=96))
        finally:
            harness.close()
    assert sources == {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
    result = dict(scope='Actual six opt-in builds; shared native installer; full hot image, BSS, hooks, gaps and timer checks.',
        limitations='No cold image in these builds. Native reset simulation is not actual Wii boot/reset or cache execution.',
        sources=sources, builds=rows,
        launcher_boot_sha256=sha(ROOT / 'build/timewarp-launcher/shared/boot.dol'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'All six integrated images passed; receipt: {args.output}')


if __name__ == '__main__':
    main()
