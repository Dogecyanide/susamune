"""Preserve palette defaults, per-region INI data and legacy Dolphin saves."""
import ctypes as C
import unittest
from test_iling_episode_persistence import EpisodePersistenceTests
from test_mario_color_persistence import MarioColorPersistenceTests
class Palette(C.Structure):
    _fields_=[('magic',C.c_uint),('version',C.c_ushort),('custom',C.c_ushort),('rgb',(C.c_ubyte*3)*16),('reserved',C.c_ubyte*8)]
class PaletteIniTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EpisodePersistenceTests.setUpClass.__func__(cls)
        cls.lib.menuColours.argtypes=[C.POINTER(Palette)]
    def state(self):
        p=Palette();self.lib.menuColours(C.byref(p));return p
    def test_per_region_roundtrip_and_absent_defaults(self):
        for region in (b'jp',b'us',b'pal'):
            self.lib.selectRegion(region);self.assertEqual(self.state().custom,0)
            old=b'; preserved\r\n[creation_other]\r\nmenu_colours_custom = 1\r\n'
            content=old+b'[creation_'+region+b']\r\nmenu_colours_custom = 65535\r\nmenu_paper_rgb = 13,27,222\r\nmenu_text_rgb = 240,250,255\r\n'
            self.lib.parse(content);before=bytes(self.state())
            self.assertEqual(self.state().custom,65535);self.assertEqual(list(self.state().rgb[0]),[13,27,222])
            emitted=self.lib.rewrite(content);self.assertIn(old,emitted)
            self.lib.selectRegion(region);self.lib.parse(emitted);self.assertEqual(bytes(self.state()),before)
    def test_invalid_values_do_not_change_palette(self):
        self.lib.selectRegion(b'jp');before=bytes(self.state())
        self.lib.parse(b'[creation_jp]\r\nmenu_paper_rgb = 256,0,0\r\nmenu_colours_custom = 65536\r\n')
        self.assertEqual(bytes(self.state()),before)
class PaletteCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):MarioColorPersistenceTests.setUpClass.__func__(cls)
    def test_legacy_and_new_card_records(self):
        for version in (14,15):
            for damaged in (0,1):
                with self.subTest(version=version,damaged=damaged):self.assertEqual(self.lib.cardMenuPalette(version,damaged),0)
if __name__=='__main__':unittest.main()
