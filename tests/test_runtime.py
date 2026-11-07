import unittest
from unittest.mock import patch

import core


class RuntimeTests(unittest.TestCase):
    def test_movie_minutes_are_converted_to_seconds(self):
        catalog = core.Catalog()
        with patch.object(catalog, 'get', return_value={'runtime': 115}) as get:
            self.assertEqual(catalog.expected_runtime({'id': 13, 'provider': 'TMDB'}), 6900)
            get.assert_called_once_with('https://api.themoviedb.org/3/movie/13')

    def test_tmdb_uses_exact_episode_including_specials(self):
        catalog = core.Catalog()
        with patch.object(catalog, 'get', return_value={'runtime': 22}) as get:
            self.assertEqual(catalog.expected_runtime({'id': 13, 'provider': 'TMDB'}, 'TV', 0, 2), 1320)
            get.assert_called_once_with('https://api.themoviedb.org/3/tv/13/season/0/episode/2')

    def test_tvmaze_uses_episode_and_handles_missing_runtime(self):
        catalog = core.Catalog()
        entries = [{'season': 2, 'number': 3, 'runtime': 25}, {'season': 1, 'number': 3, 'runtime': None}]
        with patch.object(catalog, 'get', return_value=entries):
            candidate = {'id': 19, 'provider': 'TVmaze'}
            self.assertEqual(catalog.expected_runtime(candidate, 'TV', 2, 3), 1500)
            self.assertIsNone(catalog.expected_runtime(candidate, 'TV', 1, 3))
            self.assertIsNone(catalog.expected_runtime(candidate, 'TV', 1, 4))

    def test_tolerance_scales_for_movies_and_has_episode_floor(self):
        self.assertEqual(core.compare_runtime(6300, 6000)['status'], 'Matches')
        self.assertEqual(core.compare_runtime(6301, 6000)['status'], 'Differs')
        self.assertEqual(core.compare_runtime(1080, 1200)['status'], 'Matches')
        self.assertEqual(core.compare_runtime(1079, 1200)['status'], 'Differs')

    def test_missing_or_invalid_lengths_are_unknown(self):
        for value in (None, 0, -1, float('nan'), float('inf'), '1200'):
            with self.subTest(value=value):
                self.assertEqual(core.compare_runtime(value, 1200)['status'], 'Unknown')
                self.assertEqual(core.compare_runtime(1200, value)['status'], 'Unknown')
