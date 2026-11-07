import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core


class ChangeHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        data = patch.object(core, 'DATA', self.root / 'data')
        data.start()
        self.addCleanup(data.stop)

    def movie(self, name):
        file = self.source / f'{name}.mkv'
        file.write_bytes(name.encode())
        media = core.parse(file)
        media.chosen = {'title': name, 'year': '2020'}
        media.status = 'Ready'
        return media

    def test_revert_selected_in_older_run_keeps_other_files_and_remembers_result(self):
        first, second, third = (self.movie(name) for name in ('First', 'Second', 'Third'))
        library = self.root / 'library'
        _, older = core.organize([first, second], library)
        _, newer = core.organize([third], library)
        changes = core.read_file_changes(older)
        self.assertEqual(core.change_journals(), [newer, older])
        self.assertEqual(len(changes), 2)
        self.assertEqual(core.revert_file_changes(older, [changes[0].index]), (1, {}))
        self.assertFalse(core.destination(first, library).exists())
        self.assertTrue(first.source.is_file())
        self.assertTrue(core.destination(second, library).is_file())
        self.assertTrue(core.destination(third, library).is_file())
        self.assertTrue(core.read_file_changes(older)[0].reverted)
        self.assertEqual(core.revert_file_changes(older, [changes[0].index]), (0, {}))
        self.assertEqual(core.undo(older), 1)

    def test_newer_move_must_be_reverted_before_the_older_move(self):
        movie = self.movie('Example')
        library = self.root / 'library'
        original = movie.source
        _, older = core.organize([movie], library, mode='move')
        intermediate = core.destination(movie, library)
        next_movie = core.parse(intermediate)
        next_movie.chosen = {'title': 'Updated', 'year': '2020'}
        next_movie.status = 'Ready'
        _, newer = core.organize([next_movie], library, mode='rename')
        count, skipped = core.revert_file_changes(older)
        self.assertEqual(count, 0)
        self.assertIn('newer change', next(iter(skipped.values())))
        self.assertEqual(core.undo(newer), 1)
        self.assertTrue(intermediate.is_file())
        self.assertEqual(core.undo(older), 1)
        self.assertEqual(original.read_bytes(), b'Example')

    def test_torn_final_record_does_not_hide_later_revert_marker(self):
        movie = self.movie('Example')
        _, journal = core.organize([movie], self.root / 'library', mode='move')
        with journal.open('ab') as log:
            log.write(b'{"event":"rever')
        self.assertEqual(core.undo(journal), 1)
        self.assertTrue(core.read_file_changes(journal)[0].reverted)

    def test_recycle_is_recorded_for_manual_restoration(self):
        movie = self.movie('Example')
        movie.status = core.REJECTED
        outcomes, journal = core.dispose_rejects(
            [(movie, movie.source, None)], self.source, None, Path.unlink,
        )
        self.assertEqual(outcomes, [(movie, None, '')])
        change, = core.read_file_changes(journal)
        self.assertEqual(change.record['mode'], 'recycle')
        self.assertFalse(change.reversible)
        self.assertEqual(core.undo(journal), 0)

    def moved_and_renamed(self):
        movie = self.movie('Original')
        original = movie.source
        library = self.root / 'library'
        _, moved = core.organize([movie], library, mode='move')
        intermediate = core.destination(movie, library)
        renamed_movie = core.parse(intermediate)
        renamed_movie.chosen = {'title': 'New title', 'year': '2020'}
        renamed_movie.status = 'Ready'
        _, renamed = core.organize([renamed_movie], library, mode='rename')
        current = renamed_movie.organized_path
        runs = {path.name: core.read_file_changes(path) for path in core.change_journals()}
        trail, = core.file_trails(runs)
        steps = [(name, change.index) for name, change in trail.steps]
        self.assertEqual([name for name, _ in steps], [moved.name, renamed.name])
        return original, intermediate, current, steps

    def test_restore_original_follows_all_moves_and_renames(self):
        original, intermediate, current, steps = self.moved_and_renamed()
        restored = core.restore_original_file(steps)
        self.assertEqual(restored.original, str(original))
        self.assertEqual(original.read_bytes(), b'Original')
        self.assertFalse(intermediate.exists())
        self.assertFalse(current.exists())
        self.assertTrue(all(core.read_file_changes(core.DATA / name)[0].reverted for name, _ in steps))
        with self.assertRaisesRegex(ValueError, 'history changed'):
            core.restore_original_file(steps)

    def test_original_path_conflict_leaves_latest_file_in_place(self):
        original, intermediate, current, steps = self.moved_and_renamed()
        original.write_bytes(b'new occupant')
        with self.assertRaisesRegex(ValueError, 'occupied'):
            core.restore_original_file(steps)
        self.assertEqual(original.read_bytes(), b'new occupant')
        self.assertEqual(current.read_bytes(), b'Original')
        self.assertFalse(intermediate.exists())

    def test_restore_copy_preserves_only_remaining_copy(self):
        movie = self.movie('Original')
        library = self.root / 'library'
        _, journal = core.organize([movie], library)
        target = core.destination(movie, library)
        movie.source.unlink()
        with self.assertRaisesRegex(ValueError, 'original copy source'):
            core.restore_original_file([(journal.name, 0)])
        self.assertEqual(target.read_bytes(), b'Original')
        movie.source.write_bytes(b'Original')
        core.restore_original_file([(journal.name, 0)])
        self.assertTrue(movie.source.is_file())
        self.assertFalse(target.exists())

    def test_reused_path_starts_a_separate_trail_even_for_identical_bytes(self):
        first = self.movie('Original')
        library = self.root / 'library'
        _, older = core.organize([first], library, mode='move')
        target = core.destination(first, library)
        target.unlink()
        second = self.movie('Different source')
        second.source.write_bytes(b'Original')
        second = core.parse(second.source)
        second.chosen = first.chosen
        second.status = 'Ready'
        _, newer = core.organize([second], library, mode='move')
        runs = {path.name: core.read_file_changes(path) for path in core.change_journals()}
        earlier, later = core.file_trails(runs)
        self.assertFalse(earlier.can_restore)
        self.assertTrue(later.can_restore)
        self.assertEqual(earlier.key, (older.name, 0))
        core.restore_original_file([(newer.name, 0)])
        self.assertFalse(first.source.exists())
        self.assertEqual(second.source.read_bytes(), b'Original')
