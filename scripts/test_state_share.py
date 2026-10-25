"""Exercise the Windows helper with synthetic files using the current PPC layout."""
from pathlib import Path
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]


def put(data, offset, value):
    struct.pack_into('>I', data, offset, value)


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def retag(metadata, profile=True):
    owner = 1016 if len(metadata) == 6960 else 992
    if profile:
        put(metadata, owner + 28, 0)
        put(metadata, owner + 28, fnv(metadata[owner:owner + 5920]))
    put(metadata, len(metadata) - 4, fnv(metadata[:-4]))


def envelope(words, metadata, payload):
    words = list(words)
    words[10] = zlib.crc32(metadata)
    words[11] = zlib.crc32(payload)
    words[12] = 0
    header = struct.pack('>16I', *words) + b'Pinna practice\0'.ljust(32, b'\0')
    words[12] = zlib.crc32(header)
    return struct.pack('>16I', *words) + header[64:] + metadata + payload


def archive(**fields):
    payload = zlib.compress(b'example state bytes' * 20)
    words = [0x4D535341, 1, 96, 6936, len(payload), 380,
             0x474D5350, 0x4D530011, 18, 12345, 0, 0, 0, 0x05020000, 0, 0]
    for key, value in fields.items(): words[int(key[1:])] = value
    jp = words[6] == 0x474D534A
    version = 1 if jp else 2 if words[6] == 0x474D5345 else 3
    metadata = bytearray(6960 if jp else 6936)
    if 'f3' not in fields: words[3] = len(metadata)
    # Offsets verified from the production PPC StoredState layout (JP and PAL).
    for offset, value in ((0, 0x53555341), (4, 18), (8, version), (12, 0x80500000),
                          (16, 380), (24, 1), (40, 0x80500000), (44, 380)):
        put(metadata, offset, value)
    metadata[20:22] = bytes([5, 2])
    owner = 1016 if jp else 992
    for offset, value in ((0, 0x534F574E), (4, 1), (8, version), (12, words[7]),
                          (16, words[9]), (20, 1), (24, 1), (32, 0x80001000),
                          (36, 0x12345678), (5152, 0x80002000), (5156, 32)):
        put(metadata, owner + offset, value)
    for offset, value in ((0, 1), (4, 380), (8, len(payload)), (12, zlib.adler32(b'example state bytes' * 20))):
        put(metadata, len(metadata) - 24 + offset, value)
    retag(metadata)
    return envelope(words, metadata, payload)


def damaged_metadata(original, offset, value, profile=True, tag=True):
    words = struct.unpack('>16I', original[:64])
    metadata = bytearray(original[96:96 + words[3]])
    put(metadata, offset, value)
    if tag: retag(metadata, profile)
    return envelope(words, metadata, original[96 + words[3]:])


class StateShareTests(unittest.TestCase):
    def test_snapshot_version_tracks_production(self):
        source = (ROOT / 'src/savestate.cpp').read_text(encoding='utf-8')
        helper = (ROOT / 'tools/state_share/StateShare.cs').read_text(encoding='utf-8')
        version = int(re.search(r'kSnapshotVersion\s*=\s*(\d+)u', source)[1])
        supported = int(re.search(r'SnapshotVersion\s*=\s*(\d+)', helper)[1])
        self.assertEqual(version, supported)
        self.assertEqual(version, 18, 'Recheck both region layouts before updating fixtures')

    def test_import_directory_tracks_launcher(self):
        paths = (ROOT / 'include/susamune/data_paths.h').read_text()
        helper = (ROOT / 'tools/state_share/StateShare.cs').read_text()
        root = re.search(r'#define MOONSHINE_DATA_ROOT "(/[^"]+)"', paths)[1].strip('/')
        states = re.search(r'#define MOONSHINE_STATES_DIR "(/[^"]+)"', paths)[1].strip('/')
        self.assertIn(f'Path.Combine(root, "{root}", "{states}")', helper)

    def test_copy_only_import_export_and_corrupt_package_refusal(self):
        powershell = shutil.which('powershell.exe')
        if not powershell:
            self.skipTest('Windows PowerShell required')
        with tempfile.TemporaryDirectory(prefix='state-share-', dir=ROOT / 'build') as temporary:
            folder = Path(temporary)
            valid = archive()
            (folder / 'valid.mss').write_bytes(valid)
            cases = {
                'bad-region': archive(f6=0x474D5358),
                'bad-version': archive(f1=2),
                'bad-snapshot': archive(f8=0x54415001),
                'old-snapshot': archive(f8=17),
                'zero-build': archive(f7=0),
                'zero-config': archive(f9=0),
                'oversized-metadata': archive(f3=7169),
                'bad-scene': archive(f13=0xFF020000),
                'reserved-header': archive(f15=1),
                'truncated': valid[:-1],
                'trailing': valid + b'!'
            }
            for name, offset, value in (
                ('metadata-magic', 0, 0), ('metadata-version', 4, 17),
                ('metadata-region', 8, 1), ('metadata-scene', 20, 0x05030000),
                ('metadata-heap', 12, 0x817FFFF0), ('metadata-region-count', 24, 19),
                ('metadata-region-offset', 48, 1), ('metadata-region-address', 40, 0x90000000),
                ('metadata-heap-region', 40, 0x80500020),
                ('metadata-generation', 6912, 0), ('metadata-raw-size', 6916, 381),
                ('metadata-packed-size', 6920, 999), ('metadata-parent', 6928, 1),
                ('owner-magic', 992, 0), ('owner-version', 996, 2), ('owner-region', 1000, 1),
                ('owner-build', 1004, 0x12345678), ('owner-config', 1008, 999),
                ('owner-count', 1012, 641), ('owner-keep-count', 1016, 97),
                ('owner-address', 1024, 0x12345678), ('owner-keep-range', 6144, 0x94000000)):
                cases[name] = damaged_metadata(valid, offset, value)
            cases['metadata-tag'] = damaged_metadata(valid, 6932, 1, tag=False)
            cases['owner-checksum'] = damaged_metadata(valid, 1020, 1, profile=False)
            for label, offset in [('bad-header-crc', 24), ('bad-metadata-crc', 100), ('bad-payload-crc', -1)]:
                damaged = bytearray(valid); damaged[offset] ^= 1
                cases[label] = damaged
            for name, data in cases.items(): (folder / (name + '.mss')).write_bytes(data)
            (folder / 'unknown-build.mss').write_bytes(archive(f7=0xABCDEF12))
            (folder / 'valid-jp.mss').write_bytes(archive(f6=0x474D534A))
            (folder / 'valid-us.mss').write_bytes(archive(f6=0x474D5345))
            with zipfile.ZipFile(folder / 'traversal.zip', 'w') as out:
                out.writestr('../state.mss', valid)
            with zipfile.ZipFile(folder / 'duplicate.zip', 'w') as out:
                out.writestr('state.mss', valid)
                out.writestr('other.mss', valid)
            runner = folder / 'test.ps1'
            runner.write_text(r'''
param([string]$Root,[string]$Fixtures)
$ErrorActionPreference='Stop'
. (Join-Path $Root 'tools/state_share/StateShare.ps1') -LibraryOnly
$checks=0
function Verify($condition,$message) {
    if (-not $condition) { throw $message }
    $script:checks++
}
function Reject([scriptblock]$action,$message) {
    $failed=$false
    try { & $action | Out-Null } catch { $failed=$true }
    Verify $failed $message
}
function Fingerprint($file) { [Convert]::ToBase64String([IO.File]::ReadAllBytes($file)) }
$valid=Join-Path $Fixtures 'valid.mss'
$original=[IO.File]::ReadAllBytes($valid)
$info=[MoonshineStateShare.Files]::Read($valid)
Verify ($info.Region -eq 'PAL' -and $info.Snapshot -eq 18 -and $info.Build -eq '4D530011' -and $info.KnownBuildContract) 'Header metadata was not decoded'
Verify ([MoonshineStateShare.Files]::Read((Join-Path $Fixtures 'valid-jp.mss')).Region -eq 'JP') 'JP metadata layout rejected'
Verify ([MoonshineStateShare.Files]::Read((Join-Path $Fixtures 'valid-us.mss')).Region -eq 'US') 'US metadata layout rejected'
Get-ChildItem -LiteralPath $Fixtures -Filter '*.mss' | Where-Object { $_.Name -notin @('valid.mss','valid-jp.mss','valid-us.mss','unknown-build.mss') } | ForEach-Object {
    $candidate=$_.FullName
    Reject { [MoonshineStateShare.Files]::Read($candidate) } ('Corruption accepted: '+$_.Name)
}
foreach ($name in @('traversal.zip','duplicate.zip')) {
    $candidate=Join-Path $Fixtures $name
    Reject { [MoonshineStateShare.Files]::Read($candidate) } ('Unexpected ZIP entries accepted: '+$name)
}
$zip=Join-Path $Fixtures 'shared.zip'
[MoonshineStateShare.Files]::Export($valid,$zip,'PAL, Pinna 3, matching launcher setup') | Out-Null
$zipHash=Fingerprint $zip
Verify ([MoonshineStateShare.Files]::Read($zip).Name -eq 'Pinna practice') 'ZIP round trip changed metadata'
Reject { [MoonshineStateShare.Files]::Export($valid,$zip,'replace') } 'Export overwrote an existing ZIP'
Verify ((Fingerprint $zip) -eq $zipHash) 'Refused export changed the existing ZIP'
$sd=Join-Path $Fixtures 'card'
$states=Join-Path $sd 'Moonshine data\states'
[IO.Directory]::CreateDirectory($states) | Out-Null
$suffixes=@('mss','tmp','used','name0','name1')
for($i=0;$i -lt $suffixes.Length;$i++) {
    [IO.File]::WriteAllText((Join-Path $states ('state_{0:D8}.{1}' -f ($i+1),$suffixes[$i])),'keep me')
}
$imported=[MoonshineStateShare.Files]::Import($zip,$sd)
Verify ([IO.Path]::GetFileName($imported) -eq 'state_00000006.mss') 'Import reused an occupied or reserved stem'
Verify ((Fingerprint $imported) -eq (Fingerprint $valid)) 'Import changed archive bytes'
$again=[MoonshineStateShare.Files]::Import($valid,$sd)
Verify ([IO.Path]::GetFileName($again) -eq 'state_00000007.mss') 'Repeated import reused its previous ID'
for($i=0;$i -lt $suffixes.Length;$i++) {
    Verify ([IO.File]::ReadAllText((Join-Path $states ('state_{0:D8}.{1}' -f ($i+1),$suffixes[$i]))) -eq 'keep me') 'Existing file was changed'
}
$unknown=Join-Path $Fixtures 'unknown-build.mss'
Verify (-not [MoonshineStateShare.Files]::Read($unknown).KnownBuildContract) 'Unknown contract was declared compatible'
Reject { [MoonshineStateShare.Files]::Import($unknown,$sd) } 'Unknown build contract was imported'
$unchanged=[Convert]::ToBase64String([IO.File]::ReadAllBytes($valid)) -eq [Convert]::ToBase64String($original)
Verify $unchanged 'Sender source was modified'
@{ checks=$checks; result='passed'; installedPythonRequired=$false } | ConvertTo-Json
''', encoding='utf-8')
            result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                     str(runner), '-Root', str(ROOT), '-Fixtures', str(folder)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)
            self.assertGreaterEqual(receipt['checks'], 29)
            self.assertEqual(receipt['result'], 'passed')


if __name__ == '__main__':
    unittest.main()
