import io,json,sqlite3,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch,Mock
import core

class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.data_patch=patch.object(core,'DATA',self.root/'data'); self.data_patch.start()
    def tearDown(self):
        self.data_patch.stop(); self.tmp.cleanup()
    def media(self,name):
        p=self.root/(name+'.2020.mkv'); p.write_bytes(b'test'); return core.parse(p)
    def history(self):
        h=Mock(); h.restore.return_value=False; return h
    def test_results_finish_out_of_order(self):
        items=[self.media(n) for n in ['Slow','Fast','Third']]
        gate=threading.Event(); fast=threading.Event(); barrier=threading.Barrier(3)
        def identify(m):
            barrier.wait(3)
            if m.query=='Slow': self.assertTrue(gate.wait(3))
            m.status='Ready'
        def report(i,m):
            if i==1: fast.set()
        c=Mock(); c.identify.side_effect=identify
        with ThreadPoolExecutor(max_workers=1) as controller:
            job=controller.submit(core.identify_batch,list(enumerate(items)),c,self.history(),report=report,workers=3)
            try:
                self.assertTrue(fast.wait(3)); self.assertFalse(job.done())
                self.assertEqual(items[1].status,'Ready')
            finally: gate.set()
            self.assertEqual(job.result(5)['errors'],0)
    def test_dispatch_is_bounded(self):
        gate=threading.Event(); filled=threading.Event(); lock=threading.Lock()
        count=0; active=0; maximum=0
        def jobs():
            nonlocal count
            for i in range(50):
                count+=1
                if count==6: filled.set()
                yield i,core.Media(Path(str(i)),str(i))
        def identify(m):
            nonlocal active,maximum
            with lock: active+=1; maximum=max(maximum,active)
            try: self.assertTrue(gate.wait(3)); m.status='Ready'
            finally:
                with lock: active-=1
        c=Mock(); c.identify.side_effect=identify
        with ThreadPoolExecutor(max_workers=1) as controller:
            run=controller.submit(core.identify_batch,jobs(),c,self.history(),workers=3)
            try:
                self.assertTrue(filled.wait(3)); self.assertLessEqual(count,6)
            finally: gate.set()
            self.assertEqual(run.result(5)['completed'],50)
        self.assertLessEqual(maximum,3)
    def test_identical_requests_share_one_fetch_and_atomic_cache(self):
        c=core.Catalog(); gate=threading.Event(); entered=threading.Event(); barrier=threading.Barrier(8)
        def response(*args,**kwargs):
            entered.set(); self.assertTrue(gate.wait(3)); return io.BytesIO(b'{"results":[]}')
        def get(): barrier.wait(3); return c.get('https://api.themoviedb.org/3/search/movie?query=Same')
        with patch.object(core.urllib.request,'urlopen',side_effect=response) as request:
            with ThreadPoolExecutor(max_workers=8) as pool:
                jobs=[pool.submit(get) for _ in range(8)]
                try: self.assertTrue(entered.wait(3))
                finally: gate.set()
                self.assertTrue(all(j.result(5)=={'results':[]} for j in jobs))
            self.assertEqual(request.call_count,1)
        files=list((core.DATA/'cache').iterdir()); self.assertEqual(len(files),1)
        self.assertEqual(json.loads(files[0].read_text()),{'results':[]})
    def test_fresh_flag_is_thread_local(self):
        c=core.Catalog(); entered=threading.Event(); gate=threading.Event()
        def fresh():
            with c.fresh():
                entered.set(); self.assertTrue(gate.wait(3)); self.assertTrue(c._fresh)
            self.assertFalse(c._fresh)
        with ThreadPoolExecutor(max_workers=1) as pool:
            result=pool.submit(fresh)
            try: self.assertTrue(entered.wait(3)); self.assertFalse(c._fresh)
            finally: gate.set()
            result.result(5)
    def test_parallel_history_writes_survive_restart(self):
        items=[self.media('Movie'+str(i)) for i in range(40)]
        c=Mock()
        def identify(m): m.chosen={'title':m.query,'year':'2020'}; m.status='Ready'
        c.identify.side_effect=identify
        result=core.identify_batch(enumerate(items),c)
        self.assertEqual(result['completed'],40); self.assertEqual(result['errors'],0)
        h=core.History()
        for m in items:
            again=core.parse(m.source); self.assertTrue(h.restore(again)); self.assertEqual(again.chosen,m.chosen)
        with h.connect() as db: self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_one_lookup_failure_does_not_block_others(self):
        items=[self.media(n) for n in ['Good','Bad','Other']]; c=Mock()
        def identify(m):
            if m.query=='Bad': raise OSError('offline')
            m.status='Ready'
        c.identify.side_effect=identify
        result=core.identify_batch(enumerate(items),c,self.history())
        self.assertEqual(result['errors'],1); self.assertEqual(result['completed'],3)
        self.assertEqual(items[2].status,'Ready'); self.assertTrue(items[1].status.startswith('Lookup failed'))
    def test_authentication_failure_stops_new_dispatch(self):
        seen=[]; c=Mock(); c.identify.side_effect=core.DatabaseSetupRequired('Connect TMDb')
        def jobs():
            for i in range(1000): seen.append(i); yield i,core.Media(Path(str(i)),str(i))
        result=core.identify_batch(jobs(),c,self.history(),workers=3)
        self.assertEqual(result['setup'],'Connect TMDb'); self.assertLessEqual(len(seen),6)
    def test_scan_can_finish_discovery_for_manual_review_after_authentication_failure(self):
        movies = [self.media(f'Movie{i}') for i in range(6)]
        cached = movies[-1]
        entry = core.build_manual_entry(cached, 'Saved Movie', '2024', 'Movie')
        core.resolve_manually(cached, entry.chosen, entry.query, entry.year, kind='Movie')
        movies[-1] = core.parse(cached.source)
        show = self.media('Episode')
        show.season, show.episode = 1, 2
        catalog = Mock()

        def identify(media):
            if media.kind == 'Movie':
                raise core.DatabaseSetupRequired('Connect TMDb')
            media.status = 'No match'

        catalog.identify.side_effect = identify
        result = core.identify_batch(enumerate(movies + [show]), catalog, workers=1, finish_scan_on_setup=True)
        self.assertEqual(result['completed'], 7)
        self.assertEqual(result['remembered'], 1)
        self.assertEqual([m.status for m in movies[:-1]], ['Connect TMDb'] * 5)
        self.assertEqual(movies[-1].chosen['title'], 'Saved Movie')
        self.assertEqual(show.status, 'No match')

    def test_shared_limiter_spacing_and_cooldown(self):
        clock=[0.0]
        def sleep(seconds): clock[0]+=seconds
        with patch.object(core.time,'monotonic',side_effect=lambda:clock[0]),patch.object(core.time,'sleep',side_effect=sleep):
            limiter=core.RequestLimiter(); host='api.themoviedb.org'
            limiter.acquire(host); limiter.acquire(host); self.assertAlmostEqual(clock[0],.04)
            limiter.backoff(host,2); limiter.acquire(host); self.assertAlmostEqual(clock[0],2.04)
            limiter.acquire('api.tvmaze.com'); limiter.acquire('api.tvmaze.com'); self.assertAlmostEqual(clock[0],2.55)
            limiter.block(host,'Invalid token')
            with self.assertRaises(core.DatabaseSetupRequired): limiter.acquire(host)
    def test_429_respects_retry_after(self):
        clock=[0.0]
        def sleep(seconds): clock[0]+=seconds
        url='https://api.themoviedb.org/3/search/movie?query=Example'
        error=core.urllib.error.HTTPError(url,429,'rate limit',{'Retry-After':'3'},None)
        with patch.object(core.time,'monotonic',side_effect=lambda:clock[0]),patch.object(core.time,'sleep',side_effect=sleep),patch.object(core.urllib.request,'urlopen',side_effect=[error,io.BytesIO(b'{"results":[]}')]) as request:
            self.assertEqual(core.Catalog().get(url),{'results':[]}); self.assertEqual(request.call_count,2)
            self.assertGreaterEqual(clock[0],3)
        self.assertEqual(core.RequestLimiter.retry_after('invalid',5),5)
        with patch.object(core.time,'time',return_value=0):
            self.assertEqual(core.RequestLimiter.retry_after('Thu, 01 Jan 1970 00:00:10 GMT',5),10)
    def test_selected_reidentification_is_parallel(self):
        items=[self.media(str(i)) for i in range(3)]; barrier=threading.Barrier(3); c=core.Catalog()
        def identify(m):
            self.assertTrue(c._fresh); barrier.wait(3)
            m.status='Ready'; m.chosen={'title':m.query,'year':'2020'}
        with patch.object(c,'identify',side_effect=identify):
            result=core.identify_batch(enumerate(items),c,reidentify=True,workers=3)
        self.assertEqual(result['errors'],0); self.assertFalse(c._fresh)

if __name__=='__main__': unittest.main()
