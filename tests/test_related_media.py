import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import related_media


class RelatedMediaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "Incoming"
        self.source.mkdir()
        self.library = self.root / "Library"
        patcher = patch.object(core, "DATA", self.root / "data")
        patcher.start()
        self.addCleanup(patcher.stop)

    def file(self, name, data=b"video"):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def scan(self):
        return related_media.inventory(self.source, [], core.VIDEO, core.is_link, core.parse)

    def matched(self, media):
        for item in media:
            item.chosen = dict(title=item.query, year=item.year)
            item.status = "Ready"
        return media

    def test_bonus_folder_and_subtitles_follow_movie_without_database_match(self):
        self.file("Movie (2020)/Movie.2020.mkv")
        extra = self.file("Movie (2020)/Special Features/Interviews/Director.mp4")
        subtitle = self.file("Movie (2020)/Special Features/Interviews/Director.en.srt", b"captions")
        media, extras = self.scan()
        self.assertEqual(len(media), 1)
        self.assertEqual(extras[0]["owner"], str(media[0].source))
        self.assertEqual(extras[0]["category"], "Interviews")
        movie = self.matched(media)[0]
        count, journal = core.organize(media, self.library)
        self.assertEqual(count, 1)
        folder = core.destination(movie,self.library).parent
        self.assertEqual((folder/"Interviews"/extra.name).read_bytes(), b"video")
        self.assertEqual((folder/"Interviews"/subtitle.name).read_bytes(), b"captions")
        self.assertTrue(core.History().processed(movie,self.library,'copy'))
        self.assertEqual(core.undo(journal), 3)
        self.assertTrue(extra.exists())

    def test_show_bonus_goes_beneath_show_and_numbered_special_stays_episode(self):
        self.file("Show/Season 01/Show.S01E01.mkv")
        self.file("Show/Season 01/Show.S01E02.mkv")
        special = self.file("Show/Season 00/Show.S00E01.mkv")
        bonus = self.file("Show/Extras/On set.mkv")
        media, extras = self.scan()
        self.assertEqual(len(media), 3)
        self.assertIn(special, [m.source for m in media])
        owner = next(m for m in media if m.extras)
        self.matched(media)
        planned = related_media.targets(owner,core.destination(owner,self.library),core.SortOptions())
        self.assertEqual(planned[0][1],self.library/"TV Shows"/"Show"/"Featurettes"/bonus.name)

    def test_shared_folder_with_two_movies_requires_manual_association(self):
        self.file("Collection/First.2020.mkv")
        self.file("Collection/Second.2021.mkv")
        self.file("Collection/Bonus Disc/Bonus.mp4")
        media, extras = self.scan()
        self.assertFalse(extras[0]["owner"])
        self.assertTrue(all(not m.extras for m in media))
        extras[0]["owner"] = str(media[1].source)
        related_media.attach(media,extras)
        self.assertEqual(media[1].extras,extras)

    def test_suffix_selects_exact_parent_among_multiple_movies(self):
        first = self.file("First.2020.mkv")
        self.file("Second.2021.mkv")
        self.file("First.2020-trailer.mp4")
        media, extras = self.scan()
        self.assertEqual(extras[0]["owner"],str(first))
        self.assertEqual(extras[0]["category"],"Trailers")

    def test_changed_bonus_prevents_partial_movie_move(self):
        main = self.file("Film/Film.2020.mkv")
        bonus = self.file("Film/Featurettes/Making of.mp4")
        media, _ = self.scan()
        self.matched(media)
        bonus.write_bytes(b"changed")
        count, _ = core.organize(media,self.library,mode="move")
        self.assertEqual(count,0)
        self.assertTrue(main.exists())
        self.assertIn("Related media changed",media[0].status)

    def test_bonus_material_is_not_offered_for_source_cleanup(self):
        self.file("Film/Film.2020.mkv")
        self.file("Film/Bonus Features/notes.txt",b"notes")
        self.file("Film/Bonus Features/Thumbs.db",b"junk")
        junk = self.file("Film/Thumbs.db",b"junk")
        plan = core.plan_cleanup(self.source)
        self.assertEqual([item.path for item in plan.files],[junk])

    def test_moved_extras_update_paths_and_are_reversible(self):
        main = self.file("Film/Film.2020.mkv")
        bonus = self.file("Film/Deleted Scenes/Scene one.mp4")
        media, extras = self.scan()
        self.matched(media)
        count, journal = core.organize(media,self.library,mode="move")
        self.assertEqual(count,1)
        self.assertFalse(main.exists())
        self.assertFalse(bonus.exists())
        self.assertTrue(Path(extras[0]["path"]).is_file())
        self.assertEqual(extras[0]["owner"],str(media[0].source))
        self.assertEqual(core.undo(journal),2)
        self.assertTrue(bonus.exists())

    def test_duplicate_bonus_names_are_skipped_before_any_file_moves(self):
        main = self.file("Film/Film.2020.mkv")
        self.file("Film/Extras/Disc 1/Bonus.mp4")
        self.file("Film/Extras/Disc 2/Bonus.mp4")
        media, _ = self.scan()
        self.matched(media)
        count, _ = core.organize(media,self.library,mode="move")
        self.assertEqual(count,0)
        self.assertIn("conflicting destination",media[0].status)
        self.assertTrue(main.exists())

    def test_alternate_editions_and_unmarked_videos_remain_normal_media(self):
        self.file("Film/Film.2020.Extended.Edition.mkv")
        self.file("Film/Film.2020.Theatrical.mkv")
        self.file("Film/Unidentified Documentary.mp4")
        self.file("Film/Extras/Bonus.mp4")
        media, extras = self.scan()
        self.assertEqual(len(media),3)
        self.assertFalse(extras[0]["owner"])

    def test_new_bonus_can_be_added_to_previously_copied_movie(self):
        self.file("Film/Film.2020.mkv")
        self.file("Film/Featurettes/First.mp4")
        media, _ = self.scan()
        self.matched(media)
        self.assertEqual(core.organize(media,self.library)[0],1)
        self.file("Film/Featurettes/Second.mp4")
        media, _ = self.scan()
        self.matched(media)
        count, journal = core.organize(media,self.library)
        self.assertEqual(count,1)
        self.assertEqual(core.undo(journal),1)
        folder=core.destination(media[0],self.library).parent
        self.assertTrue((folder/"Featurettes"/"First.mp4").exists())
        self.assertTrue(core.destination(media[0],self.library).exists())

    def test_tv_specials_folder_keeps_numbered_specials_and_preserves_other_bonuses(self):
        self.file("Show/Show.S01E01.mkv")
        special=self.file("Show/Specials/Show.S00E01.mkv")
        self.file("Show/Specials/Interview.mp4")
        media, extras = self.scan()
        self.assertIn(special,[m.source for m in media])
        self.assertEqual(len(extras),1)
        self.assertTrue(extras[0]["owner"])

    def test_all_presets_keep_bonuses_in_supported_subfolders(self):
        self.file("Film/Film.2020.mkv")
        self.file("Film/Bonus Features/Bonus.mp4")
        media, _ = self.scan()
        movie=self.matched(media)[0]
        folders={'none':'Featurettes','plex':'Other','jellyfin':'Other','emby':'extras'}
        for style, folder in folders.items():
            options=core.SortOptions(id_style=style)
            target=core.destination(movie,self.library,options)
            self.assertEqual(related_media.targets(movie,target,options)[0][1].parent,target.parent/folder)

    def test_manual_association_and_category_survive_a_new_scan(self):
        self.file("Film/Film.2020.mkv")
        self.file("Film/Extras/Bonus.mp4")
        media, extras=self.scan()
        extras[0].update(category="Interviews",owner=str(media[0].source))
        history=core.History()
        history.save_related(extras[0])
        rescanned, rediscovered=self.scan()
        history.restore_related(rescanned,rediscovered)
        self.assertEqual(rediscovered[0]["category"],"Interviews")
        self.assertEqual(rescanned[0].extras,rediscovered)

    def test_automatic_cleanup_can_remove_empty_bonus_folders_and_undo_them(self):
        movie=self.file("Film/Film.2020.mkv")
        bonus=self.file("Film/Bonus Features/Bonus.mp4")
        media, extras=self.scan()
        self.matched(media)
        result,journal=core.sort_and_finish(media,self.library,self.source,mode="move",auto_cleanup=True)
        self.assertEqual(result["sorted"],1)
        self.assertFalse(movie.parent.exists())
        core.undo(journal)
        self.assertTrue(movie.is_file())
        self.assertTrue(bonus.is_file())

    def test_in_place_movie_can_organize_new_extras_without_moving_the_main_file(self):
        main=self.file("Movies/Film (2020)/Film (2020).mkv")
        extra=self.file("Movies/Film (2020)/Bonus Features/New bonus.mp4")
        media, _=self.scan()
        movie=self.matched(media)[0]
        core.History().save(movie)
        self.assertTrue(core.History().restore(movie,self.source,"move"))
        self.assertEqual(movie.status,"Ready")
        count,journal=core.organize(media,self.source,mode="move")
        self.assertEqual(count,1)
        self.assertTrue(main.exists())
        self.assertFalse(extra.exists())
        self.assertTrue((main.parent/"Featurettes"/extra.name).exists())
        self.assertEqual(core.undo(journal),1)
        self.assertTrue(extra.exists())
