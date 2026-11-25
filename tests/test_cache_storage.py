from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
import cache_storage

class CacheStorageTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base=Path(temporary.name)
        self.data=self.base/"appdata"
        self.data.mkdir()
        self.destination=self.base/"New Cache"
        for name,payload in (("cache/result.json",b"{}"),("posters/art.png",b"image"),("previews/clip/frame.png",b"frame")):
            file=self.data/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(payload)
        self.history=self.data/"history.sqlite3"
        self.history.write_bytes(b"keep history")
        (self.data/"settings.json").write_bytes(b"keep settings")

    def test_size_counts_only_cached_files(self):
        self.assertEqual(cache_storage.measure(self.data),(12,3))
        self.assertEqual(cache_storage.format_size(2048),"2.0 KB")

    def test_move_verifies_and_reuses_the_new_location(self):
        self.assertEqual(cache_storage.relocate(self.data,self.destination),0)
        self.assertEqual(cache_storage.root(self.data),self.destination)
        self.assertEqual(cache_storage.measure(self.destination),(12,3))
        self.assertEqual(cache_storage.measure(self.data),(0,0))
        self.assertEqual(self.history.read_bytes(),b"keep history")
        cache_storage.relocate(self.data,self.data)
        self.assertEqual(cache_storage.root(self.data),self.data)
        self.assertEqual(cache_storage.measure(self.data),(12,3))

    def test_copy_failure_preserves_originals_and_current_configuration(self):
        with patch.object(cache_storage.shutil,"copy2",side_effect=OSError("Copy failed")):
            with self.assertRaises(OSError):
                cache_storage.relocate(self.data,self.destination)
        self.assertEqual(cache_storage.root(self.data),self.data)
        self.assertEqual(cache_storage.measure(self.data),(12,3))
        self.assertFalse(list(self.destination.glob(".sortrr-cache-move-*")))

    def test_configuration_failure_removes_only_new_cache_files(self):
        self.destination.mkdir()
        other=self.destination/"keep.txt"
        other.write_text("keep")
        with patch.object(cache_storage,"save_location",side_effect=OSError("Cannot save")):
            with self.assertRaises(OSError):
                cache_storage.relocate(self.data,self.destination)
        self.assertEqual(other.read_text(),"keep")
        self.assertEqual(cache_storage.measure(self.data),(12,3))
        self.assertEqual(cache_storage.measure(self.destination),(0,0))

    def test_existing_files_and_overlapping_paths_are_rejected(self):
        self.destination.mkdir()
        (self.destination/"cache").mkdir()
        (self.destination/"cache"/"occupied").write_bytes(b"keep")
        with self.assertRaises(ValueError):
            cache_storage.relocate(self.data,self.destination)
        with self.assertRaises(ValueError):
            cache_storage.relocate(self.data,self.data/"previews"/"nested")
        self.assertEqual(cache_storage.measure(self.data),(12,3))

    def test_clear_removes_preview_cache_and_preserves_settings_and_history(self):
        cache_storage.clear(self.data)
        self.assertEqual(cache_storage.measure(self.data),(0,0))
        self.assertEqual(self.history.read_bytes(),b"keep history")
        self.assertEqual((self.data/"settings.json").read_bytes(),b"keep settings")

if __name__=="__main__":
    unittest.main()
