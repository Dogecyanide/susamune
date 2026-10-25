"""Package the frozen, validated cold-menu probe separately from release builds."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import zipfile

from gen_mod_bin import build_mod_bin
from package_launcher import launcher_files
from test_timewarp_mod_v4 import Harness, REGION_BYTES, SENTINEL
from timewarp_timer_guard import BASELINE, verify

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/timewarp-pinned-link/source-console'
OUT = ROOT / 'build/timewarp-wii-probe-1'
BOOT = OUT / 'frozen-boot.dol'
BOOT_SHA = '8d5c6dc226ef797122d002eb48415f81f83cbb7b75beca935ad107ed21a8c593'
APP = 'apps/moonshine_memory_probe'


def sha(data):
    return hashlib.sha256(data).hexdigest()


GUIDE = '''Moonshine Memory Probe 1 — private Wii test

This checks the relocated menu code and its boot/reset path on real Wii.
It uses the existing V2.3.3 gameplay and savestate behavior. The in-game
version still says V2.3.3. Three fast savestates and the new shared buffer
are not enabled in this probe.

Installation
Extract the ZIP into the SD card root. It adds apps/moonshine_memory_probe.
Keep apps/moonshine_launcher in place. In the Homebrew Channel choose
"Moonshine Memory Probe 1". JP, US and PAL mod files are included.
It uses your existing Moonshine configuration and data folders.

First pass
1. Start your usual game source. Note your disc region and whether this is
   a real disc, SD ISO or USB ISO. Report the last screen if boot stops.
2. Enter Delfino Plaza and open the Moonshine menu using your usual bind.
3. Visit every main tab and scroll through its rows. Open and close a nested
   page. Open the save-slot and load-source/slot selectors. Back out normally.
4. Save one RAM state, move Mario, then load it. Check that Mario appears,
   moves, and responds to input. No timing measurement is needed for this pass.
5. Use the Wii RESET button to return through the normal game reset, then
   reopen the mod menu after returning to gameplay.
6. Return to the Homebrew Channel by your usual method, launch this same
   probe again, and repeat opening the menu and saving/moving/loading Mario.
   RAM states are cleared by a fresh launch, so make a new save first.

Please report: boot result, menu/nested-page result, RAM save/load result,
RESET result, and second-launch result. If anything hangs, note the exact
last action; a crash-screen photo is useful if one appears.

After this test use the normal Moonshine Launcher entry for ordinary play.
The next memory test will cover the new three-slot storage once integrated.
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    boot = BOOT.read_bytes()
    if sha(boot) != BOOT_SHA:
        raise ValueError('Frozen validated probe loader changed; do not silently substitute a new build')
    verify(json.loads(BASELINE.read_text()), BUILD, 'console', ('jp', 'us', 'pal'))
    harness_dir = OUT / 'installer'
    harness_dir.mkdir(exist_ok=True)
    harness = Harness(harness_dir)
    rows = []
    try:
        for region in ('jp', 'us', 'pal'):
            manifest_path = BUILD / f'susamune_manifest_{region}.json'
            manifest = json.loads(manifest_path.read_text())
            if manifest['target'] != 'console' or manifest['transport_environment'] != 'console':
                raise ValueError('Console probe requires console linked code')
            proof_path = Path(manifest['pinned_link_receipt']['path'])
            proof = json.loads(proof_path.read_text())
            elf = BUILD / f'susamune_{region}.o'
            if sha(elf.read_bytes()) != proof['elf_sha256']:
                raise ValueError('Frozen probe ELF differs from its source-link receipt')
            packed = build_mod_bin(manifest, format_version=4, base_dir=BUILD)
            if packed != (BUILD / f'mod_{region}.bin').read_bytes():
                raise ValueError('Frozen probe container differs from its bound manifest')
            source = C.create_string_buffer(packed)
            expected = bytearray([SENTINEL]) * (REGION_BYTES + 128)
            for segment in manifest['segments']:
                start = 64 + segment['offset']
                raw = bytes.fromhex(segment['code'])
                expected[start:start + segment['memory_size']] = raw + bytes(segment['memory_size'] - len(raw))
            for attempt in range(2):
                memory = C.create_string_buffer(bytes([SENTINEL]) * len(expected))
                result = harness.lib.production_install(source, manifest['game_id'], len(packed),
                    C.addressof(memory) + 64, REGION_BYTES, manifest['base_addr'])
                if result or memory.raw[:-1] != expected or source.raw[:-1] != packed:
                    raise ValueError(f'{region} installation/reinstallation differs from linked segments')
            (OUT / f'mod_{region}.bin').write_bytes(packed)
            rows.append(dict(region=region, container_sha256=sha(packed), bytes=len(packed),
                manifest_sha256=sha(manifest_path.read_bytes()), proof_sha256=sha(proof_path.read_bytes()),
                elf_sha256=sha(elf.read_bytes()), cold=manifest['cold_image'],
                recovered_mem1_bytes=proof['recovered_bytes_remaining'], installs_checked=2))
    finally:
        harness.close()
    files = launcher_files(BOOT, [OUT / f'mod_{r}.bin' for r in ('jp', 'us', 'pal')],
                           version='Timewarp memory probe 1')
    files = {name.replace('apps/moonshine_launcher/', APP + '/', 1): data for name, data in files.items()}
    files[APP + '/meta.xml'] = b'''<?xml version="1.0" encoding="UTF-8"?>
<app version="1"><name>Moonshine Memory Probe 1</name>
<author>Moonshine contributors</author><version>Timewarp memory probe 1</version>
<short_description>Private Wii memory test</short_description>
<long_description>Cold menu code boot/reset probe. Existing V2.3.3 gameplay.
JP, US and PAL included. Keep the normal launcher installed.</long_description><ahb_access/></app>
'''
    files['TESTING.txt'] = GUIDE.encode('utf-8')
    archive = OUT / 'Moonshine-Timewarp-Memory-Probe-1.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr(name, data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or set(z.namelist()) != set(files):
            raise ValueError('Probe ZIP verification failed')
        for name, data in files.items():
            if z.read(name) != data:
                raise ValueError('Probe ZIP member changed')
    (OUT / 'TESTING.txt').write_text(GUIDE, encoding='utf-8')
    receipt = dict(complete=True, scope='Frozen cold-menu Wii probe; no chunk pool/shared activation/new V3 features.',
        boot_sha256=sha(boot), regions=rows, zip_sha256=sha(archive.read_bytes()),
        files={name: sha(data) for name, data in sorted(files.items())},
        sd_installed=False, published=False, actual_wii_result='awaiting user test')
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Validated private Wii probe: {archive}')


if __name__ == '__main__':
    main()
