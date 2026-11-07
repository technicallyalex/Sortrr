import os,queue,shutil,subprocess,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from previews import PreviewManager,Frame,timestamp
@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg tools are required for real video tests')
class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory(); cls.source=Path(cls.fixture.name)/'test & preview.mp4'
        subprocess.run([shutil.which('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24:duration=3','-c:v','mpeg4','-y',str(cls.source)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=15)
    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.cache=Path(self.tmp.name)/'previews'; self.callbacks=queue.Queue()
        self.manager=PreviewManager(self.cache,self.callbacks.put)
    def tearDown(self):
        self.manager.close(wait=True); self.manager.pool.shutdown(wait=True,cancel_futures=True); self.tmp.cleanup()
    def test_real_png_dimensions_seek_and_disk_cache(self):
        frame=self.manager.frame(self.source,fraction=.5,size=(96,54)); raw=frame.path.read_bytes()
        self.assertTrue(raw.startswith(b'\x89PNG')); self.assertAlmostEqual(frame.duration,3,places=1); self.assertEqual(frame.seconds,1.5)
        with patch.object(self.manager,'run',side_effect=AssertionError('Cache must prevent decoding')):
            again=self.manager.frame(self.source,fraction=.5,size=(96,54))
        self.assertEqual(frame,again)
    def test_corrupt_cache_is_regenerated(self):
        frame=self.manager.frame(self.source); frame.path.write_bytes(b'corrupt')
        restored=self.manager.frame(self.source); self.assertTrue(restored.path.read_bytes().startswith(b'\x89PNG'))
    def test_fingerprint_invalidates_changed_sources(self):
        copied=Path(self.tmp.name)/'source.mp4'; copied.write_bytes(self.source.read_bytes())
        _,first=self.manager.identity(copied); st=copied.stat(); os.utime(copied,ns=(st.st_atime_ns,st.st_mtime_ns+1000000))
        _,second=self.manager.identity(copied); self.assertNotEqual(first,second)
    def test_duplicate_requests_share_work_and_dispatch_callbacks(self):
        gate=threading.Event(); entered=threading.Event(); results=[]
        def frame(*args,**kwargs): entered.set(); gate.wait(3); return Frame(Path('frame.png'),1,3)
        with patch.object(self.manager,'frame',side_effect=frame) as worker:
            for i in range(3): self.assertTrue(self.manager.request(self.source,lambda result,error:results.append((result,error))))
            self.assertTrue(entered.wait(3)); gate.set()
            for i in range(3): self.callbacks.get(timeout=3)()
            self.assertEqual(worker.call_count,1); self.assertEqual(len(results),3); self.assertTrue(all(error is None for frame,error in results))
    def test_pending_work_is_bounded(self):
        gate=threading.Event()
        with patch.object(self.manager,'frame',side_effect=lambda *args,**kwargs:(gate.wait(3),Frame(Path('frame.png'),0,3))[1]):
            try:
                accepted=[self.manager.request(self.source,lambda frame,error:None,seconds=i) for i in range(20)]
                self.assertEqual(sum(accepted),12); self.assertLessEqual(len(self.manager.pending),12)
            finally: gate.set()
    def test_real_stream_stops_and_releases_process(self):
        stop=threading.Event(); frames=[]; errors=[]
        def emit(raw,seconds,error):
            if raw: frames.append((raw,seconds))
            elif error: errors.append(error)
            if len(frames)>=2: stop.set()
        thread=threading.Thread(target=self.manager.stream,args=(self.source,0,(160,90),stop,lambda proc:None,emit)); thread.start(); thread.join(8)
        if thread.is_alive(): stop.set(); self.manager.close(wait=True); thread.join(3)
        self.assertFalse(thread.is_alive()); self.assertGreaterEqual(len(frames),2)
        self.assertTrue(frames[0][0].startswith(b'P6\n160 90\n255\n')); self.assertGreater(frames[1][1],frames[0][1])
        self.assertEqual(errors,[]); self.assertFalse(self.manager.processes)
    def test_missing_tools_and_bad_media_fail_without_changing_source(self):
        with patch.object(self.manager,'ffmpeg',None):
            with self.assertRaisesRegex(RuntimeError,'Install FFmpeg'): self.manager.frame(self.source)
        invalid=Path(self.tmp.name)/'bad.mkv'; invalid.write_bytes(b'not video')
        with self.assertRaises(RuntimeError): self.manager.frame(invalid)
        self.assertEqual(invalid.read_bytes(),b'not video'); self.assertFalse(self.manager.processes)
    def test_close_prevents_new_work(self):
        self.manager.close(wait=True); self.assertFalse(self.manager.request(self.source,lambda frame,error:None))
    def test_timestamp_format(self):
        self.assertEqual(timestamp(3661),'1:01:01'); self.assertEqual(timestamp(-1),'0:00:00')
if __name__=='__main__': unittest.main()
