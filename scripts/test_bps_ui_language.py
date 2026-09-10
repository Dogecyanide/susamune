"""Apply both source-free language variants and compare their complete output."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

from gen_iso_bps import build_operations, build_patch, expected_source_ranges
from gen_japanese_ui import build, MAX_SIZE

ROOT = Path(__file__).resolve().parents[1]
ASSET_OFFSET = 0x004AA8C0


def apply_bps(source, encoded):
    assert encoded[:4] == b'BPS1'
    source_crc, target_crc, patch_crc = struct.unpack('<III', encoded[-12:])
    assert zlib.crc32(source) == source_crc
    assert zlib.crc32(encoded[:-4]) == patch_crc
    cursor = 4

    def number():
        nonlocal cursor
        value, shift = 0, 1
        while True:
            byte = encoded[cursor]
            cursor += 1
            value += (byte & 127) * shift
            if byte & 128:
                return value
            shift <<= 7
            value += shift

    assert number() == len(source)
    target_size = number()
    metadata_size = number()
    cursor += metadata_size
    out = bytearray()
    source_relative = target_relative = 0
    while len(out) < target_size:
        command = number()
        kind, size = command & 3, (command >> 2) + 1
        assert len(out) + size <= target_size
        if kind == 0:
            out.extend(source[len(out):len(out) + size])
        elif kind == 1:
            out.extend(encoded[cursor:cursor + size])
            cursor += size
        else:
            delta = number()
            delta = -(delta >> 1) if delta & 1 else delta >> 1
            if kind == 2:
                source_relative += delta
                assert 0 <= source_relative <= len(source) - size
                out.extend(source[source_relative:source_relative + size])
                source_relative += size
            else:
                target_relative += delta
                assert 0 <= target_relative < len(out)
                pattern = out[target_relative:]
                out.extend((pattern * ((size + len(pattern) - 1) // len(pattern)))[:size])
                target_relative += size
    assert cursor == len(encoded) - 12
    assert zlib.crc32(out) == target_crc
    return bytes(out)


class BpsUiLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset = build()[0]
        cls.end = ASSET_OFFSET + MAX_SIZE
        size = cls.end + 4096
        source = bytearray((bytes(range(256)) * ((size + 255) // 256))[:size])
        # A pre-existing valid catalogue must not enable the standard patch.
        source[ASSET_OFFSET:ASSET_OFFSET + len(cls.asset)] = cls.asset
        cls.source = bytes(source)
        cls.layout = {
            'format_version': 2, 'region': 'jp', 'game_id': 0x474D534A,
            'base_addr': 0x80426020, 'iso_size': size,
            'source_crc32': f'{zlib.crc32(source):08X}', 'mod_region_size': 0xA0000,
            'first_file_offset': cls.end + 256,
            'dol': {'iso_offset': 0x1E000, 'size': 0x3EC8C0, 'new_text_slot': 2},
            'fst': {'source_offset': 0x40A8C0, 'target_offset': cls.end + 64, 'size': 32},
            'relocated_files': [{'source_offset': ASSET_OFFSET - 32,
                                 'target_offset': cls.end + 256, 'size': 32,
                                 'fst_word_offset': 4}],
            'hooks': [{'address': 0x8000561C, 'iso_offset': 0x21000}],
            'japanese_ui': {'offset': ASSET_OFFSET, 'size': MAX_SIZE},
        }
        cls.manifest = {
            'base_addr': cls.layout['base_addr'], 'game_id': cls.layout['game_id'],
            'writes': [[0x8000561C, 0x48000001]],
            'segments': [{'offset': 0, 'memory_size': 64, 'code': 'A5' * 32},
                         {'offset': 0x80000, 'memory_size': 64, 'code': '5A' * 32}],
        }
        cls.layout['source_ranges'] = [
            {'offset': offset, 'size': count,
             'crc32': f'{zlib.crc32(source[offset:offset + count]):08X}'}
            for offset, count in dict.fromkeys(expected_source_ranges(cls.layout, cls.manifest))]
        cls.english_patch, _ = build_patch(cls.layout, cls.manifest)
        cls.japanese_patch, _ = build_patch(cls.layout, cls.manifest, 'ja')
        cls.english = apply_bps(cls.source, cls.english_patch)
        cls.japanese = apply_bps(cls.source, cls.japanese_patch)

    def test_full_outputs_differ_only_inside_translation_extent(self):
        self.assertEqual(self.english[:ASSET_OFFSET], self.japanese[:ASSET_OFFSET])
        self.assertEqual(self.english[self.end:], self.japanese[self.end:])
        self.assertEqual(len(self.english), len(self.source))
        self.assertEqual(self.english[ASSET_OFFSET:self.end], bytes(MAX_SIZE))
        self.assertEqual(self.japanese[ASSET_OFFSET:self.end],
                         self.asset + bytes(MAX_SIZE - len(self.asset)))
        self.assertNotEqual(self.english_patch[-8:-4], self.japanese_patch[-8:-4])
        self.assertEqual(self.english_patch[-12:-8], self.japanese_patch[-12:-8])

    def test_language_does_not_change_sections_hooks_or_relocated_file(self):
        for output in (self.english, self.japanese):
            self.assertEqual(output[0x21000:0x21004], bytes.fromhex('48000001'))
            self.assertEqual(output[self.end + 256:self.end + 288],
                             self.source[ASSET_OFFSET - 32:ASSET_OFFSET])
            self.assertEqual(struct.unpack_from('>I', output, self.end + 68)[0], self.end + 256)
            for slot, delta, fill in ((2, 0, 0xA5), (3, 0x80000, 0x5A)):
                dol = 0x1E000
                offset = struct.unpack_from('>I', output, dol + slot * 4)[0]
                address = struct.unpack_from('>I', output, dol + 0x48 + slot * 4)[0]
                size = struct.unpack_from('>I', output, dol + 0x90 + slot * 4)[0]
                self.assertEqual((address, size), (self.layout['base_addr'] + delta, 64))
                self.assertEqual(output[dol + offset:dol + offset + size],
                                 bytes([fill]) * 32 + bytes(32))

    def test_both_languages_use_identical_verified_source_ranges(self):
        self.assertEqual(list(expected_source_ranges(self.layout, self.manifest)),
                         list(expected_source_ranges(self.layout, self.manifest, 'ja')))
        layout = json.loads((ROOT/'data/iso_layout_jp.json').read_text())
        manifest = dict(self.manifest, base_addr=layout['base_addr'], writes=[])
        self.assertEqual(list(expected_source_ranges(layout, manifest)),
                         list(expected_source_ranges(layout, manifest, 'ja')))

    def test_english_does_not_generate_or_load_the_catalogue(self):
        with patch('gen_japanese_ui.build', side_effect=AssertionError('unused catalogue')):
            self.assertEqual(build_patch(self.layout, self.manifest, 'en')[0], self.english_patch)

    def test_invalid_language_or_unsupported_translation_is_rejected(self):
        with self.assertRaises(ValueError):
            build_operations(self.layout, self.manifest, 'fr')
        for region in ('us', 'pal'):
            layout = json.loads((ROOT/f'data/iso_layout_{region}.json').read_text())
            with self.subTest(region=region), self.assertRaises(ValueError):
                build_operations(layout, self.manifest, 'ja')
        missing = copy.deepcopy(self.layout)
        del missing['japanese_ui']
        with self.assertRaises(ValueError):
            build_operations(missing, self.manifest, 'ja')

    def test_cli_defaults_to_english_and_keeps_japanese_output_separate(self):
        with tempfile.TemporaryDirectory(prefix='moonshine-bps-language-') as temporary:
            work = Path(temporary)
            (work/'layout.json').write_text(json.dumps(self.layout))
            (work/'manifest.json').write_text(json.dumps(self.manifest))
            common = [sys.executable, str(ROOT/'scripts/gen_iso_bps.py'), 'build',
                      '--layout', str(work/'layout.json'),
                      '--mod-manifest', str(work/'manifest.json')]
            for name, language, expected in (('moonshine_jp.bps', [], self.english_patch),
                    ('moonshine_jp_ja.bps', ['--ui-language', 'ja'], self.japanese_patch)):
                subprocess.run(common + ['--output', str(work/name)] + language,
                               check=True, capture_output=True)
                self.assertEqual((work/name).read_bytes(), expected)
            self.assertEqual((work/'moonshine_jp.bps').read_bytes(), self.english_patch)


if __name__ == '__main__':
    unittest.main()
