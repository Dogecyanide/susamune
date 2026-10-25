"""Freeze and package the private two-Wii online prototype; SD install is explicit."""
import argparse
import ctypes as C
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

from elftools.elf.elffile import ELFFile
from gen_mod_bin import build_mod_bin, verified_artifact
from package_launcher import launcher_files
import timewarp_timer_guard as guard

ROOT = Path(__file__).resolve().parents[1]
APP = 'apps/moonshine_timewarp_test3'
TITLE = 'Moonshine Timewarp Online Prototype 10'
VERSION = '3.0.0 Timewarp'
REGIONS = ('jp', 'us', 'pal')
FLAGS = {'TIMEWARP_SHARED_STORE=1', 'TIMEWARP_HEAP_GAP=1',
         'TIMEWARP_QUICK_REPLAY=1', 'TIMEWARP_LIVE_RACING=1', 'IS_EMULATOR=0'}

GUIDE_PATH = ROOT / 'doc/timewarp-online-testing.txt'
RELAY_FILES = ('server.py', 'README.md', 'start-windows.cmd', 'moonshine-relay.service')
STATE_SHARE_FILES = ('StateShare.cs', 'StateShare.ps1', 'Import a state.cmd',
                     'Share a state.cmd', 'README.txt')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def artifact(path):
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size,
            'sha256': sha(path.read_bytes())}


def relay_archive(out):
    source = ROOT / 'tools/live_relay'
    files = {'moonshine-live-relay/' + name: (source / name).read_bytes()
             for name in RELAY_FILES}
    archive = out / 'Moonshine-3.0.0-Timewarp-Relay-Server-5.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as packed:
        for name, data in sorted(files.items()):
            packed.writestr(name, data)
    with zipfile.ZipFile(archive) as packed:
        if (packed.testzip() is not None or sorted(packed.namelist()) != sorted(files) or
                any(packed.read(name) != data for name, data in files.items())):
            raise ValueError('Relay archive readback differs')
    if any((source / name).read_bytes() != files['moonshine-live-relay/' + name]
           for name in RELAY_FILES):
        raise ValueError('Relay source changed during packaging')
    return {'passed': True, 'archive': artifact(archive),
            'scope': 'Deployable server files only; no public host or deployment',
            'files': {name: {'bytes': len(data), 'sha256': sha(data)}
                      for name, data in files.items()}}


def package_server(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = relay_archive(out)
    save(out / 'receipt.json', receipt)
    print(json.dumps({'passed': True, 'archive': receipt['archive']['path'],
                      'scope': receipt['scope']}))


def launcher_sources():
    paths = {p for p in (ROOT / 'launcher').rglob('*') if p.is_file()
             and 'nintendont_devkitpro' not in p.parts and '.git' not in p.parts}
    queue = [p for p in paths if p.suffix.lower() in ('.h', '.c', '.cpp', '.s')]
    visited = set()
    while queue:
        p = queue.pop()
        if p in visited:
            continue
        visited.add(p)
        for name in re.findall(r'^\s*#\s*include\s*["<]([^">]+)',
                               p.read_text(errors='replace'), re.M):
            choices = (p.parent / name, ROOT / 'include' / name)
            for candidate in choices:
                if candidate.is_file() and candidate.resolve().is_relative_to(ROOT):
                    candidate = candidate.resolve()
                    if 'nintendont_devkitpro' not in candidate.parts:
                        paths.add(candidate)
                        queue.append(candidate)
                    break
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(paths)}


def kernel_budget(path):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf.little_endian or elf['e_machine'] != 'EM_ARM':
            raise ValueError('Kernel is not the big-endian ARM image')
        sections = {s.name: {'address': s['sh_addr'], 'bytes': s['sh_size']}
                    for s in elf.iter_sections() if s['sh_flags'] & 2}
        for name, section in sections.items():
            start, end = section['address'], section['address'] + section['bytes']
            bounds = ((0x12f00000, 0x12f60000) if name in ('.init', '.text') else
                      (0x12fe0000, 0x12ff0000) if name == '.stack' else
                      (0x12f60000, 0x12fe0000))
            if not bounds[0] <= start <= end <= bounds[1]:
                raise ValueError('Kernel section escapes its reservation: ' + name)
        symbols = list(elf.get_section_by_name('.symtab').iter_symbols())
        names = {s.name for s in symbols}
        required = ('MoonshineNetInit', 'MoonshineNetShutdown', 'MoonshineNetBridgeInit',
                    'MoonshineNetBridgeService', 'MoonshineNetBridgeRetire',
                    'SusamuneTransferInit', 'SusamuneStateStorageService', 'PatchSusamune')
        if any(name not in names for name in required):
            raise ValueError('Online/shared-store kernel symbols absent')
        mailbox = [s for s in symbols if s.name == 'sMailbox' and s['st_size'] == 2720]
        if len(mailbox) != 1 or mailbox[0]['st_value'] % 32:
            raise ValueError('Expected aligned 2720-byte online mailbox absent')
        code_end = max(s['address'] + s['bytes'] for n, s in sections.items()
                       if n in ('.init', '.text'))
        data_end = max(s['address'] + s['bytes'] for n, s in sections.items()
                       if n not in ('.init', '.text', '.stack'))
        if sections['.stack'] != {'address': 0x12fe0000, 'bytes': 0x2000}:
            raise ValueError('Kernel main stack reservation changed')
        return {'sections': sections, 'text_remaining_bytes': 0x12f60000 - code_end,
                'data_bss_remaining_bytes': 0x12fe0000 - data_end,
                'mailbox_physical_address': mailbox[0]['st_value'], 'mailbox_bytes': 2720,
                'required_symbols': required}


def build_launcher(args):
    out, tree = args.output.resolve(), args.build_tree.resolve(strict=True)
    out.mkdir(parents=True, exist_ok=False)
    before = launcher_sources()
    save(out / 'source-before.json', before)
    commands = [[str(args.cmake), '-S', str(ROOT / 'launcher'), '-B', str(tree),
                 '-DTIMEWARP_LIVE_RACING=ON', '-DLAUNCHER_DEFAULT_SOURCE=sd',
                 '-DLAUNCHER_DISABLE_SUSAMUNE_PATCH=OFF', '-DLAUNCHER_VERSION=' + VERSION],
                [str(args.cmake), '--build', str(tree), '--target', 'wii', '--parallel', '4']]
    env = dict(os.environ, TEMP=str(out), TMP=str(out))
    start = time.monotonic()
    with (out / 'build.log').open('w', encoding='utf-8') as log:
        for command in commands:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
    after = launcher_sources()
    save(out / 'source-after.json', after)
    changed = [n for n in sorted(before.keys() | after.keys()) if before.get(n) != after.get(n)]
    if changed:
        raise ValueError('Launcher sources changed during build: ' + ', '.join(changed))
    build = {'commands': commands, 'elapsed_seconds': round(time.monotonic() - start, 2),
             'exit_code': 0}
    save(out / 'build-result.json', build)
    freeze_launcher(tree, out, after, build)


def freeze_launcher(tree, out, after, build):
    cache = (tree / 'CMakeCache.txt').read_text()
    arm_cache = (tree / 'group-arm/CMakeCache.txt').read_text()
    for name, value in (('TIMEWARP_LIVE_RACING', 'ON'), ('LAUNCHER_DISABLE_SUSAMUNE_PATCH', 'OFF')):
        required = rf'^{name}:[^=\n]+={value}$'
        if not re.search(required, cache, re.M) or not re.search(required, arm_cache, re.M):
            raise ValueError('Build option missing: ' + required)
    sources = {'boot.dol': tree / 'shared/boot.dol',
               'kernel.elf': tree / 'group-arm/kernel/kernel.elf',
               'kernel.bin': tree / 'group-arm/kernel/kernel.bin',
               'kernel.zip': tree / 'shared/data/kernel.zip'}
    boot = sources['boot.dol'].read_bytes()
    if b'3.0.0 Timewarp' not in boot:
        raise ValueError('Launcher Timewarp version absent')
    with zipfile.ZipFile(sources['kernel.zip']) as archive:
        if archive.namelist() != ['kernel.bin'] or archive.read('kernel.bin') != sources['kernel.bin'].read_bytes():
            raise ValueError('Packed kernel differs')
    if sources['kernel.zip'].read_bytes() not in boot:
        raise ValueError('Final launcher does not embed the packed kernel')
    budget = kernel_budget(sources['kernel.elf'])
    for name, source in sources.items():
        shutil.copyfile(source, out / name)
        if sha(source.read_bytes()) != sha((out / name).read_bytes()):
            raise ValueError('Frozen launcher copy differs')
    (out / 'CMakeCache.txt').write_text(cache)
    (out / 'CMakeCache-arm.txt').write_text(arm_cache)
    receipt = {'passed': True, 'scope': 'One enabled launcher-only build; no Wii network runtime test or SD write',
               **build,
               'source_sha256': after, 'source_files': len(after), 'sources_stable': True,
               'artifacts': {n: artifact(out / n) for n in sources},
               'boot': artifact(out / 'boot.dol'), 'kernel_budget': budget,
               'checks': {'kernel_zip_exact': True, 'kernel_embedded': True,
                          'online_enabled': True, 'patching_enabled': True}}
    save(out / 'receipt.json', receipt)
    print(json.dumps({'passed': True, 'receipt': str(out / 'receipt.json'), 'kernel_budget': budget}))


def installer_checks(out, mods):
    folder = out / 'installer'
    folder.mkdir()
    source = folder / 'install.c'
    source.write_text('''#include "susamune/mod_bin.h"
__declspec(dllexport) int install(const struct SusamuneModHeader *p,
    unsigned g, unsigned n, void *d, unsigned cap, unsigned base, void *menu) {
    if (SusamuneModFileVersion(p) == SUSAMUNE_MOD_VERSION_V4)
        return SusamuneModV4InstallMapped(p,n,g,0,SUSAMUNE_MEM2_MODBIN_PPC_BASE,
            d,cap,base,menu,SUSAMUNE_MENU_CODE_SIZE,SUSAMUNE_MENU_CODE_CONSOLE_PPC_BASE);
    return SusamuneModInstall(p,g,n,d,cap,base);
}
''', encoding='ascii')
    dll = folder / 'install.dll'
    command = [str(ROOT / 'toolchain/clang.exe'), '--target=x86_64-pc-windows-msvc',
               '-x', 'c', '-std=c11', '-O2', '-fno-builtin', '-ffreestanding',
               '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'include'),
               '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', str(source), '-o', str(dll)]
    subprocess.run(command, check=True, env=dict(os.environ, TEMP=str(folder), TMP=str(folder)))
    library = C.CDLL(str(dll))
    try:
        library.install.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_void_p, C.c_uint, C.c_uint, C.c_void_p]
        for region, (packed, manifest) in mods.items():
            payload = C.create_string_buffer(packed)
            expected = bytearray([0xa7]) * (0xc0000 + 128)
            for segment in manifest['segments']:
                offset, size = segment['offset'], segment['memory_size']
                raw = bytes.fromhex(segment['code'])
                if offset < 0 or not len(raw) <= size or offset + size > 0xc0000:
                    raise ValueError('Invalid installer segment bounds')
                expected[64 + offset:64 + offset + size] = raw + bytes(size - len(raw))
            memory = C.create_string_buffer(bytes([0xa7]) * len(expected))
            menu = C.create_string_buffer(bytes([0xa7]) * (0x4100 + 128))
            menu_address = (C.addressof(menu) + 63) & ~31
            menu_offset = menu_address - C.addressof(menu)
            expected_menu = bytearray(menu.raw)
            if manifest.get('menu_code'):
                raw_menu = verified_artifact(manifest['menu_code'], ROOT, 'menu code')
                expected_menu[menu_offset:menu_offset + len(raw_menu)] = raw_menu
            for _ in range(2):
                status = library.install(payload, manifest['game_id'], len(packed),
                    C.addressof(memory) + 64, 0xc0000, manifest['base_addr'], menu_address)
                if (status or memory.raw[:-1] != expected or payload.raw[:-1] != packed or
                        menu.raw != expected_menu):
                    raise ValueError('Production installer/reset/canaries differ: ' + region)
    finally:
        C.windll.kernel32.FreeLibrary(C.c_void_p(library._handle))
    return {'passed': True, 'regions': list(mods), 'source': artifact(source), 'dll': artifact(dll),
            'scope': 'Exact packed bytes through the native production installer; not Wii execution'}


def package(args):
    out = args.output.resolve()
    if out.exists():
        raise ValueError('Package output is create-only')
    checkpoint_path = args.checkpoint.resolve(strict=True)
    link = checkpoint_path / 'console'
    checkpoint = load(checkpoint_path / 'receipt.json')
    identity = load(args.identity)
    launcher = load(args.launcher_receipt)
    if not all(item.get('passed') for item in (checkpoint, identity, launcher)):
        raise ValueError('A source build receipt did not pass')
    if set(identity['flags']) != FLAGS:
        raise ValueError('Online console feature flags differ')
    if checkpoint['snapshot_receipt_sha256'] != identity['source_snapshot_receipt_sha256']:
        raise ValueError('Mod source identity differs')
    snapshot = Path(checkpoint['source_snapshot'])
    snapshot_receipt = snapshot / 'receipt.json'
    if sha(snapshot_receipt.read_bytes()) != checkpoint['snapshot_receipt_sha256']:
        raise ValueError('Frozen source snapshot receipt differs')
    snapshot_files = load(snapshot_receipt)['files']
    snapshot_files = {n.replace('\\', '/'): h for n, h in snapshot_files.items()}
    p2p_sources = {}
    for name in ('src/live_race_session.cpp', 'include/susamune/live_p2p.hxx'):
        if snapshot_files.get(name) != sha((ROOT / name).read_bytes()):
            raise ValueError('Checkpoint does not contain the current P2P client: ' + name)
        p2p_sources[name] = snapshot_files[name]
    shared = {}
    for name, expected in launcher['source_sha256'].items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise ValueError('Launcher source changed since freeze: ' + name)
        if name.startswith('include/') and name in snapshot_files:
            if snapshot_files[name] != expected:
                raise ValueError('Launcher/mod shared header differs: ' + name)
            shared[name] = expected
    for required in ('mem2_map.h', 'susamune_cfg.h', 'live_transport.h',
                     'transfer_layout.h', 'transfer_lease.h'):
        if 'include/susamune/' + required not in shared:
            raise ValueError('Missing launcher/mod shared-header proof: ' + required)
    boot_path = Path(launcher['boot']['path'])
    boot = boot_path.read_bytes()
    if sha(boot) != launcher['boot']['sha256'] or b'3.0.0 Timewarp' not in boot:
        raise ValueError('Frozen launcher bytes/version differ')
    mods, descriptions = {}, {}
    for region in REGIONS:
        entries = [b for b in checkpoint['builds'] if b['target'] == 'console' and b['region'] == region]
        if len(entries) != 1:
            raise ValueError('Expected one console build for ' + region)
        entry = entries[0]
        if not any(row['file'] == 'live_race_session.cpp' for row in entry['source_objects']):
            raise ValueError('P2P client object absent: ' + region)
        manifest = load(link / ('manifest-' + region + '.json'))
        if manifest['target'] != 'console' or manifest['transport_environment'] != 'console':
            raise ValueError('Requires console code: ' + region)
        proof_bytes = verified_artifact(manifest['pinned_link_receipt'], link, 'link proof')
        proof = json.loads(proof_bytes)
        if sha(proof_bytes) != entry['receipt_sha256']:
            raise ValueError('Checkpoint link proof differs: ' + region)
        elf = link / ('susamune_' + region + '.o')
        if sha(elf.read_bytes()) != proof['elf_sha256']:
            raise ValueError('ELF differs from link proof: ' + region)
        protected = load(guard.BASELINE)['builds']['console-' + region]
        guard.compare(protected['symbols'], guard.linked_symbols(elf, protected['globals']),
                      'packaged ' + region + ' timer')
        packed = build_mod_bin(manifest, format_version=4, base_dir=link)
        if packed != (link / ('mod-' + region + '.bin')).read_bytes() or len(packed) != entry['mod_bytes']:
            raise ValueError('Container differs from frozen checkpoint: ' + region)
        cold = verified_artifact(manifest['cold_image'], link, 'cold code')
        image = b''.join(bytes.fromhex(s['code']) for s in manifest['segments']) + cold
        if b'3.0.0' not in image or not (b'Timewarp' in image or b'TIMEWARP' in image):
            raise ValueError('Linked Timewarp branding absent: ' + region)
        mods[region] = (packed, manifest)
        descriptions[region] = {'bytes': len(packed), 'sha256': sha(packed),
                                'remaining_bytes': entry['remaining_bytes'],
                                'protection': entry['protection'], 'link_receipt_sha256': sha(proof_bytes)}
    guide = GUIDE_PATH.read_text(encoding='ascii')
    state_share = {name: (ROOT / 'tools/state_share' / name).read_bytes()
                   for name in STATE_SHARE_FILES}
    out.mkdir(parents=True)
    (out / 'boot.dol').write_bytes(boot)
    paths = []
    for region, (packed, _) in mods.items():
        path = out / ('mod_' + region + '.bin')
        path.write_bytes(packed)
        paths.append(path)
    installer = installer_checks(out, mods)
    files = launcher_files(out / 'boot.dol', paths, source='sd', version=VERSION)
    files = {n.replace('apps/moonshine_launcher/', APP + '/', 1): b for n, b in files.items()}
    # The loader defaults to English; do not overwrite an existing preference.
    del files[APP + '/language.txt']
    meta = ET.fromstring(files[APP + '/meta.xml'])
    meta.find('name').text = TITLE
    meta.find('short_description').text = 'Private practice and online test'
    meta.find('long_description').text = ('Two-player direct (peer-to-peer) online prototype for JP, US and PAL 60 Hz. '
                                         'Players swap room codes; see TESTING.txt. '
                                         'TAS seeking, Hoverless PBs, collision display, slowdown toggle '
                                         'and experimental faster RAM states. State sharing tools included. '
                                         'New changes require Wii testing.')
    files[APP + '/meta.xml'] = ET.tostring(meta, encoding='utf-8', xml_declaration=True)
    files[APP + '/TESTING.txt'] = guide.encode('ascii')
    files.update({APP + '/State sharing/' + name: data for name, data in state_share.items()})
    archive = out / 'Moonshine-3.0.0-Timewarp-Online-Prototype-10-JP-US-PAL.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as zip_file:
        for name, data in sorted(files.items()):
            zip_file.writestr(name, data)
    if (GUIDE_PATH.read_text(encoding='ascii') != guide or
            any((ROOT / 'tools/state_share' / name).read_bytes() != data
                for name, data in state_share.items())):
        raise ValueError('Testing guide or state-sharing source changed during packaging')
    receipt = {'passed': True, 'title': TITLE, 'version': VERSION,
               'scope': 'Prototype 10 source build and package; focused host checks and protected-region link checks are not Wii timing, visual or shared-state restore verification',
               'archive': artifact(archive), 'launcher_receipt': artifact(args.launcher_receipt),
               'checkpoint_receipt': artifact(checkpoint_path / 'receipt.json'),
               'identity': artifact(args.identity), 'flags': sorted(FLAGS),
               'testing_guide': artifact(GUIDE_PATH),
               'state_sharing_sources': {name: {'bytes': len(data), 'sha256': sha(data)}
                                         for name, data in state_share.items()},
               'p2p_client_sources': p2p_sources,
               'shared_headers': shared, 'mods': descriptions, 'installer': installer,
               'files': {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in files.items()}}
    verified_zip(archive, receipt)
    (out / 'TESTING.txt').write_text(guide, encoding='ascii')
    save(out / 'receipt.json', receipt)
    print(json.dumps({'passed': True, 'archive': str(archive),
                      'relay_archive': relay['archive']['path'],
                      'files': len(files), 'mods': descriptions}))


def verified_zip(path, receipt):
    data = path.read_bytes()
    if not receipt.get('passed') or sha(data) != receipt['archive']['sha256']:
        raise ValueError('Package receipt/archive differs')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(n.casefold() for n in names)) or set(names) != set(receipt['files']):
            raise ValueError('ZIP has extra, missing or duplicate entries')
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity failed')
        result = {}
        for name in names:
            relative = PurePosixPath(name)
            if (not name.startswith(APP + '/') or '\\' in name or ':' in name or
                    '..' in relative.parts or relative.is_absolute() or name != relative.as_posix()):
                raise ValueError('Unexpected package destination: ' + name)
            content = archive.read(name)
            expected = receipt['files'][name]
            if len(content) != expected['bytes'] or sha(content) != expected['sha256']:
                raise ValueError('ZIP file differs: ' + name)
            result[name] = content
    meta = ET.fromstring(result[APP + '/meta.xml'])
    if meta.findtext('name') != TITLE or meta.findtext('version') != VERSION:
        raise ValueError('Packaged title/version differs')
    required = {'boot.dol', 'meta.xml', 'TESTING.txt', 'mod_jp.bin', 'mod_us.bin', 'mod_pal.bin'}
    required.update('State sharing/' + name for name in STATE_SHARE_FILES)
    if any(APP + '/' + n not in result for n in required):
        raise ValueError('Incomplete all-region package')
    return result


def flush_file(stream):
    stream.flush()
    if os.name != 'nt':
        os.fsync(stream.fileno())
        return
    import msvcrt
    flush = C.WinDLL('kernel32', use_last_error=True).FlushFileBuffers
    flush.argtypes = [C.c_void_p]
    flush.restype = C.c_int
    if not flush(msvcrt.get_osfhandle(stream.fileno())):
        raise C.WinError(C.get_last_error())


def install(args):
    package_path = args.package.resolve(strict=True)
    receipt = load(package_path / 'receipt.json')
    archive = package_path / Path(receipt['archive']['path']).name
    files = verified_zip(archive, receipt)
    sd = args.sd.resolve(strict=True)
    target = (sd / APP).resolve(strict=True)
    if not target.is_relative_to(sd) or target.name != 'moonshine_timewarp_test3':
        raise ValueError('Target escapes the explicitly owned Test 3 app')
    old_meta = ET.fromstring((target / 'meta.xml').read_bytes())
    if old_meta.findtext('name') not in ('Moonshine Timewarp State Test 3 (PAL)',
                                      'Moonshine Timewarp Online Prototype 1',
                                      'Moonshine Timewarp Online Prototype 2',
                                      'Moonshine Timewarp Online Prototype 3',
                                      'Moonshine Timewarp Online Prototype 4',
                                      'Moonshine Timewarp Online Prototype 5',
                                      'Moonshine Timewarp Online Prototype 6',
                                      'Moonshine Timewarp Online Prototype 7',
                                      'Moonshine Timewarp Online Prototype 8',
                                      'Moonshine Timewarp Online Prototype 9',
                                      'Moonshine Timewarp Online Prototype 10',
                                      'Moonshine Timewarp Online Prototype 11',
                                      'Moonshine Timewarp Online Prototype 12',
                                      'Moonshine Timewarp Online Prototype 13', TITLE):
        raise ValueError('Target is not the existing Test 3/online prototype app')
    if not package_path.is_relative_to(ROOT / 'build'):
        raise ValueError('Backups and package must be inside the local workspace build directory')
    ordinary = sd / 'Apps/moonshine_launcher'
    preserve_paths = [ordinary / 'boot.dol', ordinary / 'meta.xml']
    if not all(p.is_file() for p in preserve_paths):
        raise ValueError('Expected ordinary Moonshine app is absent')
    # Inventory only this app; arbitrary existing themes/preferences stay untouched.
    expected_names = {str((sd / n).resolve()).casefold() for n in files}
    preserve_paths.extend(p for p in target.rglob('*') if p.is_file()
                          and str(p.resolve()).casefold() not in expected_names)
    preserved = {str(p): sha(p.read_bytes()) for p in preserve_paths}
    destinations = {}
    for name, content in files.items():
        path = (sd / name).resolve()
        if not path.is_relative_to(target) or path == target or (path.exists() and not path.is_file()):
            raise ValueError('Destination escapes app or is not a file: ' + name)
        destinations[name] = path
    backup = package_path / ('sd-backup-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(exist_ok=False)
    previous = {}
    for name, destination in destinations.items():
        if destination.exists():
            content = destination.read_bytes()
            copy = backup / name
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(content)
            if copy.read_bytes() != content:
                raise ValueError('Local backup readback differs')
            previous[name] = {'present': True, 'bytes': len(content), 'sha256': sha(content)}
        else:
            previous[name] = {'present': False}
    save(backup / 'receipt.json', {'target': str(target), 'old_title': old_meta.findtext('name'),
                                 'files': previous, 'preserved': preserved})
    for name, destination in destinations.items():
        expected = previous[name]
        if expected['present'] != destination.exists() or (destination.exists() and
                sha(destination.read_bytes()) != expected['sha256']):
            raise ValueError('SD file changed after backup; refusing overwrite: ' + name)
    for name, destination in destinations.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('wb') as stream:
            stream.write(files[name])
            flush_file(stream)
        if destination.read_bytes() != files[name]:
            raise ValueError('SD readback differs; backup retained at ' + str(backup))
    if any(sha(Path(p).read_bytes()) != expected for p, expected in preserved.items()):
        raise ValueError('Preserved app file differs; backup retained at ' + str(backup))
    installed_meta = ET.fromstring((target / 'meta.xml').read_bytes())
    if installed_meta.findtext('name') != TITLE or installed_meta.findtext('version') != VERSION:
        raise ValueError('Installed title/version differs')
    result = {'passed': True, 'target': str(target), 'title': TITLE, 'version': VERSION,
              'archive_sha256': receipt['archive']['sha256'], 'files': receipt['files'],
              'backup': str(backup), 'preserved_files': preserved, 'all_readback_exact': True,
              'file_flush': 'FlushFileBuffers' if os.name == 'nt' else 'fsync'}
    save(backup / 'installed.json', result)
    save(package_path / 'sd-install-receipt.json', result)
    print(json.dumps({'installed': str(target), 'files_verified': len(files), 'backup': str(backup), 'title': TITLE}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    build = sub.add_parser('build-launcher')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--build-tree', type=Path, default=ROOT / 'build/timewarp-launcher')
    build.add_argument('--cmake', type=Path, default=Path('C:/Program Files/CMake/bin/cmake.exe'))
    build.set_defaults(run=build_launcher)
    pack = sub.add_parser('package')
    pack.add_argument('--launcher-receipt', type=Path, required=True)
    pack.add_argument('--checkpoint', type=Path, required=True)
    pack.add_argument('--identity', type=Path, required=True)
    pack.add_argument('--output', type=Path, required=True)
    pack.set_defaults(run=package)
    server = sub.add_parser('package-server')
    server.add_argument('--output', type=Path, required=True)
    server.set_defaults(run=package_server)
    deploy = sub.add_parser('install')
    deploy.add_argument('--package', type=Path, required=True)
    deploy.add_argument('--sd', type=Path, required=True)
    deploy.set_defaults(run=install)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
