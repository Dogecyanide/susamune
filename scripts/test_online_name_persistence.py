"""Run the Online player name through the kernel's real INI parse and rewrite."""
import ctypes as C
import re
import unittest
from pathlib import Path

from test_iling_episode_persistence import EpisodePersistenceTests

ROOT = Path(__file__).resolve().parents[1]


class OnlineName(C.Structure):
    _fields_ = [('magic', C.c_uint), ('name', C.c_char * 28)]


class OnlineNameIniTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EpisodePersistenceTests.setUpClass.__func__(cls)
        cls.lib.onlineNameBlock.restype = C.POINTER(OnlineName)
        cls.lib.rewrite.restype = C.c_char_p

    def block(self):
        return self.lib.onlineNameBlock().contents

    def test_name_roundtrips_per_region_and_keeps_other_sections(self):
        for region in (b'jp', b'us', b'pal'):
            with self.subTest(region=region):
                self.lib.selectRegion(region)
                other = b'; keep\r\n[creation_other]\r\nonline_name = Other\r\n'
                text = other + b'[creation_' + region + b']\r\nonline_name = Erik M. #1\r\n'
                self.lib.parse(text)
                self.assertEqual(self.block().name, b'Erik M. #1')
                written = self.lib.rewrite(text)
                self.assertIn(other, written)
                self.assertIn(b'online_name = Erik M. #1\r\n', written)
                self.lib.selectRegion(region)
                self.lib.parse(written)
                self.assertEqual(self.block().name, b'Erik M. #1')

    def test_old_files_keep_the_default_and_bad_names_are_ignored(self):
        self.lib.selectRegion(b'pal')
        self.lib.parse(b'[creation_pal]\r\nfinish_breakdown_rows = 95\r\n')
        self.assertEqual(self.block().magic, 0x534F4E4D)
        self.assertEqual(self.block().name, b'')
        written = self.lib.rewrite(b'[creation_pal]\r\nfinish_breakdown_rows = 95\r\n')
        self.assertNotIn(b'online_name', written)
        for bad in (b'Seventeen chars!!', b'', b'tab\there', b'caf\xc3\xa9'):
            with self.subTest(bad=bad):
                self.lib.selectRegion(b'pal')
                self.lib.parse(b'[creation_pal]\r\nonline_name = ' + bad + b'\r\n')
                self.assertEqual(self.block().name, b'')
        self.lib.parse(b'[creation_pal]\r\nonline_name = Sixteen chars!!!\r\n')
        self.assertEqual(self.block().name, b'Sixteen chars!!!')

    def test_mod_loads_at_boot_and_saves_on_confirm_on_console_only(self):
        source = (ROOT / 'src/live_race.cpp').read_text()
        init = source[source.index('void init() {'):source.index('const Options &options()')]
        configure = source[source.index('bool configure(const Options &options) {'):source.index('bool host()')]
        self.assertIn('savedName()', init)
        self.assertIn('DCInvalidateRange(saved', init)
        self.assertIn('validOptions(loaded)', init)
        self.assertRegex(configure, r'DCStoreRange\(saved[\s\S]*gSettings\.markDirty\(\)')
        self.assertRegex(source, r'#if !IS_EMULATOR\s*\n// The name lives')
        emulator = (ROOT / 'src/emulator_persistence.cpp').read_text()
        self.assertNotIn('SUSAMUNE_ONLINE_NAME_FLAG', emulator)
        kernel = (ROOT / 'launcher/kernel/SusamuneCfg.c').read_text()
        self.assertRegex(kernel, r'SUSAMUNE_FINISH_BREAKDOWN_FLAG \| SUSAMUNE_ONLINE_NAME_FLAG')
        self.assertEqual(len(re.findall(r'sync_(?:after_write|before_read)\(SUSAMUNE_ONLINE_NAME_PHYS_PTR', kernel)), 2)


if __name__ == '__main__':
    unittest.main()
