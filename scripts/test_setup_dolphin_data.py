"""Validate the standard Dolphin data-folder setup without touching a user profile."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import setup_dolphin_data as setup

class Tests(unittest.TestCase):
    def test_regional_gci_and_independent_random_seeds(self):
        for region, (number, game, directory) in setup.REGIONS.items():
            first, second = setup.seed_gci(region), setup.seed_gci(region)
            self.assertEqual(setup.identity(first), (game + b'SU', b'ms_tls_seed'))
            self.assertEqual(struct.unpack_from('>H', first, 56)[0], 2)
            self.assertEqual(first[64:72], bytes.fromhex('4d53534500000001'))
            self.assertEqual(struct.unpack_from('>I', first, 76)[0], number)
            self.assertNotEqual(first[80:112], second[80:112])
            setup.validate_seed(first, region)
            bad = bytearray(first); bad[80] ^= 1
            with self.assertRaises(ValueError): setup.validate_seed(bytes(bad), region)
            with self.assertRaises(ValueError): setup.identity(first[:-1])

    def test_repeat_setup_retains_every_private_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            setup.prepare(root / 'Moonshine data')
            before = {p: p.read_bytes() for p in root.rglob('*.gci')}
            setup.prepare(root / 'Moonshine data')
            self.assertEqual(len(before), 3)
            for p, raw in before.items(): self.assertEqual(p.read_bytes(), raw)

    def test_conflicting_seed_aborts_without_overwriting_either_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / 'old', Path(temp) / 'new'
            setup.prepare(source); setup.prepare(target)
            before = {p: p.read_bytes() for p in Path(temp).rglob('*.gci')}
            with self.assertRaises(ValueError): setup.prepare(target, source)
            for p, raw in before.items(): self.assertEqual(p.read_bytes(), raw)

    def test_migration_keeps_seed_and_ignores_normal_sunshine_save(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / 'old', Path(temp) / 'new'
            setup.prepare(source)
            retail = bytearray(setup.seed_gci('jp')); retail[4:6] = b'01'
            (source / 'JPN' / 'retail.gci').write_bytes(retail)
            setup.prepare(target, source)
            self.assertEqual(len(list(target.rglob('*.gci'))), 3)
            for p in target.rglob('*.gci'): self.assertEqual(p.read_bytes(), (source / p.relative_to(target)).read_bytes())

    def test_custom_japanese_folder_matches_dolphin_modern_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            setup.prepare(root)
            self.assertTrue((root / 'JPN' / 'GMSJ-Moonshine-security.gci').is_file())
            self.assertFalse((root / 'JAP').exists())

    def test_legacy_default_japanese_card_migrates_without_changing_seed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'GC' / 'JAP' / 'Card B'
            source.mkdir(parents=True)
            raw = setup.seed_gci('jp')
            (source / 'old.gci').write_bytes(raw)
            setup.prepare(root / 'data', root / 'GC')
            self.assertEqual((root / 'data' / 'JPN' / 'old.gci').read_bytes(), raw)
            self.assertEqual((source / 'old.gci').read_bytes(), raw)

    def test_configuration_preserves_slot_a_controller_and_comments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); config = root / 'Config' / 'Dolphin.ini'
            config.parent.mkdir()
            old = '# Personal profile\n[Core]\nSlotA = 8\nSlotB = 0\nSIDevice0 = 12\n[Interface]\nLanguageCode = ja\n'
            config.write_text(old)
            setup.configure(root, root / 'Moonshine data')
            new = config.read_text()
            for line in ('SlotA = 8', 'SIDevice0 = 12', 'LanguageCode = ja', '# Personal profile'):
                self.assertIn(line, new)
            self.assertEqual(new.count('SlotB = 8'), 1)
            self.assertIn('/Moonshine data/USA', new)
            backup = next(config.parent.glob('Dolphin.before-moonshine-*.ini'))
            self.assertEqual(backup.read_text(), old)
            setup.configure(root, root / 'Moonshine data')
            self.assertEqual(config.read_text(), new)
            self.assertEqual(len(list(config.parent.glob('Dolphin.before-moonshine-*.ini'))), 1)

    def test_game_options_preserve_unrelated_settings_and_back_up(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'GameSettings'/'GMSJ01.ini';path.parent.mkdir()
            original='# User choice\n[Core]\nCPUThread = False\n[Video_Settings]\nInternalResolution = 2\n';path.write_text(original)
            setup.configure_games(root)
            changed=path.read_text()
            for text in ('CPUThread = False','InternalResolution = 2','SerialPort1 = 12','MEM1Size = 33554432'):
                self.assertIn(text,changed)
            self.assertEqual(next(path.parent.glob('GMSJ01.before-moonshine-*.ini')).read_text(),original)
            setup.configure_games(root);self.assertEqual(path.read_text(),changed)
            self.assertEqual(len(list(path.parent.glob('GMSJ01.before-moonshine-*.ini'))),1)

if __name__ == '__main__': unittest.main()
