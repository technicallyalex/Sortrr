import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import core


class RejectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.source = root / 'source'
        self.destination = root / 'rejects'
        patcher = patch.object(core, 'DATA', root / 'data')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.file = self.source / 'subfolder' / 'Unknown.mkv'
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'rejected media')
        self.media = core.parse(self.file)
        self.media.status = core.REJECTED
        self.target = self.destination / self.file.relative_to(self.source)

    def test_reject_survives_lookup_expiration_and_folder_move_can_be_undone(self):
        history = core.History()
        with patch.object(core.time, 'time', return_value=1):
            self.assertTrue(history.save(self.media))
        restored = core.parse(self.file)
        self.assertTrue(history.restore(restored))
        self.assertEqual(restored.status, core.REJECTED)
        self.assertEqual(core.unresolved_media([restored]), [])

        # A source library and reject folder can be on different drives.
        with patch.object(core, 'move_no_replace', side_effect=OSError(errno.EXDEV, 'Different drive')):
            outcome, journal = core.dispose_rejects(
                [(restored, self.file, self.target)], self.source, self.destination, Mock(),
            )
        self.assertEqual(outcome, [(restored, self.target, '')])
        self.assertFalse(self.file.exists())
        self.assertEqual(self.target.read_bytes(), b'rejected media')
        archived = core.parse(self.target)
        self.assertTrue(history.restore(archived))
        self.assertEqual(archived.status, core.REJECT_MOVED)
        self.assertEqual(core.undo(journal), 1)
        self.assertEqual(self.file.read_bytes(), b'rejected media')

    def test_folder_collision_keeps_both_files(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'existing file')
        outcome, journal = core.dispose_rejects(
            [(self.media, self.file, self.target)], self.source, self.destination, Mock(),
        )
        self.assertIn('already exists', outcome[0][2])
        self.assertIsNone(journal)
        self.assertEqual(self.file.read_bytes(), b'rejected media')
        self.assertEqual(self.target.read_bytes(), b'existing file')

    def test_recycle_failure_or_changed_file_is_left_in_place(self):
        recycler = Mock(side_effect=OSError('Recycle Bin unavailable'))
        outcome, journal = core.dispose_rejects(
            [(self.media, self.file, None)], self.source, None, recycler,
        )
        self.assertEqual(outcome[0][2], 'Recycle Bin unavailable')
        self.assertIsNone(journal)
        self.assertTrue(self.file.is_file())

        recycler.reset_mock()
        self.file.write_bytes(b'replacement media')
        outcome, _ = core.dispose_rejects(
            [(self.media, self.file, None)], self.source, None, recycler,
        )
        self.assertIn('changed', outcome[0][2])
        recycler.assert_not_called()
        self.assertEqual(self.file.read_bytes(), b'replacement media')
