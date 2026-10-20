"""Run finish-breakdown INI and CARD persistence through production paths."""
import ctypes as C
import unittest

from test_iling_episode_persistence import EpisodePersistenceTests
from test_mario_color_persistence import MarioColorPersistenceTests


class Breakdown(C.Structure):
    _fields_ = [('magic', C.c_uint), ('version', C.c_ushort),
                ('x', C.c_ushort), ('y', C.c_ushort),
                ('scale', C.c_ubyte), ('textA', C.c_ubyte),
                ('bgR', C.c_ubyte), ('bgG', C.c_ubyte), ('bgB', C.c_ubyte),
                ('bgA', C.c_ubyte), ('textBrightness', C.c_ubyte), ('padding', C.c_ubyte),
                ('rgb', (C.c_ubyte * 3) * 3), ('rows', C.c_ubyte),
                ('halfSeconds', C.c_ubyte), ('reserved', C.c_ubyte * 3)]


class BreakdownIniTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EpisodePersistenceTests.setUpClass.__func__(cls)
        cls.lib.finishBreakdown.argtypes = [C.POINTER(Breakdown)]

    def state(self):
        value = Breakdown()
        self.lib.finishBreakdown(C.byref(value))
        return value

    def test_full_style_and_until_departure_roundtrip_preserve_other_regions(self):
        fields = {b'x': b'620', b'y': b'399', b'scale': b'140', b'text_alpha': b'117',
                  b'background_rgb': b'5,19,222', b'background_alpha': b'120',
                  b'text_brightness': b'180', b'padding': b'255', b'rows': b'65',
                  b'duration_half_seconds': b'0', b'1_rgb': b'1,23,245',
                  b'2_rgb': b'110,200,40', b'3_rgb': b'255,0,80'}
        for region in (b'jp', b'us', b'pal'):
            with self.subTest(region=region):
                self.lib.selectRegion(region)
                other = b'; retain this comment\r\n[creation_other]\r\nfinish_breakdown_x = 35\r\n'
                text = other + b'[creation_' + region + b']\r\n' + b''.join(
                    b'finish_breakdown_' + key + b' = ' + value + b'\r\n'
                    for key, value in fields.items())
                self.lib.parse(text)
                first = self.state()
                self.assertEqual(C.sizeof(first), 32)
                self.assertEqual((first.x, first.y, first.scale, first.textA), (620, 399, 140, 117))
                self.assertEqual((first.bgR, first.bgG, first.bgB, first.bgA), (5, 19, 222, 120))
                self.assertEqual((first.textBrightness, first.padding, first.rows, first.halfSeconds),
                                 (180, 255, 65, 0))
                self.assertEqual([list(row) for row in first.rgb], [[1, 23, 245], [110, 200, 40], [255, 0, 80]])
                written = self.lib.rewrite(text)
                self.assertIn(other, written)
                self.lib.selectRegion(region)
                self.lib.parse(written)
                self.assertEqual(bytes(self.state()), bytes(first))

    def test_absent_and_partial_keys_keep_defaults_and_reject_invalid_fields(self):
        self.lib.selectRegion(b'pal')
        before = self.state()
        self.assertEqual((before.x, before.y, before.rows, before.halfSeconds), (22, 72, 111, 40))
        self.assertTrue(before.rows & 32)
        self.assertFalse(before.rows & 16)
        self.lib.parse(b'[creation_pal]\r\nfinish_breakdown_duration_half_seconds = 1\r\n')
        first = self.state()
        self.assertEqual(first.halfSeconds, 1)
        self.assertEqual(first.x, before.x)
        bad = {b'x': b'641', b'y': b'481', b'scale': b'151', b'text_alpha': b'-1',
               b'background_rgb': b'256,0,0', b'background_alpha': b'bad',
               b'text_brightness': b'24', b'padding': b'17', b'rows': b'128',
               b'duration_half_seconds': b'121', b'1_rgb': b'1,2,3,4'}
        self.lib.parse(b'[creation_pal]\r\n' + b''.join(
            b'finish_breakdown_' + key + b' = ' + value + b'\r\n' for key, value in bad.items()))
        self.assertEqual(bytes(self.state()), bytes(first))

    def test_explicit_previous_default_rows_are_preserved(self):
        self.lib.selectRegion(b'pal')
        text = b'[creation_pal]\r\nfinish_breakdown_rows = 95\r\n'
        self.lib.parse(text)
        self.assertEqual(self.state().rows, 95)
        written = self.lib.rewrite(text)
        self.lib.selectRegion(b'pal')
        self.lib.parse(written)
        self.assertEqual(self.state().rows, 95)


class BreakdownCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        MarioColorPersistenceTests.setUpClass.__func__(cls)

    def test_v12_v13_upgrade_and_v14_transaction_preserve_previous_payloads(self):
        for version in (12, 13, 14):
            with self.subTest(version=version):
                self.assertEqual(self.lib.cardFinishBreakdown(version, 0), 0)

    def test_corrupt_new_record_falls_back_and_legacy_tail_is_ignored(self):
        for version in (12, 13, 14):
            with self.subTest(version=version):
                self.assertEqual(self.lib.cardFinishBreakdown(version, 1), 0)

    def test_existing_card_row_preferences_are_preserved(self):
        for rows in (0, 65, 95, 111, 127):
            with self.subTest(rows=rows):
                self.assertEqual(self.lib.cardFinishBreakdownRows(rows), 0)


if __name__ == '__main__':
    unittest.main()
