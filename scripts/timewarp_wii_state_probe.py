"""Freeze the PAL shared-store Wii probe and optionally install its exact ZIP."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from gen_mod_bin import build_mod_bin, verified_artifact
from package_launcher import launcher_files
import timewarp_timer_guard as guard

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / 'build/timewarp-integrated-checkpoint-8-replay-cold'
IDENTITY = ROOT / 'build/timewarp-integrated-checkpoint-8/identity.json'
LINK = CHECKPOINT / 'console'
OUT = ROOT / 'build/timewarp-wii-state-probe-2'
APP = 'apps/moonshine_timewarp_test'
TITLE = 'Moonshine Timewarp State Test 2 (PAL)'
VERSION = '3.0.0 Timewarp - State Test 2'
ARCHIVE = OUT / 'Moonshine-3.0.0-Timewarp-State-Test-2-PAL.zip'

GUIDE = '''Moonshine 3.0.0 Timewarp - State Test 2 (PAL)

Choose "Moonshine Timewarp State Test 2 (PAL)" in the Homebrew Channel.
Use your PAL SD ISO and usual 60 Hz mode. Only the PAL mod is included.
This app shares your usual Moonshine settings/data. Its separate app folder
is apps/moonshine_timewarp_test; your ordinary launcher stays installed.

This private build enables the shared four-bank state pool, block sharing,
unused stage-heap canonicalization and bounded Quick replacement replay.
It also contains the wider MEM2 code relocation and 3.0.0 Timewarp branding.
The isolated PowerPC replacement and linked memory checks passed; this is
the first Wii gameplay test of these features together. Timing is unproved.

1. Boot and basic operation
Open the menu and a nested page in Delfino Plaza. Save one RAM state, move,
then load it. Check Mario appears and controls, camera and sound recover.
Stop here and report the last action/screen if anything fails.

2. Three occupied slots: Pinna 3, then Bianco 5
In each stage, save slots 1, 2 and 3 at distinguishable positions. Record
each save time. Once all three are occupied, load each and record its time.
Then replace an occupied slot (especially slot 3), move, and load again.
Report any slow save, refusal, incorrect position, missing Mario or freeze.
Time loads from timer freeze until the first frame with Mario visible,
matching your earlier measurements. Save timing ends when play resumes.

3. Different-level capacity and replacement
Start a fresh launch for this set so all RAM slots begin empty.
Save slot 1 in Bianco 1, slot 2 in Noki 1, and slot 3 in Gelato 1.
Then visit Bianco 5 and replace slot 1. Record that replacement's time.
Load slot 1 there. Return to Noki 1 and Gelato 1 to load slots 2 and 3 in
their matching episodes; these RAM states do not warp between levels.
Report if a saved slot disappears, is refused, or restores incorrectly.

4. Lifecycle
Use Wii RESET and check the menu after returning to gameplay. Relaunch the
test app from the Homebrew Channel and make/load a fresh RAM state.

Useful report
Stage | Save 1/2/3 | Load 1/2/3 after all slots occupied | Replacement time
Also report menu/boot, RESET/relaunch, errors, and anything visibly wrong.
A short video is useful for timing but not required. Long ghost recording
capacity is being checked separately; this first pass needs no long wait.
'''

SPEED_GUIDE = '''Moonshine 3.0.0 Timewarp - State Test 3 (PAL)

Choose "Moonshine Timewarp State Test 3 (PAL)" in the Homebrew Channel.
Use your PAL SD ISO and usual 60 Hz mode. Only the PAL mod is included.
This app shares your usual Moonshine settings/data. Its separate app folder
is apps/moonshine_timewarp_test3; the ordinary launcher and Test 2 stay installed.

This build keeps the memory savings and three Quick slots from Test 2,
removes repeated integrity scans and unnecessary block copies, and reuses
the fast 2.3.3 checksum implementation. Isolated PowerPC comparisons passed
with identical state data; complete Wii timings still need this measurement.

Main check: Pinna 3, with all three slots occupied
1. Start a fresh launch. Save slots 1, 2 and 3 at distinguishable positions.
   Record each save time.
2. Once all three slots are occupied, load each and record its time.
3. Replace each occupied slot once, and record those save times too.
   Move and reload to check the replacement returns to the right position.

Time loads from timer freeze until the FIRST FRAME WITH MARIO VISIBLE.
Time saves until play resumes. Use the same method as your Test 2 report.

Report: Save 1/2/3 | Load 1/2/3 | Overwrite 1/2/3, plus any errors, missing
Mario, freeze, incorrect restore or slowdown once all three slots are filled.
The target remains the fast 2.3.3 behavior in every slot.

If convenient, Bianco 5 and mixed-level replacement are useful next checks.
There is no need to repeat the full menu/lifecycle checklist unless something
behaves differently. Near-ten-minute recording capacity was checked separately.
'''


def configure(number, checkpoint, identity):
    global CHECKPOINT, IDENTITY, LINK, OUT, APP, TITLE, VERSION, ARCHIVE, GUIDE
    if (checkpoint is None) != (identity is None):
        raise ValueError('Checkpoint and identity must be supplied together')
    if number == 3 and checkpoint is None:
        raise ValueError('Test 3 requires its frozen checkpoint and identity')
    if checkpoint is not None:
        CHECKPOINT, IDENTITY = checkpoint.resolve(strict=True), identity.resolve(strict=True)
    LINK = CHECKPOINT / 'console'
    OUT = ROOT / f'build/timewarp-wii-state-probe-{number}'
    APP = 'apps/moonshine_timewarp_test' + ('3' if number == 3 else '')
    TITLE = f'Moonshine Timewarp State Test {number} (PAL)'
    VERSION = f'3.0.0 Timewarp - State Test {number}'
    ARCHIVE = OUT / f'Moonshine-3.0.0-Timewarp-State-Test-{number}-PAL.zip'
    if number == 3:
        GUIDE = SPEED_GUIDE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def installer_check(packed, manifest):
    directory = OUT / 'installer'
    directory.mkdir()
    source = directory / 'install.c'
    source.write_text('''#include "susamune/mod_bin.h"
__declspec(dllexport) int install(const struct SusamuneModHeader *p,
    unsigned g, unsigned n, void *d, unsigned cap, unsigned base) {
    return SusamuneModInstall(p,g,n,d,cap,base);
}
''', encoding='ascii')
    dll = directory / 'install.dll'
    subprocess.run([str(ROOT / 'toolchain/clang.exe'),
        '--target=x86_64-pc-windows-msvc', '-x', 'c', '-std=c11', '-O2',
        '-fno-builtin', '-ffreestanding', '-Wall', '-Wextra', '-Werror',
        '-I', str(ROOT / 'include'), '-shared', '-nostdlib', '-fuse-ld=lld',
        '-Wl,/noentry', str(source), '-o', str(dll)], check=True)
    library = C.CDLL(str(dll))
    try:
        library.install.argtypes = [C.c_void_p, C.c_uint, C.c_uint,
                                    C.c_void_p, C.c_uint, C.c_uint]
        payload = C.create_string_buffer(packed)
        expected = bytearray([0xA7]) * (0xC0000 + 128)
        for segment in manifest['segments']:
            start = 64 + segment['offset']
            raw = bytes.fromhex(segment['code'])
            expected[start:start + segment['memory_size']] = (
                raw + bytes(segment['memory_size'] - len(raw)))
        memory = C.create_string_buffer(bytes([0xA7]) * len(expected))
        status = library.install(payload, manifest['game_id'], len(packed),
            C.addressof(memory) + 64, 0xC0000, manifest['base_addr'])
        if status or memory.raw[:-1] != expected or payload.raw[:-1] != packed:
            raise ValueError('Production installer output or protected canaries differ')
    finally:
        C.windll.kernel32.FreeLibrary(C.c_void_p(library._handle))
    return {'passed': True, 'scope': 'One native production installer pass on exact PAL package; not Wii execution',
            'source_sha256': sha(source.read_bytes()), 'dll_sha256': sha(dll.read_bytes())}


def package(launcher_receipt):
    if OUT.exists():
        raise ValueError('Probe output is create-only')
    launcher = load(launcher_receipt)
    if not launcher.get('passed'):
        raise ValueError('Launcher build receipt did not pass')
    boot_path = Path(launcher['boot']['path'])
    boot = boot_path.read_bytes()
    if sha(boot) != launcher['boot']['sha256']:
        raise ValueError('Launcher changed after build receipt')
    for name, value in launcher['source_sha256'].items():
        if sha((ROOT / name).read_bytes()) != value:
            raise ValueError('Launcher/shared source changed: ' + name)
    checkpoint = load(CHECKPOINT / 'receipt.json')
    identity_path = IDENTITY
    identity = load(identity_path)
    expected_flags = {'TIMEWARP_SHARED_STORE=1', 'TIMEWARP_HEAP_GAP=1',
                      'TIMEWARP_QUICK_REPLAY=1', 'IS_EMULATOR=0'}
    if not checkpoint['passed'] or not identity['passed'] or set(identity['flags']) != expected_flags:
        raise ValueError('PAL build flags differ')
    if checkpoint['snapshot_receipt_sha256'] != identity['source_snapshot_receipt_sha256']:
        raise ValueError('PAL source identity differs')
    manifest_path = LINK / 'manifest-pal.json'
    manifest = load(manifest_path)
    if manifest['target'] != 'console' or manifest['transport_environment'] != 'console':
        raise ValueError('Probe requires console code')
    proof = json.loads(verified_artifact(manifest['pinned_link_receipt'], LINK, 'link proof'))
    if sha((LINK / 'susamune_pal.o').read_bytes()) != proof['elf_sha256']:
        raise ValueError('PAL ELF differs from its verified link')
    protected = load(guard.BASELINE)['builds']['console-pal']
    guard.compare(protected['symbols'], guard.linked_symbols(LINK / 'susamune_pal.o',
        protected['globals']), 'packaged PAL timer')
    packed = build_mod_bin(manifest, format_version=4, base_dir=LINK)
    if packed != (LINK / 'mod-pal.bin').read_bytes() or len(packed) != checkpoint['mod_bytes']:
        raise ValueError('PAL container differs from frozen checkpoint')
    cold = verified_artifact(manifest['cold_image'], LINK, 'cold code')
    image = b''.join(bytes.fromhex(s['code']) for s in manifest['segments']) + cold
    if b'3.0.0' not in image or not (b'Timewarp' in image or b'TIMEWARP' in image):
        raise ValueError('Linked Timewarp branding absent')
    OUT.mkdir()
    (OUT / 'boot.dol').write_bytes(boot)
    (OUT / 'mod_pal.bin').write_bytes(packed)
    install = installer_check(packed, manifest)
    files = launcher_files(OUT / 'boot.dol', [OUT / 'mod_pal.bin'], source='sd', version=VERSION)
    files = {name.replace('apps/moonshine_launcher/', APP + '/', 1): data for name, data in files.items()}
    files[APP + '/meta.xml'] = (f'''<?xml version="1.0" encoding="UTF-8"?>
<app version="1"><name>{TITLE}</name><author>Moonshine contributors</author>
<version>{VERSION}</version><short_description>PAL three-slot Wii test</short_description>
<long_description>Private PAL-only test of shared RAM savestates, heap savings and Quick replacement.
Use your PAL game in 60 Hz mode. See TESTING.txt.</long_description><ahb_access/></app>
''').encode('utf-8')
    files[APP + '/TESTING.txt'] = GUIDE.encode('utf-8')
    with zipfile.ZipFile(ARCHIVE, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError('ZIP structure failed')
        if any(archive.read(name) != data for name, data in files.items()):
            raise ValueError('ZIP contents differ')
    (OUT / 'TESTING.txt').write_text(GUIDE, encoding='utf-8')
    receipt = {'passed': True, 'scope': 'PAL private Wii test package, hardware results pending',
        'archive': {'path': str(ARCHIVE), 'sha256': sha(ARCHIVE.read_bytes())},
        'launcher_receipt': {'path': str(launcher_receipt), 'sha256': sha(launcher_receipt.read_bytes())},
        'checkpoint_receipt_sha256': sha((CHECKPOINT / 'receipt.json').read_bytes()),
        'identity_sha256': sha(identity_path.read_bytes()), 'flags': sorted(expected_flags),
        'boot_sha256': sha(boot), 'mod_sha256': sha(packed), 'mod_bytes': len(packed),
        'free_mem1_bytes': checkpoint['remaining_bytes'], 'protection': checkpoint['protection'],
        'installer': install, 'files': {n: {'bytes': len(d), 'sha256': sha(d)} for n, d in files.items()}}
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'passed': True, 'archive': str(ARCHIVE), 'files': len(files),
                      'mod_bytes': len(packed), 'free_mem1_bytes': checkpoint['remaining_bytes']}))


def install_sd(sd):
    receipt = load(OUT / 'receipt.json')
    if not receipt['passed'] or sha(ARCHIVE.read_bytes()) != receipt['archive']['sha256']:
        raise ValueError('Package receipt differs')
    sd = sd.resolve(strict=True)
    ordinary = sd / 'Apps/moonshine_launcher'
    meta = ordinary / 'meta.xml'
    if not meta.is_file() or 'Moonshine' not in ET.fromstring(meta.read_bytes()).findtext('name', ''):
        raise ValueError('Expected Moonshine SD layout absent')
    preserved = {p: sha(p.read_bytes()) for p in (meta, ordinary / 'boot.dol')}
    target = (sd / APP).resolve()
    if not target.is_relative_to(sd / 'apps') or target.exists():
        raise ValueError('Separate test app must be new and inside SD apps')
    with zipfile.ZipFile(ARCHIVE) as archive:
        for name in archive.namelist():
            relative = Path(name)
            destination = (sd / relative).resolve()
            if not name.startswith(APP + '/') or '..' in relative.parts or not destination.is_relative_to(target):
                raise ValueError('Unexpected package destination')
        for name in archive.namelist():
            destination = sd / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
    for name, expected in receipt['files'].items():
        installed = (sd / name).read_bytes()
        if len(installed) != expected['bytes'] or sha(installed) != expected['sha256']:
            raise ValueError('SD file differs: ' + name)
    if ET.fromstring((target / 'meta.xml').read_bytes()).findtext('version') != VERSION:
        raise ValueError('Installed version differs')
    if any(sha(path.read_bytes()) != before for path, before in preserved.items()):
        raise ValueError('Ordinary launcher unexpectedly changed')
    installed = {'passed': True, 'target': str(target), 'title': TITLE, 'version': VERSION,
        'archive_sha256': receipt['archive']['sha256'], 'files': receipt['files'],
        'ordinary_launcher_boot_meta_unchanged': True}
    (OUT / 'sd-install-receipt.json').write_text(json.dumps(installed, indent=2) + '\n')
    print(json.dumps({'installed': str(target), 'files_verified': len(receipt['files']), 'title': TITLE}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--launcher-receipt', type=Path)
    mode.add_argument('--install-sd', type=Path)
    parser.add_argument('--test-number', type=int, choices=(2, 3), default=2)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--identity', type=Path)
    args = parser.parse_args()
    configure(args.test_number, args.checkpoint, args.identity)
    if args.launcher_receipt:
        package(args.launcher_receipt.resolve())
    else:
        install_sd(args.install_sd)
