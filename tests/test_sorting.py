import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import core
class SortingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.library=self.root/'Library'
        self.data_patch=patch.object(core,'DATA',self.root/'data'); self.data_patch.start()
    def tearDown(self): self.data_patch.stop(); self.tmp.cleanup()
    def media(self,name='Example.2020.mkv'):
        p=self.root/name; p.write_bytes(b'video')
        m=core.parse(p); m.chosen={'title':'Example','year':'2020'}; m.status='Ready'; return m
    def test_movie_layouts_keep_canonical_filenames(self):
        m=self.media()
        expected={'title':'Movies/Example (2020)/Example (2020).mkv','year':'Movies/2020/Example (2020)/Example (2020).mkv','letter':'Movies/E/Example (2020)/Example (2020).mkv','year_first':'Movies/2020 - Example/Example (2020).mkv'}
        for layout,path in expected.items():
            self.assertEqual(core.destination(m,self.library,core.SortOptions(movie_layout=layout)),self.library/Path(path))
    def test_show_layouts_and_specials(self):
        m=self.media('Example.S00E03.mkv')
        for layout,path in [('season','TV Shows/Example (2020)/Season 00/Example (2020) - S00E03.mkv'),('flat','TV Shows/Example (2020)/Example (2020) - S00E03.mkv')]:
            self.assertEqual(core.destination(m,self.library,core.SortOptions(show_layout=layout)),self.library/Path(path))
    def test_unknown_year_and_numeric_titles(self):
        m=self.media(); m.chosen={'title':'2001: A Space Odyssey','year':''}
        self.assertEqual(core.destination(m,self.library,core.SortOptions(movie_layout='letter')).parts[-3],'#')
        self.assertEqual(core.destination(m,self.library,core.SortOptions(movie_layout='year')).parts[-3],'Unknown Year')
    def test_invalid_layout_rejected(self):
        with self.assertRaises(ValueError): core.SortOptions(movie_layout='../escape')
        with self.assertRaises(ValueError): core.SortOptions(show_layout='unknown')
    def test_history_remembers_multiple_layouts(self):
        m=self.media(); _,default_journal=core.organize([m],self.library)
        year=core.SortOptions(movie_layout='year')
        again=core.parse(m.source); h=core.History(); h.restore(again,self.library,options=year)
        self.assertEqual(again.status,'Ready')
        count,year_journal=core.organize([again],self.library,options=year); self.assertEqual(count,1)
        for options in [core.SortOptions(),year]:
            cached=core.parse(m.source); h.restore(cached,self.library,options=options)
            self.assertEqual(cached.status,'Previously copied')
        self.assertEqual(core.undo(year_journal),1)
        cached=core.parse(m.source); h.restore(cached,self.library,options=year); self.assertEqual(cached.status,'Ready')
        cached=core.parse(m.source); h.restore(cached,self.library); self.assertEqual(cached.status,'Previously copied')
    def test_move_flat_show_subtitle_and_undo(self):
        m=self.media('Example.S02E03.mkv'); subtitle=self.root/'Example.S02E03.en.srt'; subtitle.write_text('captions')
        options=core.SortOptions(show_layout='flat')
        count,journal=core.organize([m],self.library,mode='move',options=options)
        target=core.destination(m,self.library,options)
        self.assertEqual(count,1); self.assertEqual(m.organized_path,target)
        self.assertTrue(target.with_suffix('.en.srt').exists()); self.assertFalse(m.source.exists())
        cached=core.parse(target); core.History().restore(cached,self.library,'move',options)
        self.assertEqual(cached.status,'Already organized')
        self.assertEqual(core.undo(journal),2); self.assertTrue(m.source.exists()); self.assertTrue(subtitle.exists())
    def test_numeric_sorting_and_filters(self):
        items=[self.media('A.S10E12.mkv'),self.media('B.S02E03.mkv'),self.media('Movie.1999.mkv')]
        items[0].chosen={'title':'Zebra','year':'2000'}; items[1].chosen={'title':'Alpha','year':'2020'}; items[2].chosen={'title':'Movie','year':''}
        self.assertEqual(core.sorted_media_indices(items,'season'),[1,0,2])
        self.assertEqual(core.sorted_media_indices(items,'episode',True),[0,1,2])
        self.assertEqual(core.sorted_media_indices(items,'year',True),[1,0,2])
        self.assertEqual(core.sorted_media_indices(items,'match',media_filter='TV shows'),[1,0])
        self.assertEqual(core.sorted_media_indices(items,'file',media_filter='Movies'),[2])
    def test_layout_paths_stay_inside_library(self):
        m=self.media(); m.chosen={'title':'../../bad:movie','year':'../../outside'}
        for layout in core.MOVIE_LAYOUTS.values():
            target=core.destination(m,self.library,core.SortOptions(movie_layout=layout))
            self.assertTrue(target.resolve().is_relative_to(self.library.resolve()))
if __name__=='__main__': unittest.main()
