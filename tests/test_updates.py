"""Regression coverage for release selection and verified update staging."""
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import updates


def release(tag="v1.0.0-rc.4", **values):
    data = {
        "tag_name": tag, "draft": False, "prerelease": "-rc." in tag,
        "assets": [{
            "name": updates.ASSET_NAME, "state": "uploaded", "size": 12,
            "digest": "sha256:" + "a" * 64,
            "browser_download_url": f"https://github.com/{updates.REPOSITORY}/releases/download/{tag}/{updates.ASSET_NAME}",
        }],
    }
    data.update(values)
    return data


class UpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.install = self.root / "Installed Sortrr"
        self.install.mkdir()
        (self.install / "Sortrr.exe").write_bytes(b"old app")

    def package(self, extra=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("Sortrr/Sortrr.exe", b"new app")
            archive.writestr("Sortrr/_internal/python314.dll", b"runtime")
            archive.writestr("Sortrr/version.json", json.dumps({"version": "1.0.0-rc.4"}))
            if extra:
                archive.writestr(*extra)
        return stream.getvalue()

    def test_candidates_are_ordered_numerically_and_drafts_are_ignored(self):
        chosen = updates.select_release([
            release("v1.0.0-rc.8"), release("v1.0.0-rc.10"),
            release("v2.0.0", draft=True), release("v1.0.0-rc.2"),
        ], "1.0.0-rc.3")
        self.assertEqual(chosen["version"], "1.0.0-rc.10")
        self.assertIsNone(updates.select_release([release("v1.1.0-rc.1")], "1.0.0"))
        self.assertEqual(updates.select_release([release("v1.0.0")], "1.0.0-rc.3")["version"], "1.0.0")

    def test_remote_package_url_and_digest_are_required(self):
        data = release()
        data["assets"][0]["browser_download_url"] = "https://example.com/untrusted.zip"
        with self.assertRaises(ValueError):
            updates.select_release([data], "1.0.0-rc.3")
        data = release()
        data["assets"][0].pop("digest")
        with self.assertRaisesRegex(ValueError, "checksum"):
            updates.select_release([data], "1.0.0-rc.3")

    def test_verified_download_is_staged_without_changing_the_installed_files(self):
        raw = self.package()
        selected = updates.select_release([release()], "1.0.0-rc.3")
        selected.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        seen = []
        with patch.object(updates, "open_url", return_value=io.BytesIO(raw)):
            manifest = updates.stage_update(selected, self.install, lambda done, total: seen.append((done, total)))
        plan = json.loads(manifest.read_text())
        self.assertEqual((self.install / "Sortrr.exe").read_bytes(), b"old app")
        self.assertEqual((Path(plan["package"]) / "Sortrr.exe").read_bytes(), b"new app")
        self.assertEqual(seen[-1], (len(raw), len(raw)))
        self.assertTrue((manifest.parent / "install-update.ps1").is_file())

    def test_bad_checksum_discards_download_and_keeps_the_installed_app(self):
        raw = self.package()
        selected = updates.select_release([release()], "1.0.0-rc.3")
        selected["size"] = len(raw)
        with patch.object(updates, "open_url", return_value=io.BytesIO(raw)):
            with self.assertRaisesRegex(ValueError, "verification failed"):
                updates.stage_update(selected, self.install)
        self.assertEqual((self.install / "Sortrr.exe").read_bytes(), b"old app")
        self.assertFalse(list(self.root.glob(".sortrr-update-*")))

    def test_extraction_rejects_traversal_absolute_paths_and_duplicate_case(self):
        for name in ("Sortrr/../outside.exe", "/outside.exe", "Sortrr/_internal/CON.txt",
                     "Sortrr/_internal/name:stream", "Sortrr/sortrr.EXE"):
            with self.subTest(name=name):
                archive = self.root / "bad.zip"
                archive.write_bytes(self.package((name, b"bad")))
                with tempfile.TemporaryDirectory(dir=self.root) as stage:
                    with self.assertRaises(ValueError):
                        updates.extract_package(archive, Path(stage), "1.0.0-rc.4")

    def test_extraction_rejects_links_and_wrong_version(self):
        archive = self.root / "bad.zip"
        entry = zipfile.ZipInfo("Sortrr/_internal/link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.write_bytes(self.package((entry, b"elsewhere")))
        with self.assertRaisesRegex(ValueError, "link"):
            updates.extract_package(archive, self.root / "extract", "1.0.0-rc.4")
        archive.write_bytes(self.package())
        with self.assertRaisesRegex(ValueError, "version"):
            updates.extract_package(archive, self.root / "extract2", "1.0.0-rc.5")


if __name__ == "__main__":
    unittest.main()
