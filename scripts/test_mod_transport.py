"""Boot encoder compatibility against the production C installer."""
import json
import copy
import hashlib
from pathlib import Path
import random
import struct
import tempfile
import unittest

from gen_mod_bin import build_mod_bin
from mod_transport import ROOT, BLOCK, encode_quick, decode_quick, build_mod_v4, GAMES, BASES, ARENA, stage, _lz4, compress_lz4
from test_timewarp_mod_v4 import Harness, SENTINEL, REGION_BYTES


class BootTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-boot-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.harness = Harness(cls.temp.name)
        cls.addClassCleanup(cls.harness.close)

    def check_install(self, container, game, segments):
        status, memory = self.harness.run(container, game=game)
        self.assertEqual(status, 0)
        expected = bytearray([SENTINEL]) * (REGION_BYTES + 128)
        for s in segments:
            start = 64 + s['offset']
            expected[start:start + len(s['raw'])] = s['raw']
            expected[start + len(s['raw']):start + s['memory_size']] = bytes(s['memory_size'] - len(s['raw']))
        self.assertEqual(memory.raw[:-1], expected)

    def test_encoder_boundaries_and_incompressible_fallback(self):
        rng = random.Random(7731)
        for size in (4, 12, 16, 256, 65536, BLOCK - 4, BLOCK, BLOCK + 4):
            for raw in (bytes(size), (bytes(range(256)) * ((size + 255) // 256))[:size], rng.randbytes(size)):
                with self.subTest(size=size, prefix=raw[:4].hex()):
                    packed = encode_quick(raw)
                    self.assertEqual(decode_quick(packed, size), raw)
                    segments = [dict(offset=0, memory_size=size + 32, raw=raw, quick=packed),
                                dict(offset=0x80000, memory_size=32, raw=b"")]
                    container = build_mod_v4(GAMES['jp'], segments, [])
                    self.check_install(container, GAMES['jp'], segments)

    def test_manifest_default_stays_v3_and_opt_in_is_repeatable(self):
        for game in GAMES.values():
            manifest = dict(game_id=game, base_addr=BASES[game], region_reserve=ARENA,
                            segments=[dict(offset=0, memory_size=8192, code=(b'abcd' * 1024).hex()),
                                      dict(offset=0x80000, memory_size=256, code='')],
                            writes=[[0x8000561c, 0x48000001]])
            old = build_mod_bin(manifest)
            self.assertEqual(struct.unpack_from('>8I', old),
                             (0x534d4f44, 3, game, BASES[game], 32 + 4096, 1, ARENA, 8448))
            self.assertEqual(old, build_mod_bin(manifest, format_version=3))
            result = build_mod_bin(manifest, format_version=4)
            self.assertEqual(result, build_mod_bin(manifest, format_version=4))
            self.assertEqual(struct.unpack_from('>I', result, 4)[0], 4)
            self.assertLess(len(result), len(old))
            segments = [dict(offset=s['offset'], memory_size=s['memory_size'], raw=bytes.fromhex(s['code']))
                        for s in manifest['segments']]
            self.check_install(result, game, segments)

    def test_bounded_match_search_is_deterministic_and_never_larger(self):
        rng = random.Random(9834)
        for raw in (rng.randbytes(8192), b'ABCDlong-pattern-' * 400,
                    (b'ABCDabcdefgh' + b'ABCDwxyz' + b'ABCDabcdefghijklmnop') * 300):
            packed = encode_quick(raw)
            self.assertEqual(packed, encode_quick(raw))
            self.assertEqual(decode_quick(packed, len(raw)), raw)
            self.assertLessEqual(len(packed), 16 + min(len(raw), len(_lz4(raw))))
            segments = [dict(offset=0, memory_size=len(raw), raw=raw, quick=packed),
                        dict(offset=0x80000, memory_size=32, raw=b'')]
            self.check_install(build_mod_v4(GAMES['jp'], segments, []), GAMES['jp'], segments)

    def test_lazy_match_skips_short_prefix_and_uses_existing_c_decoder(self):
        raw = b'abcdXbcdefghijklmnopq--abcdefghijklmnopq-final-literals'
        raw += bytes((-len(raw)) & 3)
        lazy = _lz4(raw, 512, lazy=True)
        self.assertLess(len(lazy), min(len(_lz4(raw, depth)) for depth in (1, 4, 32)))
        packed = struct.pack('>4I', 0x4D534C34, BLOCK, len(raw), len(lazy)) + lazy
        self.assertEqual(decode_quick(packed, len(raw)), raw)
        segments = [dict(offset=0, memory_size=len(raw), raw=raw, quick=packed),
                    dict(offset=0x80000, memory_size=32, raw=b'')]
        self.check_install(build_mod_v4(GAMES['jp'], segments, []), GAMES['jp'], segments)

    def test_high_compression_candidate_uses_existing_installer(self):
        rng = random.Random(19041)
        prefix = rng.randbytes(12000)
        raw = prefix + prefix[1:] + prefix + b"last-five-bytes"
        raw += bytes((-len(raw)) & 3)
        compressed = compress_lz4(raw, mode="high_compression", compression=12,
                                  store_size=False)
        self.assertLess(len(compressed), len(raw))
        packed = struct.pack(">4I", 0x4D534C34, BLOCK, len(raw), len(compressed)) + compressed
        self.assertEqual(decode_quick(packed, len(raw)), raw)
        segments = [dict(offset=0, memory_size=len(raw), raw=raw, quick=packed),
                    dict(offset=0x80000, memory_size=32, raw=b"")]
        self.check_install(build_mod_v4(GAMES["jp"], segments, []), GAMES["jp"], segments)

    def test_actual_baseline_images(self):
        base = ROOT / 'build/baseline-console'
        required = [base / name.format(region=region) for region in GAMES
                    for name in ('susamune_manifest_{region}.json', 'mod_{region}.bin')]
        if not all(path.is_file() for path in required):
            self.skipTest('Original console baseline build fixtures required')
        for region in ('jp', 'us', 'pal'):
            manifest = json.loads((base / f'susamune_manifest_{region}.json').read_text())
            old = (base / f'mod_{region}.bin').read_bytes()
            self.assertEqual(build_mod_bin(manifest), old)
            result = build_mod_bin(manifest, format_version=4)
            self.assertEqual(result, build_mod_bin(manifest, format_version=4))
            self.assertEqual(struct.unpack_from('>I', result, 4)[0], 4)
            self.assertLess(len(result), len(old))
            segments = [dict(offset=s['offset'], memory_size=s['memory_size'], raw=bytes.fromhex(s['code']))
                        for s in manifest['segments']]
            self.check_install(result, GAMES[region], segments)

    def test_cold_manifest_binds_artifact_receipt_and_environment(self):
        folder = Path(self.temp.name)
        cold = b'cold' * 8
        (folder / 'cold.bin').write_bytes(cold)
        for environment, flags in (('console', 0), ('dolphin', 1)):
            info = dict(path='cold.bin', vma=stage(flags) + 0xa0, size=len(cold),
                        sha256=hashlib.sha256(cold).hexdigest())
            proof = dict(passed=True, region='jp', target='emu' if flags else 'console', cold_image=info)
            def seal_proof(value):
                data = json.dumps(value).encode()
                (folder / 'receipt.json').write_bytes(data)
                return dict(path='receipt.json', sha256=hashlib.sha256(data).hexdigest())
            manifest = dict(game_id=GAMES['jp'], base_addr=BASES[GAMES['jp']], region_reserve=ARENA,
                            segments=[dict(offset=0, memory_size=32, code=''),
                                      dict(offset=0x80000, memory_size=32, code='')], writes=[],
                            cold_image=info, transport_environment=environment,
                            pinned_link_receipt=seal_proof(proof))
            data = build_mod_bin(manifest, format_version=4, base_dir=folder)
            self.assertEqual(struct.unpack_from('>I', data, 44)[0], flags)
            self.assertEqual(data[0xa0:0xc0], cold)
            status, _ = self.harness.run(data, game=GAMES['jp'], flags=flags)
            self.assertEqual(status, 0)
            for options in ({}, dict(format_version=4)):
                with self.assertRaises(ValueError):
                    build_mod_bin(manifest, **options)
            for key, value in (('size', 64), ('vma', info['vma'] + 32), ('sha256', '0' * 64)):
                bad = copy.deepcopy(manifest)
                bad['cold_image'][key] = value
                with self.assertRaises(ValueError):
                    build_mod_bin(bad, format_version=4, base_dir=folder)
            for key, value in (('passed', False), ('target', 'wrong'), ('region', 'us')):
                bad = copy.deepcopy(manifest)
                changed = dict(proof, **{key: value})
                bad['pinned_link_receipt'] = seal_proof(changed)
                with self.assertRaises(ValueError):
                    build_mod_bin(bad, format_version=4, base_dir=folder)
            manifest['pinned_link_receipt'] = seal_proof(proof)
            (folder / 'cold.bin').write_bytes(b'bad!' * 8)
            with self.assertRaises(ValueError):
                build_mod_bin(manifest, format_version=4, base_dir=folder)
            (folder / 'cold.bin').write_bytes(cold)


if __name__ == '__main__':
    unittest.main()
