import ctypes,os,queue,shutil,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import core
from audio_output import AudioPlayback,WaveOutput,WaveHeader,WaveFormat,pcm_command
from previews import PreviewManager
class EntryInfoTests(unittest.TestCase):
    def test_movie_details_use_selected_id(self):
        c=core.Catalog()
        with patch.object(c,'get',return_value={'title':'Chosen film','overview':'Plot','runtime':123}) as get:
            data=c.entry_details({'provider':'TMDB','id':42})
        self.assertEqual(get.call_args.args[0],'https://api.themoviedb.org/3/movie/42')
        self.assertEqual(data['entry_url'],'https://www.themoviedb.org/movie/42'); self.assertEqual(data['runtime'],123)
    def test_tvmaze_maps_to_tmdb_only_by_external_id(self):
        c=core.Catalog()
        with patch.dict(os.environ,{'SORTRR_TMDB_TOKEN':'token'}),patch.object(c,'get',side_effect=[{'tv_results':[{'id':77}]},{'name':'Chosen show','overview':'Plot'}]) as get:
            data=c.entry_details({'provider':'TVmaze','id':1,'external_ids':{'thetvdb':222}},'TV')
        self.assertIn('/find/222?external_source=tvdb_id',get.call_args_list[0].args[0])
        self.assertIn('/tv/77',get.call_args_list[1].args[0]); self.assertEqual(data['provider'],'TMDb')
    def test_tvmaze_fallback_does_not_mislabel_its_id(self):
        c=core.Catalog()
        with patch.dict(os.environ,{'SORTRR_TMDB_TOKEN':''}),patch.object(c,'get',return_value={'name':'Show','summary':'<p>Summary &amp; more</p>'}) as get:
            data=c.entry_details({'provider':'TVmaze','id':1},'TV')
        self.assertEqual(get.call_args.args[0],'https://api.tvmaze.com/shows/1'); self.assertEqual(data['provider'],'TVmaze')
        self.assertIn('Summary & more',core.entry_info_text(data))
    def test_ambiguous_external_mapping_falls_back(self):
        c=core.Catalog()
        with patch.dict(os.environ,{'SORTRR_TMDB_TOKEN':'token'}),patch.object(c,'get',side_effect=[{'tv_results':[{'id':1},{'id':2}]},{'name':'TVmaze show'}]):
            data=c.entry_details({'provider':'TVmaze','id':3,'external_ids':{'thetvdb':4}},'TV')
        self.assertEqual(data['provider'],'TVmaze')
    def test_details_format_and_invalid_identity(self):
        text=core.entry_info_text({'title':'Title','original_title':'Original','release_date':'2020-02-03','runtime':120,'genres':[{'name':'Drama'}],'vote_average':7.25,'vote_count':100,'overview':'Full synopsis'})
        for part in ['Original','2020-02-03','120 min','Drama','7.2/10','100 votes','Full synopsis']: self.assertIn(part,text)
        with self.assertRaises(ValueError): core.Catalog().entry_details({'provider':'TMDB','id':'../wrong'})

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg tools required')
class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.root=Path(cls.tmp.name); cls.source=cls.root/'two tracks.mp4'
        subprocess.run([shutil.which('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-f','lavfi','-i','sine=frequency=880:duration=2','-map','0:v','-map','1:a','-map','2:a','-c:v','mpeg4','-c:a','aac','-metadata:s:a:0','language=eng','-metadata:s:a:1','language=spa','-disposition:a:0','default','-disposition:a:1','0','-shortest','-y',str(cls.source)],check=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def setUp(self):
        self.cache=tempfile.TemporaryDirectory(); self.manager=PreviewManager(Path(self.cache.name),lambda cb:cb())
    def tearDown(self): self.manager.close(wait=True); self.manager.pool.shutdown(wait=True,cancel_futures=True); self.cache.cleanup()
    def test_probe_discovers_tracks_languages_and_default(self):
        frame=self.manager.frame(self.source)
        self.assertEqual([track['index'] for track in frame.audio_tracks],[1,2]); self.assertTrue(frame.audio_tracks[0]['default']); self.assertFalse(frame.audio_tracks[1]['default'])
        self.assertIn('eng',frame.audio_tracks[0]['label']); self.assertIn('spa',frame.audio_tracks[1]['label'])
    def test_muted_windows_output_clock_and_shutdown(self):
        if os.name!='nt' or not ctypes.WinDLL('winmm').waveOutGetNumDevs(): self.skipTest('No Windows audio device')
        audio=AudioPlayback(self.manager,self.source,.2,2,volume=0)
        try:
            self.assertTrue(audio.ready.wait(5)); self.assertIsNone(audio.error)
            audio.begin(); deadline=time.monotonic()+2
            while audio.elapsed()<.15 and time.monotonic()<deadline: time.sleep(.01)
            self.assertGreaterEqual(audio.elapsed(),.15); audio.volume(0)
            with audio.lock:
                if audio.sink: self.assertLessEqual(len(audio.sink.buffers),4)
        finally: audio.stop(); audio.thread.join(5)
        self.assertFalse(audio.thread.is_alive()); self.assertFalse(self.manager.processes)
    def test_audio_device_error_is_exposed_and_ready_unblocks(self):
        with patch('audio_output.WaveOutput',side_effect=RuntimeError('device unavailable')):
            audio=AudioPlayback(self.manager,self.source,0,1,0); self.assertTrue(audio.ready.wait(3)); audio.thread.join(3)
        self.assertIn('device unavailable',audio.error); audio.begin(); self.assertGreaterEqual(audio.elapsed(),0); audio.stop()
    def test_audio_timestamp_gap_is_preserved(self):
        shifted=Path(self.cache.name)/'shifted.mp4'
        self.manager.run([self.manager.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-f','lavfi','-i','color=size=160x90:rate=24:duration=2','-itsoffset','0.4','-f','lavfi','-i','sine=frequency=440:duration=1.5','-map','0:v','-map','1:a','-c:v','mpeg4','-c:a','aac','-y',str(shifted)])
        raw=self.manager.run(pcm_command(self.manager.ffmpeg,shifted,0,1))
        self.assertTrue(raw); self.assertFalse(any(raw[:int(.2*48000*4)]))
        self.assertTrue(any(raw[int(.5*48000*4):int(.8*48000*4)]))
    def test_winmm_structures_use_pointer_sized_fields(self):
        self.assertEqual(WaveOutput.RATE,48000)
        self.assertEqual(ctypes.sizeof(WaveHeader),48 if ctypes.sizeof(ctypes.c_void_p)==8 else 32)
        self.assertGreaterEqual(ctypes.sizeof(WaveFormat),18)

if __name__=='__main__': unittest.main()
