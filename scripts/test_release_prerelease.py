"""Release identity and admission checks must survive packager consolidation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import release_prerelease as release


class ReleaseTests(unittest.TestCase):
    def test_prototypes_cannot_share_build_or_package_identity(self):
        a, b = release.Release(27), release.Release(28)
        self.assertNotEqual(a.app, b.app)
        self.assertNotEqual(a.tree("console"), b.tree("console"))
        self.assertNotEqual(a.tree("console"), a.tree("emu"))
        self.assertEqual(a.version, "3.0.0 Timewarp PR27")
        for number in (-1, 0, 26, 10000):
            with self.assertRaises(ValueError):
                release.Release(number)
        with self.assertRaises(ValueError):
            a.tree("../console")

    def test_existing_package_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            sentinel = output / "original.zip"
            sentinel.write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                release.package(release.Release(27), output)
            self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_stale_sources_fail_before_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = release.Release(27)
            tree = root / "build/pr27-console"
            tree.mkdir(parents=True)
            release.save(tree / "pr27-build-receipt.json", dict(passed=True, sources={"x": "old"}))
            output = root / "package"
            with patch.object(release, "ROOT", root), patch.object(release, "sources", return_value={"x": "new"}):
                with self.assertRaisesRegex(ValueError, "stale"):
                    release.package(spec, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
