import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import core
class FileToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.source=self.root/'source'; self.source.mkdir()
        self.data_patch=patch.object(core,'DATA',self.root/'data'); self.data_patch.start()
    def tearDown(self): self.data_patch.stop(); self.tmp.cleanup()
    def file(self,name,content=b'test'):
        p=self.source/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(content); return p
    def media(self,name='Old.Movie.2020.mkv'):
        p=self.file(name,b'video'); m=core.parse(p); m.chosen={'title':'Correct Title','year':'2020','provider':'TMDB','id':123}; m.status='Ready'; return m
    def test_rename_media_subtitles_and_assets_without_moving_folders(self):
        m=self.media(); sub=self.file('Old.Movie.2020.en.srt'); nfo=self.file('Old.Movie.2020.nfo'); poster=self.file('Old.Movie.2020-poster.jpg'); shared=self.file('poster.jpg')
        options=core.SortOptions(id_style='plex'); changes=core.plan_renames([m],options)
        self.assertEqual(len(changes),4); self.assertTrue(all(c.target.parent==self.source for c in changes))
        self.assertTrue(m.source.exists(),'Planning must not modify sources')
        count,journal=core.organize([m],self.root/'unused',mode='rename',options=options)
        self.assertEqual(count,1); self.assertEqual(m.status,'Renamed')
        target=self.source/'Correct Title (2020) {tmdb-123}.mkv'
        self.assertTrue(target.exists()); self.assertTrue(target.with_suffix('.en.srt').exists()); self.assertTrue(target.with_suffix('.nfo').exists())
        self.assertTrue(target.with_name(target.stem+'-poster.jpg').exists()); self.assertTrue(shared.exists())
        self.assertFalse((self.root/'unused').exists())
        self.assertEqual(core.undo(journal),4); self.assertTrue(m.source.exists()); self.assertTrue(sub.exists()); self.assertTrue(nfo.exists()); self.assertTrue(poster.exists())
    def test_rename_conflict_is_preflighted_for_whole_group(self):
        m=self.media(); sub=self.file('Old.Movie.2020.en.srt'); self.file('Correct Title (2020).en.srt',b'keep')
        count,_=core.organize([m],self.source,mode='rename')
        self.assertEqual(count,0); self.assertTrue(m.source.exists()); self.assertTrue(sub.exists())
        self.assertFalse((self.source/'Correct Title (2020).mkv').exists())
    def test_changed_rename_source_is_skipped(self):
        m=self.media(); m.source.write_bytes(b'changed')
        self.assertIn('Source changed',core.plan_renames([m])[0].error)
        self.assertEqual(core.organize([m],self.source,mode='rename')[0],0)
    def test_cleanup_defaults_protect_media_and_optional_files(self):
        paths=[self.file(n) for n in ['Movie.mkv','Movie.en.srt','Thumbs.db','movie.sfv','readme.txt','Movie.nfo','poster.jpg','archive.rar','sample.mkv']]
        plan=core.plan_cleanup(self.source); selected={i.path for i in plan.files if i.recommended}
        self.assertEqual(selected,{self.source/'Thumbs.db',self.source/'movie.sfv'})
        self.assertNotIn(self.source/'Movie.mkv',{i.path for i in plan.files}); self.assertNotIn(self.source/'Movie.en.srt',{i.path for i in plan.files})
        self.assertTrue(all(p.exists() for p in paths))
        result,journal=core.apply_cleanup(plan,selected)
        self.assertEqual(result['files'],2); self.assertTrue((self.source/'Movie.nfo').exists()); self.assertTrue((self.source/'poster.jpg').exists())
        self.assertEqual(core.undo(journal),2); self.assertTrue(all(p.exists() for p in paths))
    def test_cleanup_selected_files_and_empty_folders_restore(self):
        junk=self.file('Old/Nested/readme.txt'); (self.source/'Empty').mkdir(); kept=self.file('Keep/Movie.mkv')
        plan=core.plan_cleanup(self.source)
        expected={self.source/'Old/Nested',self.source/'Old',self.source/'Empty'}
        self.assertEqual(set(core.cleanup_empty_folders(plan,{junk})),expected)
        result,journal=core.apply_cleanup(plan,{junk})
        self.assertEqual((result['files'],result['folders']),(1,3)); self.assertTrue(kept.exists()); self.assertTrue(self.source.exists())
        self.assertTrue((self.source/'.sortrr-trash').is_dir()); self.assertEqual(core.undo(journal),4)
        self.assertTrue(junk.exists()); self.assertTrue((self.source/'Empty').is_dir())
    def test_cleanup_can_preserve_empty_folders(self):
        junk=self.file('Old/readme.txt'); plan=core.plan_cleanup(self.source)
        result,_=core.apply_cleanup(plan,{junk},remove_empty=False)
        self.assertEqual(result['folders'],0); self.assertTrue(junk.parent.exists())
    def test_cleanup_skips_changed_and_new_files(self):
        junk=self.file('Old/readme.txt'); plan=core.plan_cleanup(self.source); junk.write_bytes(b'changed')
        result,_=core.apply_cleanup(plan,{junk})
        self.assertEqual(result['files'],0); self.assertEqual(len(result['skipped']),1); self.assertTrue(junk.exists())
        junk.write_bytes(b'test'); plan=core.plan_cleanup(self.source); new=self.file('Old/New.mkv')
        result,_=core.apply_cleanup(plan,{junk}); self.assertEqual(result['folders'],0); self.assertTrue(new.exists())
    def test_cleanup_cannot_accept_unreviewed_paths(self):
        main=self.file('Movie.mkv'); plan=core.plan_cleanup(self.source)
        with self.assertRaises(ValueError): core.apply_cleanup(plan,{main})
        outside=self.root/'outside.txt'; outside.write_bytes(b'outside')
        with self.assertRaises(ValueError): core.apply_cleanup(plan,{outside})
        self.assertTrue(main.exists()); self.assertTrue(outside.exists())
    def test_cleanup_excludes_destinations_and_recovery_storage(self):
        self.file('Library/Thumbs.db'); self.file('.sortrr-trash/old/readme.txt'); junk=self.file('Old/movie.sfv')
        plan=core.plan_cleanup(self.source,[self.source/'Library'])
        self.assertEqual([i.path for i in plan.files],[junk])
        self.assertNotIn(self.source/'Library',plan.contents); self.assertNotIn(self.source/'.sortrr-trash',plan.contents)
    def test_cleanup_undo_preserves_modified_files_and_conflicts(self):
        junk=self.file('readme.txt'); plan=core.plan_cleanup(self.source); _,journal=core.apply_cleanup(plan,{junk})
        record=next(r for r in core.journal_records(journal) if r['event']=='complete')
        stored=Path(record['target']); stored.write_bytes(b'edited')
        self.assertEqual(core.undo(journal),0); self.assertTrue(stored.exists())
        stored.write_bytes(b'test'); junk.write_bytes(b'new file')
        self.assertEqual(core.undo(journal),0); self.assertEqual(junk.read_bytes(),b'new file')
    def test_cleanup_partial_journal_can_be_undone(self):
        junk=self.file('readme.txt'); plan=core.plan_cleanup(self.source); _,journal=core.apply_cleanup(plan,{junk})
        first=journal.read_text().splitlines()[0]; journal.write_text(first+'\n{"event":')
        self.assertEqual(core.undo(journal),1); self.assertTrue(junk.exists())
    def test_cleanup_does_not_follow_directory_links(self):
        outside=self.root/'outside'; outside.mkdir(); (outside/'readme.txt').write_bytes(b'outside')
        link=self.source/'linked'
        if os.name=='nt':
            import subprocess
            result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
            if result.returncode: self.skipTest('Directory junctions unavailable')
        else: link.symlink_to(outside,target_is_directory=True)
        try:
            plan=core.plan_cleanup(self.source)
            self.assertEqual(plan.files,[]); self.assertNotIn(link,plan.contents)
            with self.assertRaises(ValueError): core.source_boundary(link/'readme.txt',self.source)
        finally:
            if os.name=='nt': link.rmdir()
            else: link.unlink()
        self.assertTrue((outside/'readme.txt').exists())
if __name__=='__main__': unittest.main()
