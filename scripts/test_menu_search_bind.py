"""The menu search shortcut is a normal, persisted bind that defaults to L+Y."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
L, R, Y, A = 0x40, 0x20, 0x800, 0x100


def tab_buttons(search, rapid, released):
    """Mirror of Menu::update's shoulder routing, kept beside the source check."""
    shoulder = search & (L | R) if search & (search - 1) else 0
    return (rapid & ~shoulder) | (released & shoulder)


class MenuSearchBindTests(unittest.TestCase):
    def setUp(self):
        self.menu = (ROOT / "src/menu.cpp").read_text()
        self.search = (ROOT / "src/menu_search.inc").read_text()

    def test_bind_is_appended_with_an_l_y_default(self):
        rows = re.findall(r"X\((BIND_\w+),", (ROOT / "include/susamune/binds_list.h").read_text())
        self.assertEqual(rows[-1], "BIND_MENU_SEARCH")
        self.assertLessEqual(len(rows), 64)
        # Binds live in a 0x80-byte MEM2 slot: 2 bytes per bind plus 10 of state.
        self.assertLessEqual(len(rows) * 2 + 10, 0x80)
        descs = re.findall(r'^BIND_DESC\((.*)\)$', (ROOT / "src/binds_descs.inc").read_text(), re.M)
        self.assertEqual(len(descs), len(rows))
        self.assertEqual(descs[-1], '"Open menu search", kL | kY')
        self.assertIn('"menu_search"', (ROOT / "include/susamune/binds_list.h").read_text())

    def test_binds_menu_lists_it_beside_the_menu_toggle(self):
        self.assertIn("BIND_MENU_TOGGLE, BIND_MENU_SEARCH, BIND_TOGGLE_INPUT_DISPLAY,", self.menu)
        self.assertIn('{"Menu and displays", 0, 3}', self.menu)
        self.assertIn("id == BIND_MENU_SEARCH ? kSearchBindHelp", self.menu)

    def test_menu_uses_the_bind_and_keeps_y_free_elsewhere(self):
        update = self.menu[self.menu.index("void Menu::update(TMarioGamePad *pad) {"):]
        update = update[:update.index("\n}\n")]
        self.assertIn("if (searchShortcut(pad)) return;", update)
        self.assertNotIn("TMarioGamePad::Y", update)
        self.assertNotIn("switchTab", update)
        shortcut = self.search[self.search.index("bool Menu::searchShortcut("):]
        shortcut = shortcut[:shortcut.index("\n}\n")]
        self.assertIn("searchAvailable() ? gBinds.get(BIND_MENU_SEARCH) : 0", shortcut)
        self.assertLess(shortcut.index("wasPressedRaw(BIND_MENU_SEARCH)"), shortcut.index("switchTab(-1)"))
        self.assertIn('"searchShortcut__4MenuFP13TMarioGamePad"',
                      (ROOT / "scripts/pinned_cold_extensions.py").read_text())
        theme = (ROOT / "src/menu_theme.inc").read_text()
        self.assertNotIn('SUSAMUNE_GLYPH_Y " Search"', theme)
        self.assertIn("Binds::format(gBinds.get(BIND_MENU_SEARCH), combo)", theme)

    def test_shoulder_in_the_combo_switches_tabs_on_release_only(self):
        self.assertIn("(search & (search - 1)) ? search & (TMarioGamePad::L | TMarioGamePad::R) : 0", self.search)
        self.assertIn("(pad->mButtons.mRapidInput & ~shoulder) | (pad->mButtons._8 & shoulder)", self.search)
        self.assertEqual(tab_buttons(L | Y, L, 0), 0)          # holding L for L+Y
        self.assertEqual(tab_buttons(L | Y, 0, L), L)          # a plain L tap still changes tab
        self.assertEqual(tab_buttons(L | Y, R, 0), R)          # R is untouched
        self.assertEqual(tab_buttons(Y, L, 0), L)              # rebinding to Y restores L on press
        self.assertEqual(tab_buttons(L, L, 0), L)              # a lone shoulder bind cannot shadow L
        self.assertEqual(tab_buttons(0, L | R, 0), L | R)      # unavailable or cleared search


if __name__ == "__main__":
    unittest.main()
