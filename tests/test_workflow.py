import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import core
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.source=self.root/'source'; self.source.mkdir(); self.library=self.root/'library'
        self.patcher=patch.object(core,'DATA',self.root/'data'); self.patcher.start()
    def tearDown(self): self.patcher.stop(); self.tmp.cleanup()
    def file(self,name,data=b'test'):
        p=self.source/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); return p
    def media(self,name='Old/Title.2020.mkv'):
        m=core.parse(self.file(name,b'video')); m.chosen={'title':'Correct Title','year':'2020'}; m.status='Ready'; return m
    def test_copy_finishes_then_cleans_only_recommended_junk(self):
        m=self.media(); junk=self.file('Old/movie.sfv'); notes=self.file('Old/readme.txt'); subtitle=self.file('Old/Title.2020.en.srt')
        result,journal=core.sort_and_finish([m],self.library,self.source,auto_cleanup=True)
        self.assertEqual(result['sorted'],1); self.assertEqual(result['cleanup']['files'],1)
        self.assertTrue(m.source.exists()); self.assertTrue(subtitle.exists()); self.assertTrue(notes.exists()); self.assertFalse(junk.exists())
        self.assertTrue(core.destination(m,self.library).exists())
        self.assertEqual(core.undo(journal),3); self.assertTrue(junk.exists()); self.assertFalse(core.destination(m,self.library).exists())
    def test_move_cleanup_removes_only_successful_empty_source_folders(self):
        good=self.media('Good/Nested/Title.2020.mkv'); bad=self.media('Bad/Other.2020.mkv')
        good_junk=self.file('Good/Nested/movie.sfv'); bad_junk=self.file('Bad/movie.sfv'); unrelated=self.source/'Unrelated'; unrelated.mkdir()
        bad.signature=(0,0)
        result,journal=core.sort_and_finish([good,bad],self.library,self.source,mode='move',auto_cleanup=True)
        self.assertEqual(result['sorted'],1); self.assertEqual(result['cleanup']['files'],1); self.assertEqual(result['cleanup']['folders'],2)
        self.assertTrue(bad.source.exists()); self.assertTrue(bad_junk.exists()); self.assertTrue(unrelated.exists()); self.assertFalse(good.source.parent.exists())
        self.assertEqual(core.undo(journal),4); self.assertTrue(good.source.exists()); self.assertTrue(good_junk.exists())
    def test_shared_unselected_media_keeps_junk(self):
        m=self.media(); junk=self.file('Old/movie.sfv'); self.file('Old/Unmatched.mkv')
        result,_=core.sort_and_finish([m],self.library,self.source,auto_cleanup=True)
        self.assertEqual(result['sorted'],1); self.assertEqual(result['cleanup']['files'],0); self.assertTrue(junk.exists())
    def test_no_success_means_no_cleanup(self):
        m=self.media(); m.signature=(0,0); junk=self.file('Old/movie.sfv')
        result,_=core.sort_and_finish([m],self.library,self.source,auto_cleanup=True)
        self.assertEqual(result['sorted'],0); self.assertTrue(junk.exists())
    def test_changed_junk_after_sort_is_preserved(self):
        m=self.media(); junk=self.file('Old/movie.sfv')
        def report(status):
            if status=='Copied': junk.write_bytes(b'changed after preview')
        result,_=core.sort_and_finish([m],self.library,self.source,auto_cleanup=True,report=report)
        self.assertEqual(result['sorted'],1); self.assertEqual(result['cleanup']['files'],0); self.assertTrue(junk.exists())
        self.assertEqual(len(result['cleanup']['skipped']),1)
    def test_disable_renaming_keeps_original_filename_and_history(self):
        m=self.media(); options=core.SortOptions(rename_files=False)
        result,_=core.sort_and_finish([m],self.library,self.source,options=options)
        target=core.destination(m,self.library,options)
        self.assertEqual(target.name,m.source.name); self.assertTrue(target.exists())
        again=core.parse(m.source); core.History().restore(again,self.library,options=options)
        self.assertEqual(again.status,'Previously copied')
    def test_cleanup_off_preserves_junk(self):
        m=self.media(); junk=self.file('Old/movie.sfv')
        result,_=core.sort_and_finish([m],self.library,self.source)
        self.assertEqual(result['sorted'],1); self.assertTrue(junk.exists())
    def test_unresolved_selection_excludes_matched_and_skipped(self):
        items=[self.media(str(i)+'.mkv') for i in range(5)]
        for m,status in zip(items,['No match','Choose match','Lookup failed: offline','Skipped by you','Ready']):
            m.status=status
            if status!='Ready': m.chosen=None
        self.assertEqual(core.unresolved_media(items),items[:3])
    def test_wizard_can_correct_media_type_and_episode_numbers(self):
        m=self.media(); m.chosen=None; m.status='No match'
        candidate={'title':'Correct Show','year':'2018','provider':'TVmaze','id':1,'external_ids':{'thetvdb':222}}
        core.resolve_manually(m,candidate,'Correct Show','2018',2,3,'TV')
        self.assertEqual((m.kind,m.season,m.episode,m.status),('TV',2,3,'Ready'))
        restored=core.parse(m.source); self.assertTrue(core.History().restore(restored))
        self.assertEqual((restored.season,restored.episode),(2,3)); self.assertEqual(restored.chosen,candidate)
    def test_wizard_rejects_invalid_numbering_changed_files_and_unsupported_patterns(self):
        m=self.media(); m.chosen=None; m.status='No match'; candidate={'title':'Example','year':'2020'}
        with self.assertRaises(ValueError): core.resolve_manually(m,candidate,'Example','2020',-1,0,'TV')
        m.status='Unsupported episode pattern'
        with self.assertRaises(ValueError): core.resolve_manually(m,candidate,'Example','2020',1,1,'TV')
        m.status='No match'; m.source.write_bytes(b'changed')
        with self.assertRaises(ValueError): core.resolve_manually(m,candidate,'Example','2020')
    def test_manual_movie_is_sorted_without_a_database_id_and_remembered(self):
        media = core.parse(self.file('Unknown.2020.mkv', b'movie'))
        media.status = 'No match'
        entry = core.build_manual_entry(media, 'Local: Cut', '2023', 'Movie')
        options = core.SortOptions(movie_layout='year', id_style='jellyfin')
        target = self.library / 'Movies' / '2023' / 'Local Cut (2023)' / 'Local Cut (2023).mkv'
        self.assertEqual(core.destination(entry, self.library, options), target)
        core.resolve_manually(media, entry.chosen, entry.query, entry.year, kind='Movie')
        count, _ = core.organize([media], self.library, options=options)
        self.assertEqual(count, 1)
        self.assertEqual(target.read_bytes(), b'movie')
        restored = core.parse(media.source)
        self.assertTrue(core.History().restore(restored))
        self.assertEqual(restored.chosen, {'title': 'Local: Cut', 'year': '2023', 'provider': 'Manual'})

    def test_manual_show_validates_fields_and_supports_specials_without_a_year(self):
        media = core.parse(self.file('Unknown.mkv'))
        entry = core.build_manual_entry(media, 'Archive Show', '', 'TV', 0, 2)
        self.assertEqual(
            core.destination(entry, self.library),
            self.library / 'TV Shows' / 'Archive Show' / 'Season 00' / 'Archive Show - S00E02.mkv',
        )
        for title, year, season, episode in [(' / . ', '', 1, 1), ('Series', '24', 1, 1), ('Series', '', 1, 0)]:
            with self.subTest(title=title, year=year, season=season, episode=episode):
                with self.assertRaises(ValueError):
                    core.build_manual_entry(media, title, year, 'TV', season, episode)
        self.assertIsNone(core.Catalog().expected_runtime(entry.chosen, 'TV', 0, 2))

if __name__=='__main__': unittest.main()
