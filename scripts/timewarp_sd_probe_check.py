"""Read-only SD probe verification and bounded retail DOL extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / 'build/timewarp-wii-probe-1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def immutable(path, data):
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f'Existing captured file differs: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def inspect(sd):
    ordinary = sd / 'Apps/moonshine_launcher/meta.xml'
    if not ordinary.is_file() or 'moonshine' not in ordinary.read_text(encoding='utf-8').lower():
        raise ValueError('Expected Moonshine SD layout is absent')
    archive = PROBE / 'Moonshine-Timewarp-Memory-Probe-1.zip'
    installed = []
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if item.is_dir() or not item.filename.startswith('apps/moonshine_memory_probe/'):
                continue
            if '..' in Path(item.filename).parts:
                raise ValueError('Unexpected package path')
            expected = z.read(item)
            actual = (sd / item.filename).read_bytes()
            if actual != expected:
                raise ValueError(f'Installed probe differs: {item.filename}')
            installed.append(dict(path=item.filename, size=len(actual), sha256=sha(actual)))
    if len(installed) < 6:
        raise ValueError('Incomplete probe package')

    regions = {b'GMSJ01': 'jp', b'GMSE01': 'us', b'GMSP01': 'pal'}
    images = []
    for path in sorted((sd / 'Games').rglob('*.iso')):
        with path.open('rb') as stream:
            header = stream.read(0x440)
            region = regions.get(header[:6])
            if not region:
                continue
            if len(header) != 0x440 or struct.unpack_from('>I', header, 0x1c)[0] != 0xc2339f3d:
                raise ValueError(f'Invalid GameCube header: {path}')
            offset = struct.unpack_from('>I', header, 0x420)[0]
            stream.seek(offset)
            dol_header = stream.read(0x100)
            if len(dol_header) != 0x100:
                raise ValueError(f'Truncated DOL: {path}')
            offsets = struct.unpack_from('>18I', dol_header)
            sizes = struct.unpack_from('>18I', dol_header, 0x90)
            size = max([0x100] + [a + b for a, b in zip(offsets, sizes) if b])
            if size > 0x2000000 or offset > path.stat().st_size - size:
                raise ValueError(f'DOL exceeds image: {path}')
            stream.seek(offset)
            dol = stream.read(size)
            if len(dol) != size:
                raise ValueError(f'Truncated DOL payload: {path}')
        destination = ROOT / f'build/timewarp-sd-retail/{region}-{header[7]}/main.dol'
        immutable(destination, dol)
        images.append(dict(path=str(path), game_id=header[:6].decode(), region=region,
                           revision=header[7], disc_number=header[6], image_bytes=path.stat().st_size,
                           header_sha256=sha(header), dol_offset=offset, dol_bytes=size,
                           dol_sha256=sha(dol), extracted_dol=str(destination)))
    receipt = dict(sd_root=str(sd), archive_sha256=sha(archive.read_bytes()),
                   probe_files=installed, game_images=images, sd_writes=False,
                   user_report=dict(date='2026-10-08', region='PAL', source='SD ISO',
                                    boot=True, menus_and_nested_pages=True, ram_save_load=True,
                                    wii_reset=True, second_launch_and_fresh_ram_state=True,
                                    evidence='User report; no Wii telemetry captured'))
    (PROBE / 'sd-return-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(probe_files_verified=len(installed), regions=[i['region'] for i in images],
                          retail_dols=[dict(region=i['region'], revision=i['revision'],
                                            bytes=i['dol_bytes'], sha256=i['dol_sha256']) for i in images],
                          sd_writes=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('sd', type=Path)
    inspect(parser.parse_args().sd)
