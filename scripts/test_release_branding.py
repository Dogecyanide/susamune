"""FOXTROT package branding and guides."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
class ReleaseBrandingTests(unittest.TestCase):
    def test_prerelease_branding_in_all_surfaces(self):
        for path in ("CMakeLists.txt", "launcher/meta.xml.j2", "launcher/loader/source/menu.c", "src/menu.cpp"):
            source = (ROOT / path).read_text()
            with self.subTest(path=path):
                self.assertIn("FOXTROT", source)
                self.assertIn("pre-release", source.lower())
        meta = (ROOT / "launcher/meta.xml.j2").read_text()
        self.assertIn("<name>Moonshine Launcher FOXTROT</name>", meta)
        self.assertNotIn("The House Always Wins", meta)
    def test_tester_material_and_guides_packaged(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        self.assertIn("doc/foxtrot-testing.md", cmake)
        self.assertIn("doc/foxtrot-changelog.md", cmake)
        packer = (ROOT / "scripts/package_launcher.py").read_text()
        for name in ("foxtrot-guide-en.md", "foxtrot-guide-ja.md"):
            self.assertIn(name, packer)
            self.assertTrue((ROOT / "doc" / name).is_file())
        self.assertIn("decode_crash.py", packer)
if __name__ == "__main__": unittest.main()
