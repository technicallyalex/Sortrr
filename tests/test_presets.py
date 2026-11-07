import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import core
class PresetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.library=self.root/'Library'
        self.data_patch=patch.object(core,'DATA',self.root/'data'); self.data_patch.start()
    def tearDown(self): self.data_patch.stop(); self.tmp.cleanup()
    def media(self,name='Example.2020.mkv'):
        p=self.root/name; p.write_bytes(b'video'); m=core.parse(p)
        m.chosen={'title':'Example','year':'2020','provider':'TMDB','id':123}; m.status='Ready'; return m
    def test_documented_movie_id_syntax(self):
        m=self.media()
        for style,tag in [('none',''),('plex',' {tmdb-123}'),('jellyfin',' [tmdbid-123]'),('emby',' [tmdbid=123]')]:
            target=core.destination(m,self.library,core.SortOptions(id_style=style))
            self.assertEqual(target.parent.name,'Example (2020)'+tag)
            self.assertEqual(target.name,'Example (2020)'+tag+'.mkv')
    def test_show_external_ids_and_specials(self):
        m=self.media('Example.S00E03.mkv')
        m.chosen={'title':'Example','year':'2020','provider':'TVmaze','id':111,'external_ids':{'thetvdb':222,'imdb':'tt333'}}
        for style,tag in [('plex',' {tvdb-222}'),('jellyfin',' [tvdbid-222]'),('emby',' [tvdbid=222]')]:
            target=core.destination(m,self.library,core.SortOptions(id_style=style))
            self.assertEqual(target.parent.name,'Season 00')
            self.assertEqual(target.parent.parent.name,'Example (2020)'+tag)
            self.assertEqual(target.name,'Example (2020) - S00E03.mkv')
    def test_tvmaze_id_is_never_mislabeled(self):
        m=self.media('Example.S01E01.mkv'); m.chosen={'title':'Example','year':'2020','provider':'TVmaze','id':111}
        for style in ['plex','jellyfin','emby']: self.assertEqual(core.metadata_tag(m,style),'')
        m.chosen['external_ids']={'imdb':'tt1234567'}
        self.assertEqual(core.metadata_tag(m,'plex'),' {imdb-tt1234567}')
    def test_invalid_ids_are_omitted(self):
        m=self.media()
        for value in [None,True,0,-1,'../escape','123}bad']:
            m.chosen['id']=value; self.assertEqual(core.metadata_tag(m,'plex'),'')
        m.chosen['provider']='Apple'; m.chosen['id']=123; self.assertEqual(core.metadata_tag(m,'plex'),'')
    def test_old_settings_and_preset_detection(self):
        options=core.SortOptions(**{'movie_layout':'title','show_layout':'season'})
        self.assertEqual(core.preset_name(options),'Universal (all three servers)')
        for name,preset in core.LAYOUT_PRESETS.items():
            self.assertEqual(core.preset_name(preset.options),name)
            self.assertEqual(core.SortOptions(**preset.options.to_dict()),preset.options)
            self.assertEqual(preset.options.movie_layout,'title'); self.assertEqual(preset.options.show_layout,'season')
            self.assertTrue(all(url.startswith('https://') for label,url in preset.docs))
        self.assertEqual(core.preset_name(core.SortOptions(movie_layout='year')),'Custom')
    def test_preset_change_preserves_both_output_histories(self):
        m=self.media(); core.organize([m],self.library)
        plex=core.SortOptions(id_style='plex'); again=core.parse(m.source)
        core.History().restore(again,self.library,options=plex); self.assertEqual(again.status,'Ready')
        count,journal=core.organize([again],self.library,options=plex); self.assertEqual(count,1)
        for options in [core.SortOptions(),plex]:
            cached=core.parse(m.source); core.History().restore(cached,self.library,options=options)
            self.assertEqual(cached.status,'Previously copied')
        self.assertEqual(core.undo(journal),1)
        cached=core.parse(m.source); core.History().restore(cached,self.library,options=plex); self.assertEqual(cached.status,'Ready')
    def test_preset_subtitle_moves_and_undo(self):
        m=self.media(); sub=self.root/'Example.2020.en.srt'; sub.write_text('captions')
        for style in ['plex','jellyfin','emby']:
            options=core.SortOptions(id_style=style); m.status='Ready'
            count,journal=core.organize([m],self.library,mode='move',options=options)
            target=core.destination(m,self.library,options)
            self.assertEqual(count,1); self.assertTrue(target.with_suffix('.en.srt').exists())
            self.assertEqual(core.undo(journal),2); self.assertTrue(m.source.exists()); self.assertTrue(sub.exists())
    def test_tagged_filenames_parse_after_cache_reset(self):
        for name in ['Example {tmdb-123}.mkv','Example [tmdbid-123].mkv','Example [tmdbid=123].mkv']:
            self.assertEqual(self.media(name).query,'Example')
    def test_long_names_preserve_complete_identifier(self):
        m=self.media(); m.chosen['title']='Long title '*30
        target=core.destination(m,self.library,core.SortOptions(id_style='plex'))
        self.assertTrue(target.stem.endswith('{tmdb-123}')); self.assertLessEqual(len(target.stem),140)
    def test_tvmaze_search_retains_external_ids(self):
        m=self.media('Example.S01E01.mkv'); c=core.Catalog()
        with patch.object(c,'get',return_value=[{'show':{'id':111,'name':'Example','premiered':'2020-01-01','externals':{'thetvdb':222,'imdb':'tt333'}}}]):
            candidates=c.search(m)
        self.assertEqual(candidates[0]['external_ids']['thetvdb'],222)
if __name__=='__main__': unittest.main()
