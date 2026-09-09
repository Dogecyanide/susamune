"""FOXTROT package branding and guides."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_launcher

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
        self.assertIn("doc/foxtrot-tester-checklist.md", cmake)
        self.assertIn("doc/foxtrot-changelog.md", cmake)
        packer = (ROOT / "scripts/package_launcher.py").read_text()
        for name in ("foxtrot-guide-en.md", "foxtrot-guide-ja.md"):
            self.assertIn(name, packer)
            self.assertTrue((ROOT / "doc" / name).is_file())
        self.assertIn("decode_crash.py", packer)
    def test_launcher_zip_contains_complete_codec_licenses(self):
        with tempfile.TemporaryDirectory(prefix="moonshine-package-") as temporary:
            work = Path(temporary)
            boot = work / "boot.dol"
            boot.write_bytes(b"test loader")
            mod = work / "mod_us.bin"
            mod.write_bytes(b"test mod")
            archive = work / "launcher.zip"
            quick = work / "feedback.md"
            quick.write_text("Short feedback checklist")
            rc1 = work / "rc1.md"
            rc1.write_text("Complete RC1 test log")
            routes = work / "routes.md"
            routes.write_text("Course and checkpoint reference")
            with patch.object(package_launcher, "render_meta", return_value="<app/>"), \
                 patch.object(package_launcher, "RC1_TEST_LOG", rc1), \
                 patch.object(package_launcher, "RC1_ROUTES", routes):
                result = package_launcher.main([
                    "--boot-dol", str(boot), "--out-zip", str(archive),
                    "--test-log", str(quick),
                    "--mod-bins", str(mod)])
            self.assertEqual(result, 0)
            with zipfile.ZipFile(archive) as packaged:
                prefix = package_launcher.APP_NAME + "/"
                self.assertEqual(packaged.read(prefix + "TESTING.md"), quick.read_bytes())
                self.assertEqual(packaged.read(prefix + "RC1_TESTING.md"),
                                 rc1.read_bytes())
                self.assertEqual(packaged.read(prefix + "RC1_ROUTES.md"),
                                 routes.read_bytes())
                self.assertEqual(packaged.read(prefix + "licenses/miniz-LICENSE.txt"),
                                 (ROOT / "vendor/miniz/LICENSE").read_bytes())
                self.assertEqual(packaged.read(prefix + "licenses/lz4-LICENSE.txt"),
                                 (ROOT / "vendor/lz4/LICENSE").read_bytes())
                self.assertEqual(packaged.read(prefix + "boot.dol"), boot.read_bytes())
                self.assertEqual(packaged.read(prefix + "mod_us.bin"), mod.read_bytes())
                for name in ("foxtrot-guide-en.md", "foxtrot-guide-ja.md"):
                    self.assertEqual(packaged.read(prefix + name), (ROOT / "doc" / name).read_bytes())
if __name__ == "__main__": unittest.main()
