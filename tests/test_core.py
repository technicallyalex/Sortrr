import unittest, tempfile
from pathlib import Path
from unittest.mock import patch
import core
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.src=self.root/'in'; self.src.mkdir(); self.out=self.root/'library'
        self.patch=patch.object(core,'DATA',self.root/'data'); self.patch.start()
    def tearDown(self): self.patch.stop(); self.tmp.cleanup()
    def media(self,name):
        p=self.src/name; p.write_bytes(b'media-test'); m=core.parse(p); m.chosen={'title':'Example','year':'2020'}; m.status='Ready'; return m
    def test_parse(self):
        m=self.media('Example.2020.S02E03.1080p.mkv'); self.assertEqual((m.query,m.year,m.season,m.episode),('Example','2020',2,3))
    def test_copy_subtitle_and_undo(self):
        m=self.media('Example.2020.mkv'); (self.src/'Example.2020.en.srt').write_text('subtitle')
        n,j=core.organize([m],self.out); self.assertEqual(n,1); dst=core.destination(m,self.out)
        self.assertEqual(dst.read_bytes(),m.source.read_bytes()); self.assertTrue(dst.with_suffix('.en.srt').exists()); self.assertEqual(core.undo(j),2); self.assertTrue(m.source.exists())
    def test_collision(self):
        m=self.media('Example.2020.mkv'); dst=core.destination(m,self.out); dst.parent.mkdir(parents=True); dst.write_text('keep')
        self.assertEqual(core.organize([m],self.out)[0],0); self.assertEqual(dst.read_text(),'keep')
    def test_changed_source(self):
        m=self.media('Example.2020.mkv'); m.source.write_text('changed'); self.assertEqual(core.organize([m],self.out)[0],0)
    def test_undo_preserves_modified(self):
        m=self.media('Example.2020.mkv'); _,j=core.organize([m],self.out); core.destination(m,self.out).write_text('modified'); self.assertEqual(core.undo(j),0)
    def test_ambiguous_match(self):
        m=self.media('Example.2020.mkv'); m.chosen=None; c=core.Catalog()
        with patch.object(c,'search',return_value=[{'title':'Example','year':'2020','score':1},{'title':'Example','year':'2021','score':1}]): c.identify(m)
        self.assertIsNone(m.chosen)
    def test_tmdb_movie_provider(self):
        m=self.media('Example.2020.mkv'); c=core.Catalog()
        with patch.dict(core.os.environ,{'SORTRR_TMDB_TOKEN':'test-token'}), patch.object(c,'get',return_value={'results':[{'title':'Example','release_date':'2020-01-01','id':10}]}) as get:
            c.identify(m)
            self.assertEqual(m.chosen['provider'],'TMDB')
            self.assertEqual(m.status,'Ready')
            self.assertIn('/3/search/movie?',get.call_args[0][0])
    def test_episode_validation(self):
        m=self.media('Example.S01E02.mkv'); m.chosen=None; c=core.Catalog()
        with patch.object(c,'search',return_value=[{'title':'Example','year':'2020','score':1,'id':1}]), patch.object(c,'get',return_value=[{'season':1,'number':1}]): c.identify(m)
        self.assertIsNone(m.chosen)
        self.assertEqual(m.status,'Episode needs review')
    def test_move_with_subtitles_and_undo(self):
        m=self.media('Example.2020.mkv'); subtitle=self.src/'Example.2020.en.srt'; subtitle.write_text('subtitles')
        with patch.object(core.shutil,'copyfileobj',side_effect=AssertionError('Move must not copy')):
            count,journal=core.organize([m],self.src,mode='move')
        target=core.destination(m,self.src)
        self.assertEqual(count,1); self.assertFalse(m.source.exists()); self.assertFalse(subtitle.exists())
        self.assertEqual(target.read_bytes(),b'media-test')
        self.assertEqual(core.undo(journal),2)
        self.assertEqual(m.source.read_bytes(),b'media-test'); self.assertEqual(subtitle.read_text(),'subtitles')
        self.assertFalse(target.exists()); self.assertEqual(core.undo(journal),0)
    def test_move_conflict_preserves_original(self):
        m=self.media('Example.2020.mkv'); target=core.destination(m,self.src)
        target.parent.mkdir(parents=True); target.write_bytes(b'existing')
        self.assertEqual(core.organize([m],self.src,mode='move')[0],0)
        self.assertEqual(m.source.read_bytes(),b'media-test'); self.assertEqual(target.read_bytes(),b'existing')
    def test_move_undo_preserves_modified_and_occupied_source(self):
        m=self.media('Example.2020.mkv'); _,journal=core.organize([m],self.src,mode='move')
        target=core.destination(m,self.src); target.write_bytes(b'edited')
        self.assertEqual(core.undo(journal),0)
        target.write_bytes(b'media-test'); m.source.write_bytes(b'new original')
        self.assertEqual(core.undo(journal),0); self.assertTrue(target.exists())
        self.assertEqual(m.source.read_bytes(),b'new original')
    def test_repeat_in_place_scan(self):
        m=self.media('Example.2020.mkv'); core.organize([m],self.src,mode='move')
        again=core.parse(core.destination(m,self.src)); again.chosen=m.chosen; again.status='Ready'
        count,_=core.organize([again],self.src,mode='move')
        self.assertEqual(count,0); self.assertEqual(again.status,'Already organized'); self.assertTrue(again.source.exists())
    def test_undo_interrupted_move(self):
        m=self.media('Example.2020.mkv'); _,journal=core.organize([m],self.src,mode='move')
        lines=journal.read_text().splitlines(); journal.write_text(lines[0]+'\n')
        self.assertEqual(core.undo(journal),1); self.assertTrue(m.source.exists())
    def test_history_persists_manual_match(self):
        m=self.media('Wrong.Title.2020.mkv'); m.query='Corrected title'; core.History().save(m)
        again=core.parse(m.source)
        self.assertTrue(core.History().restore(again,self.out))
        self.assertEqual(again.chosen,m.chosen); self.assertEqual(again.query,'Corrected title')
        self.assertEqual(again.status,'Ready'); self.assertTrue(again.cached)
    def test_history_invalidates_changed_source(self):
        m=self.media('Example.2020.mkv'); h=core.History(); h.save(m)
        m.source.write_bytes(b'different contents')
        self.assertFalse(h.restore(core.parse(m.source),self.out))
    def test_history_copy_checks_outputs_and_new_subtitles(self):
        m=self.media('Example.2020.mkv'); _,journal=core.organize([m],self.out)
        h=core.History(); again=core.parse(m.source)
        self.assertTrue(h.restore(again,self.out)); self.assertEqual(again.status,'Previously copied')
        # A different destination must still be eligible for organizing.
        other=core.parse(m.source); h.restore(other,self.root/'other'); self.assertEqual(other.status,'Ready')
        (self.src/'Example.2020.en.srt').write_text('new subtitle')
        again=core.parse(m.source); h.restore(again,self.out); self.assertEqual(again.status,'Ready')
        core.undo(journal)
        again=core.parse(m.source); h.restore(again,self.out); self.assertEqual(again.status,'Ready')
    def test_history_move_and_undo_paths(self):
        m=self.media('Example.2020.mkv'); _,journal=core.organize([m],self.src,mode='move')
        target=core.destination(m,self.src); again=core.parse(target)
        self.assertTrue(core.History().restore(again,self.src,'move'))
        self.assertEqual(again.status,'Already organized'); self.assertEqual(again.chosen,m.chosen)
        core.undo(journal); again=core.parse(m.source)
        self.assertTrue(core.History().restore(again,self.src,'move')); self.assertEqual(again.status,'Ready')
    def test_history_retries_failures_and_provider_change(self):
        m=self.media('Example.2020.mkv'); m.chosen=None; m.status='Lookup failed: offline'
        h=core.History(); h.save(m); self.assertFalse(h.restore(core.parse(m.source)))
        with patch.dict(core.os.environ,{'SORTRR_TMDB_TOKEN':''}):
            m.status='No match'; h.save(m); self.assertTrue(h.restore(core.parse(m.source)))
            with h.connect() as db: db.execute("UPDATE files SET provider='Apple'")
        with patch.dict(core.os.environ,{'SORTRR_TMDB_TOKEN':'token'}):
            self.assertFalse(h.restore(core.parse(m.source)))
    def test_history_remembers_skip(self):
        m=self.media('Example.2020.mkv'); m.chosen=None; m.status='Skipped by you'; core.History().save(m)
        again=core.parse(m.source); self.assertTrue(core.History().restore(again)); self.assertEqual(again.status,'Skipped by you')
    def test_history_changed_choice_gets_new_destination(self):
        m=self.media('Example.2020.mkv'); core.organize([m],self.out)
        m.chosen={'title':'Correct title','year':'2020'}; m.status='Ready'; core.History().save(m)
        again=core.parse(m.source); core.History().restore(again,self.out)
        self.assertEqual(again.status,'Ready'); self.assertEqual(again.chosen['title'],'Correct title')
    def test_history_uncertain_expires(self):
        m=self.media('Example.2020.mkv'); m.chosen=None; m.status='Choose match'
        h=core.History()
        with patch.object(core.time,'time',return_value=100): h.save(m)
        with patch.object(core.time,'time',return_value=86501): self.assertFalse(h.restore(core.parse(m.source)))
    def test_forget_selected_also_forgets_organized_alias(self):
        m=self.media('Example.2020.mkv'); core.organize([m],self.out)
        other=self.media('Other.2020.mkv'); core.History().save(other)
        h=core.History(); h.forget([core.destination(m,self.out)])
        self.assertFalse(h.restore(core.parse(m.source)))
        self.assertFalse(h.restore(core.parse(core.destination(m,self.out))))
        self.assertTrue(h.restore(core.parse(other.source)))
        self.assertFalse(h.processed(m,self.out,'copy'))
    def test_clear_cache_preserves_media_settings_and_undo(self):
        m=self.media('Example.2020.mkv'); _,journal=core.organize([m],self.out)
        settings=core.DATA/'settings.json'; settings.write_text('settings')
        token=core.DATA/'tmdb-token.txt'; token.write_text('secret')
        cache=core.DATA/'cache'; cache.mkdir(); cached=cache/('a'*64+'.json'); cached.write_text('{}')
        other=cache/'unrelated.txt'; other.write_text('keep')
        c=core.Catalog(); c.memory['url']={'stale':True}
        core.History().clear(); c.clear_cache()
        self.assertFalse(core.History().restore(core.parse(m.source)))
        self.assertFalse(core.History().processed(m,self.out,'copy'))
        self.assertFalse(cached.exists()); self.assertEqual(c.memory,{})
        self.assertTrue(other.exists()); self.assertEqual(settings.read_text(),'settings')
        self.assertEqual(token.read_text(),'secret'); self.assertTrue(journal.exists())
        self.assertTrue(m.source.exists()); self.assertTrue(core.destination(m,self.out).exists())
        self.assertEqual(core.undo(journal),1)
    def test_reidentify_replaces_saved_match(self):
        m=self.media('Example.2020.mkv'); m.chosen={'title':'Wrong','year':'1990'}; core.History().save(m)
        c=core.Catalog()
        def identify(fresh):
            self.assertTrue(c._fresh); self.assertIsNone(fresh.chosen); self.assertFalse(fresh.cached)
            self.assertEqual(fresh.query,'Example')
            fresh.chosen={'title':'Correct','year':'2020'}; fresh.status='Ready'
        with patch.object(c,'identify',side_effect=identify): c.reidentify(m)
        again=core.parse(m.source); self.assertTrue(core.History().restore(again))
        self.assertEqual(again.chosen['title'],'Correct'); self.assertFalse(c._fresh)
    def test_failed_reidentify_does_not_keep_wrong_match(self):
        m=self.media('Example.2020.mkv'); core.History().save(m); c=core.Catalog()
        with patch.object(c,'identify',side_effect=OSError('offline')):
            with self.assertRaises(OSError): c.reidentify(m)
        self.assertIsNone(m.chosen); self.assertFalse(c._fresh)
        self.assertFalse(core.History().restore(core.parse(m.source)))
    def test_fresh_requests_bypass_memory_and_disk(self):
        import io, json, hashlib
        url='https://example.test/search'; c=core.Catalog(); c.memory[url]={'old':'memory'}
        cache=core.DATA/'cache'; cache.mkdir(parents=True)
        path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.json'); path.write_text(json.dumps({'old':'disk'}))
        with patch.object(core.urllib.request,'urlopen',return_value=io.BytesIO(b'{"fresh":true}')) as request:
            with c.fresh(): self.assertEqual(c.get(url),{'fresh':True})
            request.assert_called_once()
        with patch.object(core.urllib.request,'urlopen',side_effect=AssertionError('Should now reuse fresh response')):
            self.assertEqual(c.get(url),{'fresh':True})
    def test_default_movie_database_needs_tmdb_connection(self):
        m=self.media('Example.2020.mkv')
        with patch.dict(core.os.environ,{'SORTRR_TMDB_TOKEN':''}), patch.object(core.Catalog,'get',side_effect=AssertionError('No fallback database')):
            self.assertEqual(core.History.provider(m),'TMDB')
            with self.assertRaises(core.DatabaseSetupRequired): core.Catalog().search(m)
    def test_tmdb_invalid_token_is_setup_error(self):
        import urllib.error
        url='https://api.themoviedb.org/3/search/movie?query=Example'
        error=urllib.error.HTTPError(url,401,'Unauthorized',{},None)
        with patch.object(core.urllib.request,'urlopen',side_effect=error):
            with self.assertRaises(core.DatabaseSetupRequired): core.Catalog().get(url)
    def test_numeric_and_bracketed_movie_names(self):
        for name,title,year in [
            ('01 Back to the Future - 1985 1080p.mp4','Back to the Future','1985'),
            ('2001.a.space.odyssey.1968.2160p.mkv','2001 a space odyssey','1968'),
            ('12.Angry.Men.1957.mkv','12 Angry Men','1957'),
            ('1917.2019.mkv','1917','2019'),
            ('Black Angel (1980).mkv','Black Angel','1980'),
            ('[site] Movie [1988].1080p.mkv','Movie','1988'),
        ]:
            m=self.media(name); self.assertEqual((m.query,m.year),(title,year))
    def test_tmdb_alternate_title_retry(self):
        m=self.media('[group] Koe no Katachi (A Silent Voice) [BD 1080p].mkv')
        self.assertEqual(m.query,'Koe no Katachi'); self.assertIn('A Silent Voice',m.alternate_queries)
        with patch.dict(core.os.environ,{'SORTRR_TMDB_TOKEN':'token'}), patch.object(core.Catalog,'get',side_effect=[{'results':[]},{'results':[{'title':'A Silent Voice','release_date':'2016-09-17','id':1}]}]) as get:
            core.Catalog().identify(m)
        self.assertEqual(get.call_count,2); self.assertEqual(m.status,'Ready')
        self.assertEqual(m.chosen['provider'],'TMDB')
    def test_unsupported(self):
        self.assertTrue(self.media('Example.S01E01E02.mkv').status=='Ready')
        self.assertTrue(core.parse(self.src/'Example.S01E01E02.mkv').status.startswith('Unsupported'))
if __name__=='__main__': unittest.main()
