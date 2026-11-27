import os
import tempfile
import unittest
from pathlib import Path
from watch_folders import StableIndex, inventory, atomic_json
import json


class WatchIndexTests(unittest.TestCase):
    def test_files_must_be_unchanged_and_old_enough(self):
        index = StableIndex(quiet_seconds=60)
        snapshot = {"movie.mp4": [100, 1000_000_000_000]}
        self.assertEqual(index.ready(snapshot, 0, 1000), [])
        self.assertEqual(index.ready(snapshot, 59, 1100), [])
        self.assertEqual(index.ready(snapshot, 60, 1050), [])
        self.assertEqual(index.ready(snapshot, 61, 1061), ["movie.mp4"])

    def test_growing_file_restarts_the_quiet_period(self):
        index = StableIndex(quiet_seconds=10)
        index.ready({"a": [10, 1]}, 0, 100)
        self.assertEqual(index.ready({"a": [20, 1]}, 11, 100), [])
        self.assertEqual(index.ready({"a": [20, 1]}, 20, 100), [])
        self.assertEqual(index.ready({"a": [20, 1]}, 21, 100), ["a"])

    def test_processed_fingerprints_survive_restart_and_changes_requeue(self):
        index = StableIndex(quiet_seconds=1)
        index.acknowledge("a", [20, 1])
        restored = StableIndex(index.seen, quiet_seconds=1)
        self.assertEqual(restored.ready({"a": [20, 1]}, 10, 100), [])
        self.assertEqual(restored.ready({"a": [21, 2]}, 11, 100), [])
        self.assertEqual(restored.ready({"a": [21, 2]}, 12, 100), ["a"])

    def test_multiple_roots_keep_independent_stability_timers(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/"a", Path(folder)/"b"
            pa, pb = str(a/"one.mp4"), str(b/"two.mp4")
            index = StableIndex(quiet_seconds=10)
            index.ready({pa: [20, 1]}, 0, 100, scope=a)
            index.ready({pb: [20, 1]}, 0, 100, scope=b)
            self.assertEqual(index.ready({pa: [20, 1]}, 10, 100, scope=a), [pa])
            self.assertEqual(index.ready({pb: [20, 1]}, 10, 100, scope=b), [pb])
            index.ready({}, 11, 100, scope=a)
            self.assertIn(pb, index.observed)
            self.assertNotIn(pa, index.observed)

    def test_disappearing_and_returning_file_must_settle_again(self):
        index = StableIndex(quiet_seconds=10)
        index.ready({"a": [20, 1]}, 0, 100)
        index.ready({}, 20, 100)
        self.assertEqual(index.ready({"a": [20, 1]}, 30, 100), [])


class WatchInventoryTests(unittest.TestCase):
    def test_recursive_inventory_ignores_outputs_temporary_and_empty_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"sub").mkdir()
            (root/"library").mkdir()
            for name in ("movie.mp4", "sub/show.S01E01.mkv", "library/copied.mp4", "movie.part.mp4", "notes.txt"):
                (root/name).write_bytes(b"x")
            (root/"empty.mp4").touch()
            found = inventory(root, [root/"library"])
            self.assertEqual({Path(p).relative_to(root).as_posix() for p in found},
                             {"movie.mp4", "sub/show.S01E01.mkv"})

    def test_unavailable_folder_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OSError):
                inventory(Path(folder)/"missing")

    def test_atomic_state_is_replaced_and_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"state.json"
            atomic_json(path, {"a": [1, 2]})
            atomic_json(path, {"b": [2, 3]})
            self.assertEqual(json.loads(path.read_text()), {"b": [2, 3]})
            self.assertFalse(path.with_suffix(".tmp").exists())
