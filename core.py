from contextlib import contextmanager
import errno, threading, tempfile, math
from concurrent.futures import ThreadPoolExecutor, Future, wait, FIRST_COMPLETED
from email.utils import parsedate_to_datetime
import html
import unicodedata
import sqlite3
import json, os, re, hashlib, shutil, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from app_paths import APP_DIR, data_directory

ROOT=APP_DIR
DATA=data_directory()
REJECTED = 'Rejected'
REJECT_MOVED = 'Moved to reject folder'
REJECT_RECYCLED = 'Sent to Recycle Bin'
VIDEO={'.mkv','.mp4','.avi','.mov','.m4v','.wmv','.ts','.m2ts','.webm'}
def clean(s):
    s=re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',str(s))
    s=re.sub(r'\s+',' ',s).strip(' .')[:140] or 'Untitled'
    if s.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(10)),*(f'LPT{i}' for i in range(10))}: s='_'+s
    return s
def norm(s): return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().casefold())
@dataclass
class Media:
    source: Path
    query: str
    year: str=''
    season: int|None=None
    episode: int|None=None
    candidates: list=field(default_factory=list)
    chosen: dict|None=None
    status: str='Waiting'
    signature: tuple=()
    cached: bool=False
    alternate_queries: list=field(default_factory=list)
    organized_path: Path|None=None
    runtime_check: dict=field(default_factory=dict)
    @property
    def kind(self): return 'TV' if self.season is not None else 'Movie'
def parse(p):
    stem=re.sub(r'(?i)\{(?:tmdb|tvdb|imdb)(?:id)?[-=][^}]+\}',' ',p.stem)
    s=re.sub(r'\[([^]]*)\]',lambda match: '('+match[1]+')' if re.fullmatch(r'(?:19|20)\d{2}',match[1]) else ' ',stem.replace('_',' '))
    e=re.search(r'(?i)\bS(\d{1,2})E(\d{1,3})\b|\b(\d{1,2})x(\d{1,3})\b',s)
    unsupported=bool(re.search(r'(?i)E\d+[ ._-]*E\d|\d{4}[.-]\d{2}[.-]\d{2}|S\d+E\d+[- ]+(?:E)?\d+',s))
    title=s[:e.start()] if e else s
    years=list(re.finditer(r'(?<!\d)((?:19|20)\d{2})(?!\d)',title))
    y=next((v for v in reversed(years) if v.start()>0),None)
    year=y[1] if y else ''
    if y and y.start()>0: title=title[:y.start()]
    title=re.split(r'(?i)\b(?:2160p|1080p|720p|480p|bluray|brrip|webrip|web-dl|hdtv|x264|x265|remux|dvdrip)\b',title.replace('.',' '))[0]
    alternates=[v.strip() for v in re.findall(r'\(([^()]*)\)',title) if len(v.split())>=2 and not re.search(r'(?i)\b(edition|extended|cut|version|dubbed|1080p|2160p|720p)\b',v)]
    title=re.sub(r'\[[^]]*\]|\([^)]*\)','',title).strip(' -_.()[]{}') or p.parent.name
    title=re.sub(r'^0[1-9]\s+|^\d{1,3}[.)_-]\s*','',title)
    title=re.sub(r'(?i)\s+-\s+(?:DUAL|MULTI)(?:\s.*)?$','',title).strip()
    st=p.stat()
    return Media(p,title,year,int(e[1] or e[3]) if e else None,int(e[2] or e[4]) if e else None,status='Unsupported episode pattern' if unsupported else 'Waiting',signature=(st.st_size,st.st_mtime_ns),alternate_queries=alternates)
class History:
    """Persistent per-file decisions and completed-output manifests, separate from API cache."""
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.path=DATA/'history.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INTEGER, mtime INTEGER, payload TEXT, provider TEXT, saved REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS outputs (source TEXT, library TEXT, mode TEXT, inputs TEXT, targets TEXT, PRIMARY KEY(source,library,mode))')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path, timeout=15)
        try:
            with db: yield db
        finally: db.close()
    @staticmethod
    def key(path): return os.path.normcase(str(Path(path).resolve()))
    @staticmethod
    def provider(m): return 'TVmaze' if m.kind=='TV' else 'TMDB'
    @staticmethod
    def snapshot(paths):
        return [(History.key(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths]
    def save(self,m,path=None):
        if not (m.chosen or m.status in {'Choose match','No match','Episode needs review','Skipped by you',REJECTED,REJECT_MOVED} or m.status.startswith('Unsupported')): return
        path=Path(path or m.source)
        st=path.stat()
        # Do not attach a decision to a file changed while its lookup was running.
        if path==m.source and (st.st_size,st.st_mtime_ns)!=m.signature: return False
        payload={k:getattr(m,k) for k in ('query','year','season','episode','candidates','chosen','status','alternate_queries','runtime_check')}
        if m.chosen: payload['status']='Ready'
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)',(self.key(path),st.st_size,st.st_mtime_ns,json.dumps(payload),self.provider(m),time.time()))
        return True
    def restore(self,m,library=None,mode='copy',options=None):
        with self.connect() as db:
            row=db.execute('SELECT size,mtime,payload,provider,saved FROM files WHERE path=?',(self.key(m.source),)).fetchone()
        if not row or tuple(row[:2])!=m.signature: return False
        data=json.loads(row[2])
        permanent=bool(data['chosen']) or data['status'] in {'Skipped by you', REJECTED, REJECT_MOVED}
        if not permanent and (row[3]!=self.provider(m) or time.time()-row[4]>86400): return False
        for key,value in data.items(): setattr(m,key,value)
        m.cached=True
        if m.chosen and library:
            if self.key(m.source)==self.key(destination(m,library,options)): m.status='Already organized'
            elif self.processed(m,library,mode,options): m.status='Previously copied' if mode=='copy' else 'Previously moved'
        return True
    @staticmethod
    def operation_mode(m,mode,options):
        options=options or SortOptions()
        layout=options.movie_layout if m.kind=='Movie' else options.show_layout
        default='title' if m.kind=='Movie' else 'season'
        key=mode if layout==default else mode+':'+m.kind+':'+layout
        if metadata_tag(m,options.id_style): key+=':ids:'+options.id_style
        if not options.rename_files: key+=':original-names'
        return key
    def completed(self,m,library,mode,inputs,pairs,options=None):
        targets=self.snapshot([dst for src,dst in pairs])
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO outputs VALUES (?,?,?,?,?)',(self.key(m.source),self.key(library),self.operation_mode(m,mode,options),json.dumps(inputs),json.dumps(targets)))
        # Keep both original and organized paths identifiable, including after restart/undo.
        if m.source.exists(): self.save(m)
        self.save(m,path=pairs[0][1])
    def processed(self,m,library,mode,options=None):
        with self.connect() as db:
            row=db.execute('SELECT inputs,targets FROM outputs WHERE source=? AND library=? AND mode=?',(self.key(m.source),self.key(library),self.operation_mode(m,mode,options))).fetchone()
        if not row: return False
        try:
            pairs=companions(m,destination(m,library,options),include_assets=(options or SortOptions()).rename_files)
            inputs=self.snapshot([src for src,dst in pairs])
            targets=json.loads(row[1])
            if [self.key(dst) for src,dst in pairs] != [t[0] for t in targets]: return False
            return json.loads(json.dumps(inputs))==json.loads(row[0]) and json.loads(json.dumps(self.snapshot([Path(t[0]) for t in targets])))==targets
        except OSError: return False

    def clear(self):
        with self.connect() as db:
            db.execute('DELETE FROM files')
            db.execute('DELETE FROM outputs')
    def forget(self,paths):
        # Invalidate original/organized aliases together without touching unrelated media.
        keys={self.key(p) for p in paths}
        with self.connect() as db:
            rows=db.execute('SELECT source,targets FROM outputs').fetchall()
            changed=True
            while changed:
                changed=False
                for source,targets_json in rows:
                    targets=json.loads(targets_json)
                    aliases={source}
                    if targets: aliases.add(targets[0][0])
                    if keys & aliases and not aliases <= keys:
                        keys.update(aliases); changed=True
            db.executemany('DELETE FROM files WHERE path=?',[(k,) for k in keys])
            db.executemany('DELETE FROM outputs WHERE source=?',[(k,) for k in keys])

class DatabaseSetupRequired(RuntimeError):
    pass

class RequestLimiter:
    def __init__(self):
        self.lock=threading.Lock()
        self.next_at={}; self.cooldown={}; self.blocked={}
    def acquire(self,host):
        interval=.04 if host=='api.themoviedb.org' else .51
        while True:
            with self.lock:
                if host in self.blocked: raise DatabaseSetupRequired(self.blocked[host])
                now=time.monotonic()
                delay=max(self.next_at.get(host,0),self.cooldown.get(host,0))-now
                if delay<=0:
                    self.next_at[host]=now+interval
                    return
            time.sleep(min(delay,1.0))
    def backoff(self,host,seconds):
        with self.lock:
            self.cooldown[host]=max(self.cooldown.get(host,0),time.monotonic()+seconds)
    def block(self,host,message):
        with self.lock: self.blocked[host]=message
    @staticmethod
    def retry_after(value,default):
        try:
            seconds=float(value)
            if math.isfinite(seconds): return max(0,seconds)
        except (ValueError,TypeError): pass
        try: return max(0,parsedate_to_datetime(value).timestamp()-time.time())
        except (ValueError,TypeError,OverflowError): return default

class Catalog:
    def __init__(self):
        self.memory={}; self.lock=threading.RLock(); self.inflight={}
        self.local=threading.local(); self.limiter=RequestLimiter()
    @property
    def _fresh(self): return getattr(self.local,'fresh',False)
    @_fresh.setter
    def _fresh(self,value): self.local.fresh=value
    @contextmanager
    def fresh(self):
        previous=self._fresh
        self._fresh=True
        try: yield
        finally: self._fresh=previous
    def clear_cache(self):
        with self.lock: self.memory.clear()
        folder=DATA/'cache'
        if folder.is_dir():
            for p in folder.iterdir():
                if re.fullmatch(r'[0-9a-f]{64}\.json',p.name) and p.is_file() and not p.is_symlink(): p.unlink()
    def reidentify(self,m,history=None,forget=True):
        history=history or History()
        if forget: history.forget([m.source])
        fresh=parse(m.source)
        for name in ('query','year','season','episode','candidates','chosen','status','signature','cached','alternate_queries'):
            setattr(m,name,getattr(fresh,name))
        try:
            with self.fresh(): self.identify(m)
            history.save(m)
        except Exception as exc:
            m.chosen=None; m.status='Lookup failed: '+str(exc)
            raise
    def get(self,url):
        key=(url,self._fresh)
        with self.lock:
            if not self._fresh and url in self.memory: return self.memory[url]
            future=self.inflight.get(key)
            owner=future is None
            if owner:
                future=Future(); self.inflight[key]=future
        if not owner: return future.result()
        try:
            result=self.fetch(url)
            with self.lock: self.memory[url]=result
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self.lock: self.inflight.pop(key,None)
    def fetch(self,url):
        cache=DATA/'cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if not self._fresh and cache.exists():
            try:
                if time.time()-cache.stat().st_mtime<604800:
                    return json.loads(cache.read_text(encoding='utf-8'))
            except (OSError,ValueError): pass
        host=urllib.parse.urlsplit(url).netloc
        for attempt in range(3):
            self.limiter.acquire(host)
            try:
                headers={'User-Agent':'Sortrr/1.1'}
                if host=='api.themoviedb.org': headers['Authorization']='Bearer '+os.environ.get('SORTRR_TMDB_TOKEN','')
                req=urllib.request.Request(url,headers=headers)
                with urllib.request.urlopen(req,timeout=20) as response: result=json.load(response)
                break
            except urllib.error.HTTPError as ex:
                try:
                    if ex.code in {401,403} and host=='api.themoviedb.org':
                        message='TMDb rejected the saved token. Update it in Movie database.'
                        self.limiter.block(host,message)
                        raise DatabaseSetupRequired(message) from ex
                    if ex.code==429:
                        delay=self.limiter.retry_after(ex.headers.get('Retry-After') if ex.headers else None,5*(attempt+1))
                        self.limiter.backoff(host,delay)
                        if attempt<2: continue
                    raise
                finally:
                    ex.close()
        # Atomic replacement prevents partial JSON from being visible to other readers.
        temporary=None
        try:
            cache.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=cache.parent,suffix='.tmp',delete=False) as out:
                temporary=Path(out.name); json.dump(result,out)
            os.replace(temporary,cache)
        except OSError:
            pass  # A cache-write failure must not discard a successful lookup.
        finally:
            if temporary: temporary.unlink(missing_ok=True)
        return result
    def search(self,m):
        if m.kind=='TV':
            rows=self.get('https://api.tvmaze.com/search/shows?'+urllib.parse.urlencode({'q':m.query}))
            cs=[{'title':r['show']['name'],'year':(r['show'].get('premiered') or '')[:4],'id':r['show']['id'],'provider':'TVmaze','external_ids':r['show'].get('externals') or {}} for r in rows]
        else:
            if not os.environ.get('SORTRR_TMDB_TOKEN','').strip():
                raise DatabaseSetupRequired('Connect TMDb using Movie database before identifying movies.')
            rows=[]
            queries=[m.query]+m.alternate_queries
            if re.match(r'^\d{3} to ',m.query,re.I): queries.append(m.query[0]+':'+m.query[1:])
            for query in dict.fromkeys(queries):
                rows=self.get('https://api.themoviedb.org/3/search/movie?'+urllib.parse.urlencode({'query':query,'include_adult':'false'}))['results']
                if rows: break
            cs=[{'title':r['title'],'year':r.get('release_date','')[:4],'id':r['id'],'provider':'TMDB','aliases':[r.get('original_title',r['title'])],'overview':r.get('overview',''),'release_date':r.get('release_date',''),'vote_average':r.get('vote_average'),'vote_count':r.get('vote_count'),'original_title':r.get('original_title','')} for r in rows]
        unique={}
        for c in cs:
            names=[c['title']]+c.get('aliases',[])
            c['score']=max(SequenceMatcher(None,norm(query),norm(name)).ratio() for name in names for query in [m.query]+m.alternate_queries)-(.3 if m.year and m.year not in c.get('years',[c['year']]) else 0)
            unique.setdefault((norm(c['title']),c['year']),c)
        return sorted(unique.values(),key=lambda c:c['score'],reverse=True)
    def tmdb_image_url(self, path, size_key, preferred_sizes):
        if not isinstance(path, str) or not re.fullmatch(r'/[A-Za-z0-9._-]+\.(?:jpg|jpeg|png|webp)', path, re.I):
            return ''
        images = self.get('https://api.themoviedb.org/3/configuration').get('images', {})
        base = images.get('secure_base_url', 'https://image.tmdb.org/t/p/')
        if base != 'https://image.tmdb.org/t/p/':
            return ''
        size = next((value for value in preferred_sizes if value in images.get(size_key, [])), None)
        return base + size + path if size else ''

    @staticmethod
    def tvmaze_image_url(image):
        url = (image or {}).get('medium') or ''
        parsed = urllib.parse.urlsplit(url)
        return url if parsed.scheme == 'https' and parsed.netloc == 'static.tvmaze.com' else ''

    def poster_url(self, details):
        provider = str(details.get('provider', '')).casefold()
        if provider == 'tmdb':
            return self.tmdb_image_url(details.get('poster_path'), 'poster_sizes', ('w185', 'w154', 'w342', 'w92'))
        if provider == 'tvmaze':
            return self.tvmaze_image_url(details.get('image'))
        return ''

    def episode_details(self, candidate, season, episode):
        identity = str(candidate.get('id', ''))
        if not re.fullmatch(r'[1-9]\d*', identity):
            raise ValueError('Invalid database entry ID')
        provider = candidate.get('provider', '').upper()
        if provider == 'TVMAZE':
            episodes = self.get(f'https://api.tvmaze.com/shows/{identity}/episodes?specials=1')
            return next((entry for entry in episodes if entry.get('season') == season and entry.get('number') == episode), {})
        if provider == 'TMDB':
            return self.get(f'https://api.themoviedb.org/3/tv/{identity}/season/{int(season)}/episode/{int(episode)}')
        return {}

    def entry_details(self,candidate,kind='Movie'):
        c=dict(candidate); provider=c.get('provider',''); identity=str(c.get('id',''))
        if not re.fullmatch(r'[1-9]\d*',identity): raise ValueError('Invalid database entry ID')
        if provider.upper()=='TMDB':
            namespace='tv' if kind=='TV' else 'movie'
            data=self.get(f'https://api.themoviedb.org/3/{namespace}/{identity}')
            return {**data,'provider':'TMDb','entry_url':f'https://www.themoviedb.org/{namespace}/{identity}'}
        if provider=='TVmaze':
            external=c.get('external_ids') or {}
            source,value=('tvdb_id',external.get('thetvdb')) if external.get('thetvdb') else ('imdb_id',external.get('imdb'))
            if value and os.environ.get('SORTRR_TMDB_TOKEN','').strip():
                valid=re.fullmatch(r'[1-9]\d*',str(value)) if source=='tvdb_id' else re.fullmatch(r'tt\d+',str(value))
                if valid:
                    found=self.get('https://api.themoviedb.org/3/find/'+str(value)+'?'+urllib.parse.urlencode({'external_source':source}))
                    matches=found.get('tv_results',[])
                    if len(matches)==1:
                        return self.entry_details({'provider':'TMDB','id':matches[0]['id']},'TV')
            data=self.get(f'https://api.tvmaze.com/shows/{identity}')
            return {**data,'provider':'TVmaze','entry_url':f'https://www.tvmaze.com/shows/{identity}'}
        return {**c,'provider':provider,'entry_url':''}
    def expected_runtime(self,candidate,kind='Movie',season=None,episode=None):
        """Return seconds for the exact movie or episode; never substitute a series average."""
        if candidate.get('provider') == 'Manual':
            return None
        identity=str(candidate.get('id',''))
        if not re.fullmatch(r'[1-9]\d*',identity): raise ValueError('Invalid database entry ID')
        if kind == 'TV':
            if season is None or episode is None:
                return None
            data = self.episode_details(candidate, season, episode)
        else:
            data = self.entry_details(candidate, kind)
        value=data.get('runtime')
        return float(value)*60 if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0 else None
    def identify(self,m):
        if m.status.startswith('Unsupported'): return
        m.candidates=self.search(m); cs=m.candidates
        if cs and cs[0]['score']>=.97 and (len(cs)==1 or cs[0]['score']-cs[1]['score']>=.12):
            if m.kind=='TV':
                es=self.get(f"https://api.tvmaze.com/shows/{cs[0]['id']}/episodes?specials=1")
                if not any(e['season']==m.season and e['number']==m.episode for e in es): m.status='Episode needs review'; return
            m.chosen=cs[0]; m.status='Ready'
        else: m.status='Choose match' if cs else 'No match'
IDENTIFICATION_WORKERS=12

def identify_batch(jobs,catalog,history=None,library=None,mode='copy',reidentify=False,report=lambda i,m:None,workers=IDENTIFICATION_WORKERS,options=None,finish_scan_on_setup=False):
    """Bounded streaming jobs, with an option to keep discovering files for manual review."""
    if workers<1: raise ValueError('At least one worker is required')
    history=history or History()
    if reidentify:
        jobs=list(jobs)
        history.forget([m.source for i,m in jobs])
    stop=threading.Event(); lock=threading.Lock()
    summary={'completed':0,'errors':0,'remembered':0,'setup':None}
    def identify_one(index,m):
        error=0
        try:
            if not reidentify and (finish_scan_on_setup or not stop.is_set()) and history.restore(m,library,mode,options):
                return 0, 1
            if stop.is_set() and (not finish_scan_on_setup or m.kind == 'Movie'):
                if not m.status.startswith('Unsupported'):
                    m.status = 'Connect TMDb' if finish_scan_on_setup else 'Not identified'
            elif reidentify:
                catalog.reidentify(m,history,forget=False)
            else:
                catalog.identify(m)
                history.save(m)
        except DatabaseSetupRequired as exc:
            m.chosen=None; m.status='Connect TMDb'; stop.set()
            with lock:
                if summary['setup'] is None: summary['setup']=str(exc)
        except Exception as exc:
            m.chosen=None; m.status='Lookup failed: '+str(exc); error=1
        finally:
            report(index,m)
        return error,int(m.cached)
    iterator=iter(jobs); pending=set(); exhausted=False
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='sortrr-identify') as pool:
        while pending or (not exhausted and (finish_scan_on_setup or not stop.is_set())):
            while not exhausted and (finish_scan_on_setup or not stop.is_set()) and len(pending)<workers*2:
                try: index,m=next(iterator)
                except StopIteration: exhausted=True; break
                pending.add(pool.submit(identify_one,index,m))
            if not pending: break
            done,pending=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                error,cached=future.result()
                summary['completed']+=1; summary['errors']+=error; summary['remembered']+=cached
    if reidentify and stop.is_set():
        for index,m in jobs:
            if m.status=='Re-identifying':
                m.status='Not identified'; report(index,m)
    return summary

MOVIE_LAYOUTS={'Title (Year)':'title','Year / Title (Year)':'year','A-Z / Title (Year)':'letter','Year - Title':'year_first'}
SHOW_LAYOUTS={'Show / Season / Episode':'season','Show / Episode (no season folders)':'flat'}

@dataclass(frozen=True)
class SortOptions:
    movie_layout: str='title'
    show_layout: str='season'
    id_style: str='none'
    rename_files: bool=True
    def __post_init__(self):
        if not isinstance(self.rename_files,bool): raise ValueError('Invalid rename option')
        if self.movie_layout not in MOVIE_LAYOUTS.values() or self.show_layout not in SHOW_LAYOUTS.values() or self.id_style not in ('none','plex','jellyfin','emby'):
            raise ValueError('Unknown folder layout')
    def to_dict(self): return {'movie_layout':self.movie_layout,'show_layout':self.show_layout,'id_style':self.id_style,'rename_files':self.rename_files}

ID_STYLES={'No database IDs':'none','Plex IDs':'plex','Jellyfin IDs':'jellyfin','Emby IDs':'emby'}

@dataclass(frozen=True)
class LayoutPreset:
    options: SortOptions
    description: str
    docs: tuple

PLEX_DOCS=(('Plex movies','https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/'),('Plex TV','https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/'))
JELLYFIN_DOCS=(('Jellyfin movies','https://jellyfin.org/docs/general/server/media/movies/'),('Jellyfin TV','https://jellyfin.org/docs/general/server/media/shows/'))
EMBY_DOCS=(('Emby movies','https://emby.media/support/articles/Movie-Naming.html'),('Emby TV','https://emby.media/support/articles/TV-Naming.html'))
LAYOUT_PRESETS={
    'Universal (all three servers)':LayoutPreset(SortOptions(),'Shared movie and season-folder structure for all three servers, without provider ID tags.',PLEX_DOCS+JELLYFIN_DOCS+EMBY_DOCS),
    'Plex (recommended)':LayoutPreset(SortOptions(id_style='plex'),'Individual movie folders and show/season folders. Adds available provider IDs using Plex syntax.',PLEX_DOCS),
    'Jellyfin (recommended)':LayoutPreset(SortOptions(id_style='jellyfin'),'Matching movie folder/file names and zero-padded season folders. Adds available provider IDs using Jellyfin syntax.',JELLYFIN_DOCS),
    'Emby (recommended)':LayoutPreset(SortOptions(id_style='emby'),'Individual movie folders and show/season folders. Adds available provider IDs using Emby syntax.',EMBY_DOCS),
}

def preset_name(options):
    return next((name for name,preset in LAYOUT_PRESETS.items() if preset.options==options),'Custom')

def provider_identifier(m):
    c=m.chosen or {}
    def numeric(value):
        text=str(value)
        return text if re.fullmatch(r'[1-9]\d*',text) else None
    if c.get('provider','').upper()=='TMDB':
        value=numeric(c.get('id'))
        if value: return 'tmdb',value
    if m.kind=='TV' and c.get('provider')=='TVmaze':
        # TVmaze's own numeric show ID is not a TVDB or TMDb ID.
        external=c.get('external_ids') or {}
        value=numeric(external.get('thetvdb'))
        if value: return 'tvdb',value
        value=external.get('imdb','')
        if isinstance(value,str) and re.fullmatch(r'tt\d+',value): return 'imdb',value
    return None

def metadata_tag(m,style):
    identifier=provider_identifier(m)
    if style=='none' or identifier is None: return ''
    source,value=identifier
    if style=='plex': return ' {'+source+'-'+value+'}'
    if style=='jellyfin': return ' ['+source+'id-'+value+']'
    if style=='emby': return ' ['+source+'id='+value+']'
    raise ValueError('Unknown ID style')

def tagged_name(base,tag):
    # Keep the entire identifier when shortening an unusually long title.
    return base[:max(1,140-len(tag))].rstrip(' .')+tag

def destination(m,library,options=None):
    options=options or SortOptions()
    c=m.chosen
    if not c: raise ValueError('Choose a match before organizing')
    title=clean(c['title']); year=str(c.get('year',''))
    name=title+(f" ({year})" if year else '')
    name=clean(name)
    tagged=tagged_name(name,metadata_tag(m,options.id_style))
    if m.kind=='TV':
        folder=Path(library)/'TV Shows'/tagged
        if options.show_layout=='season': folder/=f'Season {m.season:02d}'
        return folder/(f'{name} - S{m.season:02d}E{m.episode:02d}{m.source.suffix.lower()}' if options.rename_files else m.source.name)
    folder=Path(library)/'Movies'
    if options.movie_layout=='year': folder/=year if re.fullmatch(r'\d{4}',year) else 'Unknown Year'
    elif options.movie_layout=='letter':
        initial=norm(title)[:1].upper()
        folder/=initial if initial and 'A'<=initial<='Z' else '#'
    if options.movie_layout=='year_first': folder/=tagged_name(clean((year+' - ' if year else '')+title),metadata_tag(m,options.id_style))
    else: folder/=tagged
    return folder/(tagged+m.source.suffix.lower() if options.rename_files else m.source.name)

VIEW_SORT_FIELDS={'Source name':'file','Title':'match','Type':'kind','Year':'year','Season':'season','Episode':'episode','Status':'status'}

def sorted_media_indices(items,field='file',descending=False,media_filter='All media'):
    if field not in VIEW_SORT_FIELDS.values(): raise ValueError('Unknown sort field')
    def value(m):
        if field=='file': return m.source.name.casefold()
        if field=='match': return (m.chosen['title'] if m.chosen else m.query).casefold()
        if field=='kind': return m.kind
        if field=='year':
            year=str(m.chosen.get('year','') if m.chosen else m.year)
            return int(year) if re.fullmatch(r'\d{4}',year) else None
        if field=='season': return m.season
        if field=='episode': return m.episode
        return m.status.casefold()
    known=[]; unknown=[]
    for i,m in enumerate(items):
        if media_filter=='Movies' and m.kind!='Movie': continue
        if media_filter=='TV shows' and m.kind!='TV': continue
        v=value(m)
        if v is None: unknown.append(i)
        else: known.append((v,m.source.name.casefold(),i))
    # Numeric seasons/episodes sort numerically; missing values always go last.
    return [i for v,name,i in sorted(known,reverse=descending)]+unknown

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4194304),b''): h.update(b)
    return h.hexdigest()
def companions(m,target,include_assets=False):
    pairs=[(m.source,target)]
    extensions={'.srt','.ass','.ssa','.vtt','.sub','.idx'}
    if include_assets: extensions.update({'.nfo','.jpg','.jpeg','.png','.webp','.tbn'})
    images={'.jpg','.jpeg','.png','.webp','.tbn'}
    for p in sorted(m.source.parent.iterdir()):
        if not p.is_file() or is_link(p) or p.suffix.lower() not in extensions: continue
        match=p.stem==m.source.stem or p.name.startswith(m.source.stem+'.')
        if include_assets and p.suffix.lower() in images and p.stem.startswith(m.source.stem+'-'):
            match=bool(re.fullmatch(r'(poster|fanart|backdrop|cover|thumb|banner|clearart|logo|clearlogo|landscape|discart)\d*',p.stem[len(m.source.stem)+1:].casefold()))
        if match:
            suffix=p.name[len(m.source.stem):]
            pairs.append((p,target.with_name(target.stem+suffix)))
    return pairs

def move_no_replace(src, dst):
    # Windows rename fails if the destination exists. Never use os.replace.
    if os.name == 'nt':
        os.rename(src, dst)
    else:
        os.link(src, dst)
        src.unlink()

def organize(items,library,report=lambda s:None,mode='copy',options=None,journal=None):
    options=options or SortOptions()
    if mode=='rename': options=replace(options,rename_files=True)
    if mode not in {'copy', 'move', 'rename'}: raise ValueError('Unknown organization mode')
    history=History()
    DATA.mkdir(exist_ok=True); shared=journal is not None
    journal=Path(journal) if shared else DATA/f'run-{time.time_ns()}.jsonl'; count=0
    with journal.open('a' if shared else 'x',encoding='utf-8') as log:
        for m in items:
            if not m.chosen or m.status!='Ready': continue
            try:
                st=m.source.stat()
                if (st.st_size,st.st_mtime_ns)!=m.signature: raise ValueError('Source changed; scan again')
                target = destination(m,library,options)
                if mode=='rename':
                    source_boundary(m.source,m.source.parent.resolve())
                    target=m.source.with_name(target.name)
                if m.source.resolve() == target.resolve():
                    m.organized_path=target
                    m.status = 'Already organized'
                    report(m.status)
                    continue
                pairs=companions(m,target,include_assets=mode=='rename' or bool(options and options.rename_files))
                for src,dst in pairs:
                    if src.is_symlink(): raise ValueError('Symbolic links skipped')
                    if dst.exists() or dst.is_symlink(): raise FileExistsError('Destination already exists')
                    if not dst.resolve().is_relative_to(m.source.parent.resolve() if mode=='rename' else Path(library).resolve()): raise ValueError('Unsafe destination')
                inputs=history.snapshot([src for src,dst in pairs])
                history.save(m)
                for src,dst in pairs:
                    dst.parent.mkdir(parents=True,exist_ok=True)
                    rec={'source':str(src.resolve()),'target':str(dst.resolve()),'event':'intent','mode':mode}
                    if mode=='rename': rec['root']=str(m.source.parent.resolve())
                    if mode in {'move','rename'}:
                        before = src.stat()
                        checksum = digest(src)
                        after = src.stat()
                        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                            raise ValueError('Source changed during verification')
                        rec['sha256'] = checksum
                        log.write(json.dumps(rec)+'\n'); log.flush(); os.fsync(log.fileno())
                        move_no_replace(src, dst)
                        log.write(json.dumps({**rec, 'event':'complete'})+'\n'); log.flush(); os.fsync(log.fileno())
                        continue
                    log.write(json.dumps(rec)+'\n'); log.flush(); os.fsync(log.fileno())
                    created=False
                    try:
                        with dst.open('xb') as out:
                            created=True
                            with src.open('rb') as inp: shutil.copyfileobj(inp,out,4194304)
                            out.flush(); os.fsync(out.fileno())
                        checksum=digest(dst)
                        if checksum!=digest(src): raise IOError('Copy verification failed')
                        shutil.copystat(src,dst)
                        log.write(json.dumps({**rec,'event':'complete','sha256':checksum})+'\n'); log.flush(); os.fsync(log.fileno())
                    except Exception:
                        if created: dst.unlink(missing_ok=True)
                        raise
                history.completed(m,library,mode,inputs,pairs,options)
                m.organized_path=target
                m.status='Renamed' if mode=='rename' else ('Moved' if mode=='move' else 'Copied'); count+=1
            except Exception as ex: m.status='Skipped: '+str(ex)
            report(m.status)
    return count,journal
def journal_records(journal):
    records=[]; lines=Path(journal).read_text(encoding='utf-8').splitlines()
    for index,line in enumerate(lines):
        if not line.strip(): continue
        try: records.append(json.loads(line))
        except json.JSONDecodeError:
            if index==len(lines)-1: break  # An interrupted final append is not a complete record.
            raise ValueError('Operation journal contains a corrupt record')
    return records

CHANGE_LABELS = {
    'copy': 'Copy', 'move': 'Move', 'rename': 'Rename', 'cleanup': 'Archive',
    'reject': 'Move reject', 'rmdir': 'Remove folder', 'recycle': 'Recycle',
}


@dataclass(frozen=True)
class FileChange:
    index: int
    record: dict
    reverted: bool

    @property
    def paths(self):
        keys = {os.path.normcase(self.record['target'])}
        if self.record['mode'] != 'copy':
            keys.add(os.path.normcase(self.record['source']))
        return keys

    @property
    def reversible(self):
        return not self.reverted and self.record['mode'] != 'recycle'


def read_file_changes(journal):
    """Pair old intent and completion records without changing their on-disk format."""
    entries = {}
    pending = {}
    reverted = set()
    for index, record in enumerate(journal_records(journal)):
        event = record.get('event')
        if event == 'reverted':
            reverted.add(record['change'])
        elif event in {'intent', 'complete'} and record.get('mode') in CHANGE_LABELS:
            key = record['mode'], record['source'], record['target']
            if event == 'intent':
                pending[key] = index
            else:
                index = pending.pop(key, index)
            entries[index] = record
    return [
        FileChange(index, record, index in reverted)
        for index, record in entries.items()
        if record['event'] == 'complete' or record['mode'] not in {'copy', 'recycle'}
    ]


def change_journals():
    return sorted(
        (p for p in DATA.glob('run-*.jsonl') if re.fullmatch(r'run-[0-9]{1,19}\.jsonl', p.name) and not is_link(p)),
        key=lambda p: int(p.stem[4:]), reverse=True,
    )


def write_record(log, record):
    log.write(json.dumps(record) + '\n')
    log.flush()
    os.fsync(log.fileno())


def change_restore_paths(record):
    mode = record['mode']
    original = Path(record['source'])
    target = Path(record['target'])
    root = record.get('reject_root') if mode == 'reject' else record.get('root')
    source_boundary(target, Path(root or target.anchor))
    if mode != 'copy':
        source_boundary(original, Path(record.get('root') or original.anchor))
    return original, target


def verify_change_file(path, expected):
    if not path.is_file():
        raise ValueError(f'Recorded file is missing or is no longer a file: {path}')
    before = path.stat()
    checksum = digest(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or checksum != expected:
        raise ValueError(f'The file changed since Sortrr recorded it: {path}')
    return checksum


def restore_file_change(record):
    mode = record['mode']
    original, target = change_restore_paths(record)
    if mode != 'copy' and original.exists():
        raise ValueError(f'Original path is already occupied: {original}')
    if mode == 'rmdir':
        original.mkdir(parents=True, exist_ok=False)
        return
    checksum = verify_change_file(target, record.get('sha256'))
    if mode == 'copy':
        target.unlink()
    else:
        original.parent.mkdir(parents=True, exist_ok=True)
        if mode == 'reject':
            move_reject_file(target, original, checksum)
        else:
            move_no_replace(target, original)


def repair_journal_tail(journal):
    # Repair a torn final append before adding new records so earlier IDs remain stable.
    with journal.open('r+b') as raw:
        data = raw.read()
        if data and not data.endswith(b'\n'):
            tail = data.rsplit(b'\n', 1)[-1]
            try:
                json.loads(tail)
            except (ValueError, UnicodeError):
                raw.truncate(len(data) - len(tail))
            else:
                raw.write(b'\n')


def revert_file_changes(journal, selected=None):
    """Restore a run or selected entries, protecting paths claimed by newer changes."""
    journal = Path(journal)
    changes = read_file_changes(journal)
    selected = None if selected is None else set(selected)
    protected = set()
    for newer in change_journals():
        if int(newer.stem[4:]) <= int(journal.stem[4:]):
            break
        for change in read_file_changes(newer):
            if change.reversible:
                protected.update(change.paths)

    restored = 0
    skipped = {}
    if not any(change.reversible and (selected is None or change.index in selected) for change in changes):
        return restored, skipped

    repair_journal_tail(journal)
    with journal.open('a', encoding='utf-8') as log:
        for change in reversed(changes):
            if not change.reversible:
                continue
            if selected is not None and change.index not in selected:
                protected.update(change.paths)
                continue
            try:
                if protected.intersection(change.paths):
                    raise ValueError('Revert the newer change affecting this path first.')
                restore_file_change(change.record)
            except (OSError, ValueError) as exc:
                skipped[change.index] = str(exc)
                protected.update(change.paths)
            else:
                write_record(log, {'event': 'reverted', 'change': change.index})
                restored += 1
    return restored, skipped



@dataclass
class FileTrail:
    steps: list
    unavailable: str = ''
    aliases: set = field(default_factory=set)

    @property
    def key(self):
        journal, change = self.steps[0]
        return journal, change.index

    @property
    def original(self):
        return self.steps[0][1].record['source']

    @property
    def current(self):
        return self.steps[-1][1].record['target']

    @property
    def can_restore(self):
        return not self.unavailable and all(change.reversible for _, change in self.steps)


def file_trails(runs):
    """Follow recorded occupants in time order. A copy starts a separate branch."""
    trails = []
    occupants = {}
    for journal, changes in reversed(list(runs.items())):
        for change in changes:
            record = change.record
            mode = record['mode']
            if mode == 'rmdir':
                continue
            source = os.path.normcase(record['source'])
            target = os.path.normcase(record['target'])
            if change.reverted:
                prior = occupants.get(source)
                if mode != 'copy' and prior and record.get('sha256') == prior.steps[-1][1].record.get('sha256'):
                    prior.aliases.add(record['target'])
                trails.append(FileTrail([(journal, change)], 'Reverted', {record['source'], record['target']}))
                continue
            trail = occupants.pop(source, None) if mode != 'copy' else None
            if trail and mode != 'recycle' and record.get('sha256') != trail.steps[-1][1].record.get('sha256'):
                trail.unavailable = 'A later change recorded different file contents.'
                trail = None
            if trail is None:
                trail = FileTrail([])
                trails.append(trail)
            trail.steps.append((journal, change))
            trail.aliases.update((record['source'], record['target']))
            if mode == 'recycle':
                trail.unavailable = 'Restore in Windows Recycle Bin'
                continue
            replaced = occupants.get(target)
            if replaced:
                replaced.unavailable = 'A later operation reused this path.'
            occupants[target] = trail
    return trails


def verify_copy_original(record):
    original = Path(record['source'])
    source_boundary(original, Path(original.anchor))
    try:
        verify_change_file(original, record['sha256'])
    except (OSError, ValueError) as exc:
        raise ValueError('The original copy source must be present and unchanged before Sortrr can remove its copy.') from exc


def preflight_original_restore(trail, runs):
    selected = {(journal, change.index) for journal, change in trail.steps}
    protected = set()
    for journal, changes in runs.items():
        for change in reversed(changes):
            if not change.reversible:
                continue
            key = journal, change.index
            if key in selected:
                if protected.intersection(change.paths):
                    raise ValueError('A different newer change affects one of these paths. Review it before restoring this file.')
                selected.remove(key)
            else:
                protected.update(change.paths)
        if not selected:
            break

    # Simulate the reverse sequence so a known path conflict leaves every file in place.
    occupied = {}
    for _, change in reversed(trail.steps):
        record = change.record
        original, target = change_restore_paths(record)
        target_key = os.path.normcase(str(target))
        if not occupied.get(target_key, target.is_file()):
            raise ValueError(f'Recorded file is missing or is no longer a file: {target}')
        occupied[target_key] = False
        if record['mode'] != 'copy':
            original_key = os.path.normcase(str(original))
            if occupied.get(original_key, original.exists()):
                raise ValueError(f'Restore path is already occupied: {original}')
            occupied[original_key] = True
    first = trail.steps[0][1].record
    if first['mode'] == 'copy':
        verify_copy_original(first)


def restore_original_file(expected_steps):
    """Reverse one verified trail under the caller's file-operation lock."""
    runs = {path.name: read_file_changes(path) for path in change_journals()}
    expected_steps = tuple(expected_steps)
    if not expected_steps:
        raise ValueError('No file changes were selected.')
    trail = next((t for t in file_trails(runs) if t.key == expected_steps[0]), None)
    if not trail or not trail.can_restore or tuple((name, c.index) for name, c in trail.steps) != expected_steps:
        raise ValueError('This file history changed. Search again and review the updated paths.')
    preflight_original_restore(trail, runs)

    for name in dict.fromkeys(name for name, _ in trail.steps):
        repair_journal_tail(DATA / name)
    restored = 0
    try:
        for name, change in reversed(trail.steps):
            with (DATA / name).open('a', encoding='utf-8') as log:
                if change.record['mode'] == 'copy':
                    verify_copy_original(change.record)
                restore_file_change(change.record)
                write_record(log, {'event': 'reverted', 'change': change.index})
                restored += 1
    except (OSError, ValueError) as exc:
        if restored:
            raise ValueError(f'Reverted {restored} of {len(trail.steps)} changes before stopping. {exc}') from exc
        raise
    return trail

def undo(journal):
    return revert_file_changes(journal)[0]


@dataclass(frozen=True)
class RenameChange:
    source: Path
    target: Path
    error: str=''

def plan_renames(items,options=None):
    options=replace(options or SortOptions(),rename_files=True)
    changes=[]; targets=set()
    for m in items:
        if not m.chosen: continue
        try:
            st=m.source.stat()
            if (st.st_size,st.st_mtime_ns)!=m.signature: raise ValueError('Source changed; scan again')
            target=m.source.with_name(destination(m,m.source.parent,options).name)
            for src,dst in companions(m,target,include_assets=True):
                if src.resolve()==dst.resolve(): error='Already named correctly'
                elif is_link(src): error='Links are skipped'
                elif dst.exists() or dst.is_symlink() or History.key(dst) in targets: error='Destination already exists or conflicts'
                else: error=''
                targets.add(History.key(dst)); changes.append(RenameChange(src,dst,error))
        except (OSError,ValueError) as exc: changes.append(RenameChange(m.source,m.source,str(exc)))
    return changes

def is_link(path):
    path=Path(path)
    if path.is_symlink() or getattr(path,'is_junction',lambda:False)(): return True
    try: return bool(getattr(path.lstat(),'st_file_attributes',0) & 0x400)
    except FileNotFoundError: return False

def source_boundary(path,root):
    path=Path(path).absolute(); root=Path(root).absolute()
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes source folder')
    current=path
    while True:
        if is_link(current): raise ValueError('Links and junctions are skipped')
        if current==root: break
        current=current.parent
    return path

@dataclass(frozen=True)
class CleanupItem:
    path: Path
    category: str
    signature: tuple
    recommended: bool=False

@dataclass
class CleanupPlan:
    root: Path
    files: list
    contents: dict

CLEANUP_CATEGORIES={
    'System junk':'System-generated folder files',
    'Checksums':'Checksum and verification files',
    'Text and links':'Text documents and links (review first)',
    'Archives':'Archive files (review first)',
    'Metadata and artwork':'Metadata and artwork (review first)',
    'Samples':'Sample videos (review first)',
}

def cleanup_category(path):
    name=path.name.casefold(); suffix=path.suffix.casefold()
    if name in {'thumbs.db','desktop.ini','.ds_store'}: return 'System junk'
    if suffix in {'.sfv','.md5','.sha1','.sha256'}: return 'Checksums'
    if suffix in {'.txt','.url','.webloc'}: return 'Text and links'
    if suffix in {'.nfo','.jpg','.jpeg','.png','.webp','.tbn'}: return 'Metadata and artwork'
    if suffix in {'.zip','.rar','.7z','.tar','.gz'} or re.fullmatch(r'\.r\d{2}',suffix): return 'Archives'
    if suffix in VIDEO and (re.search(r'(?i)(?:^|[ ._-])sample(?:[ ._-]|$)',path.stem) or path.parent.name.casefold() in {'sample','samples'}): return 'Samples'
    return None

def plan_cleanup(source,excluded=()):
    source=Path(source)
    if is_link(source): raise ValueError('Choose a source folder that is not a link or junction')
    root=source.resolve()
    if not root.is_dir(): raise ValueError('Choose an existing source folder')
    protected=[Path(p).resolve() for p in excluded]+[ROOT.resolve(),DATA.resolve()]
    def protected_path(path):
        resolved=path.resolve()
        return any(resolved.is_relative_to(p) for p in protected)
    files=[]; contents={}
    if protected_path(root): return CleanupPlan(root,files,contents)
    def onerror(error): raise error
    for folder,dirs,names in os.walk(root,followlinks=False,onerror=onerror):
        parent=Path(folder)
        # Retain excluded children in the inventory so their parent cannot appear empty.
        entries=[parent/name for name in dirs+names]
        contents[parent]=tuple(entries)
        dirs[:]=[name for name in dirs if name.casefold()!='.sortrr-trash' and not is_link(parent/name) and not protected_path(parent/name)]
        for name in names:
            path=parent/name
            if is_link(path) or protected_path(path): continue
            category=cleanup_category(path)
            if category:
                st=path.stat()
                files.append(CleanupItem(path,category,(st.st_size,st.st_mtime_ns),category in {'System junk','Checksums'}))
    return CleanupPlan(root,files,contents)

def cleanup_empty_folders(plan,selected):
    selected={Path(p) for p in selected}; empty=set()
    for folder in sorted(plan.contents,key=lambda p:len(p.parts),reverse=True):
        if folder==plan.root: continue
        if all(p in selected or p in empty for p in plan.contents[folder]): empty.add(folder)
    return sorted(empty,key=lambda p:len(p.parts),reverse=True)

def apply_cleanup(plan,selected,remove_empty=True,report=lambda text:None,journal=None):
    known={item.path:item for item in plan.files}
    selected={Path(p) for p in selected}
    if not selected<=known.keys(): raise ValueError('Cleanup selection contains unreviewed paths')
    root=source_boundary(plan.root,plan.root)
    DATA.mkdir(parents=True,exist_ok=True)
    shared=journal is not None; run_id=str(time.time_ns())
    journal=Path(journal) if shared else DATA/('run-'+run_id+'.jsonl')
    vault=root/'.sortrr-trash'/run_id
    result={'files':0,'folders':0,'skipped':[]}
    with journal.open('a' if shared else 'x',encoding='utf-8') as log:
        def record(data):
            log.write(json.dumps(data)+'\n'); log.flush(); os.fsync(log.fileno())
        for src in sorted(selected):
            dst=vault/src.relative_to(root)
            try:
                source_boundary(src,root); source_boundary(dst,root)
                item=known[src]; st=src.stat()
                if (st.st_size,st.st_mtime_ns)!=item.signature: raise ValueError('Changed since preview')
                checksum=digest(src); after=src.stat()
                if (after.st_size,after.st_mtime_ns)!=item.signature: raise ValueError('Changed during verification')
                dst.parent.mkdir(parents=True,exist_ok=True)
                source_boundary(dst,root)
                rec={'source':str(src),'target':str(dst),'mode':'cleanup','event':'intent','sha256':checksum,'root':str(root)}
                record(rec); move_no_replace(src,dst); record({**rec,'event':'complete'})
                result['files']+=1
                report('Removed from source: '+src.name)
            except (OSError,ValueError) as exc:
                result['skipped'].append(str(src)+': '+str(exc))
                record({'source':str(src),'target':str(dst),'mode':'cleanup','event':'skip','reason':str(exc)})
        if remove_empty:
            for folder in cleanup_empty_folders(plan,selected):
                try:
                    source_boundary(folder,root)
                    if folder==root: continue
                    if any(folder.iterdir()): continue
                    rec={'source':str(folder),'target':str(folder),'mode':'rmdir','event':'intent','root':str(root)}
                    record(rec); folder.rmdir(); record({**rec,'event':'complete'}); result['folders']+=1
                except (OSError,ValueError) as exc:
                    result['skipped'].append(str(folder)+': '+str(exc))
        return result,journal


def move_reject_file(source, target, checksum):
    """Keep the source until a cross-volume copy has been verified."""
    try:
        move_no_replace(source, target)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, 'winerror', None) != 17:
            raise

    before = source.stat()
    created = False
    try:
        with target.open('xb') as out:
            created = True
            with source.open('rb') as inp:
                shutil.copyfileobj(inp, out, 4194304)
            out.flush()
            os.fsync(out.fileno())
        if digest(target) != checksum:
            raise OSError('Copy verification failed')
        shutil.copystat(source, target)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('File changed during the move')
        source.unlink()
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise


def dispose_rejects(items, source_root, reject_root, recycle, journal=None):
    """Apply the confirmed paths. Return results without changing the rows on this thread."""
    history = History()
    results = []
    for media, source, target in items:
        try:
            source_boundary(source, source_root)
            stat = source.stat()
            if not source.is_file() or (stat.st_size, stat.st_mtime_ns) != media.signature:
                raise ValueError('File changed since the scan')
            if target is None:
                recycle_log = journal or DATA / f'run-{time.time_ns()}.jsonl'
                record = {'source': str(source), 'target': str(source), 'mode': 'recycle'}
                with recycle_log.open('a' if journal else 'x', encoding='utf-8') as log:
                    write_record(log, {**record, 'event': 'intent'})
                    recycle(source)
                    journal = recycle_log
                    write_record(log, {**record, 'event': 'complete'})
            else:
                source_boundary(target, reject_root)
                if target.exists():
                    raise FileExistsError('Reject destination already exists')
                checksum = digest(source)
                stat = source.stat()
                if (stat.st_size, stat.st_mtime_ns) != media.signature:
                    raise ValueError('File changed during verification')
                target.parent.mkdir(parents=True, exist_ok=True)
                source_boundary(source, source_root)
                source_boundary(target, reject_root)
                if journal is None:
                    journal = DATA / f'run-{time.time_ns()}.jsonl'
                    journal.touch(exist_ok=False)
                record = {
                    'source': str(source), 'target': str(target), 'mode': 'reject',
                    'root': str(source_root), 'reject_root': str(reject_root), 'sha256': checksum,
                }
                with journal.open('a', encoding='utf-8') as log:
                    log.write(json.dumps({**record, 'event': 'intent'}) + '\n')
                    log.flush()
                    os.fsync(log.fileno())
                    move_reject_file(source, target, checksum)
                    write_record(log, {**record, 'event': 'complete'})
        except (OSError, ValueError) as exc:
            results.append((media, target, str(exc)))
            continue
        if target is not None:
            # Keep archived rejects out of subsequent plans, including after the folder preference changes.
            try:
                history.save(replace(media, status=REJECT_MOVED), path=target)
            except (OSError, sqlite3.Error):
                # The intent record still allows the completed move to be undone.
                pass
        results.append((media, target, ''))
    return results, journal


def sort_and_finish(items,library,source,mode='copy',options=None,auto_cleanup=False,report=lambda text:None):
    """Sort and then clean only directories whose media successfully completed this run."""
    options=options or SortOptions(); items=list(items)
    root=Path(source).resolve(); output=Path(library).resolve()
    original={id(m):m.source.resolve() for m in items}
    plan=None; warnings=[]
    if auto_cleanup:
        excluded=[output] if output!=root else [root/'Movies',root/'TV Shows']
        try: plan=plan_cleanup(root,excluded)
        except (OSError,ValueError) as exc: warnings.append('Cleanup preview failed: '+str(exc))
    DATA.mkdir(parents=True,exist_ok=True); journal=DATA/f'run-{time.time_ns()}.jsonl'
    journal.touch(exist_ok=False)
    count,_=organize(items,library,report,mode,options,journal=journal)
    cleanup={'files':0,'folders':0,'skipped':[]}
    if plan is not None:
        successful={original[id(m)] for m in items if m.status in {'Copied','Moved','Already organized'}}
        failed={original[id(m)].parent for m in items if m.status not in {'Copied','Moved','Already organized'}}
        eligible=set()
        for folder in {p.parent for p in successful}-failed:
            if folder not in plan.contents: continue
            # An unmatched/unselected media file keeps its shared source folder untouched.
            media=[p for p in plan.contents[folder] if p.suffix.lower() in VIDEO]
            if all(p in successful for p in media): eligible.add(folder)
        selected={i.path for i in plan.files if i.recommended and i.path.parent in eligible}
        scoped={root}
        for folder in eligible:
            scoped.add(folder)
            scoped.update(p for p in folder.parents if p.is_relative_to(root))
        limited=CleanupPlan(root,[i for i in plan.files if i.path in selected],{p:tuple(e for e in v if e.exists() or e.is_symlink()) for p,v in plan.contents.items() if p in scoped})
        try: cleanup,_=apply_cleanup(limited,selected,True,report,journal=journal)
        except (OSError,ValueError) as exc: warnings.append('Cleanup failed: '+str(exc))
    return {'sorted':count,'cleanup':cleanup,'warnings':warnings},journal

UNRESOLVED_STATUSES={'No match','Choose match','Episode needs review','Connect TMDb','Not identified'}
def unresolved_media(items):
    return [m for m in items if not m.chosen and (m.status in UNRESOLVED_STATUSES or m.status.startswith(('Lookup failed','Unsupported')))]

def build_manual_entry(media, title, year, kind, season=None, episode=None):
    """Build a local entry for the same naming rules as a database match."""
    if media.status.startswith('Unsupported'):
        raise ValueError('Correct the unsupported filename and scan again')
    title, year = title.strip(), year.strip()
    if not re.search(r'[^<>:"/\\|?*\x00-\x1f.\s]', title):
        raise ValueError('Enter the movie or show title.')
    if year and not re.fullmatch(r'[1-9][0-9]{3}', year):
        raise ValueError('Enter a four-digit year or leave it blank.')
    if kind not in {'Movie', 'TV'}:
        raise ValueError('Choose Movie or TV.')
    if kind == 'TV' and (season is None or episode is None or not 0 <= season <= 99 or not 1 <= episode <= 999):
        raise ValueError('Enter a season from 0 to 99 and an episode from 1 to 999.')
    return replace(media, query=title, year=year,
                   season=season if kind == 'TV' else None, episode=episode if kind == 'TV' else None,
                   chosen={'title': title, 'year': year, 'provider': 'Manual'})


def resolve_manually(m,candidate,query,year,season=None,episode=None,kind=None):
    """Persist a reviewed wizard choice, including corrected episode numbering."""
    if m.status.startswith('Unsupported'): raise ValueError('Correct the unsupported filename and scan again')
    kind=kind or m.kind
    if kind not in {'Movie','TV'}: raise ValueError('Choose Movie or TV')
    if kind=='TV':
        if season is None or episode is None or season<0 or episode<1: raise ValueError('Enter a valid season and episode')
    stat=m.source.stat()
    if (stat.st_size,stat.st_mtime_ns)!=m.signature: raise ValueError('File changed; scan again before matching')
    decision = replace(
        m, query=query.strip(), year=year.strip(), season=season if kind == 'TV' else None,
        episode=episode if kind == 'TV' else None, chosen=dict(candidate), candidates=[dict(candidate)],
        status='Ready', cached=False,
        runtime_check={} if candidate.get('provider') == 'Manual' else m.runtime_check,
    )
    if not History().save(decision):
        raise ValueError('File changed; scan again before matching')
    for field in ('query', 'year', 'season', 'episode', 'chosen', 'candidates', 'status', 'cached', 'runtime_check'):
        setattr(m, field, getattr(decision, field))



def entry_info_text(details):
    title=details.get('title') or details.get('name') or 'Untitled'
    original=details.get('original_title') or details.get('original_name')
    date=details.get('release_date') or details.get('first_air_date') or details.get('premiered') or details.get('year','')
    lines=[str(title)]
    if original and original!=title: lines.append('Original title: '+str(original))
    if date: lines.append('Released: '+str(date))
    runtime=details.get('runtime') or next(iter(details.get('episode_run_time') or []),None)
    if runtime: lines.append('Runtime: '+str(runtime)+' min')
    genres=[g.get('name','') if isinstance(g,dict) else str(g) for g in details.get('genres',[])]
    if genres: lines.append('Genres: '+', '.join(genres))
    rating=details.get('vote_average')
    if rating is None and isinstance(details.get('rating'),dict): rating=details['rating'].get('average')
    if rating is not None:
        text=f'Rating: {float(rating):.1f}/10'
        if details.get('vote_count') is not None: text+=f" ({details['vote_count']} votes)"
        lines.append(text)
    if details.get('tagline'): lines.extend(['',str(details['tagline'])])
    overview=details.get('overview') or details.get('summary')
    if overview: lines.extend(['',html.unescape(re.sub(r'<[^>]+>','',str(overview)))])
    return '\n'.join(lines)


def compare_runtime(local,expected,tolerance=5):
    """Five percent or two minutes accommodates rounded metadata and credits."""
    def valid(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0
    if not valid(local) or not valid(expected): return {'status':'Unknown','local':local,'expected':expected,'label':'Runtime unavailable'}
    delta=local-expected; limit=max(120,expected*max(0,min(50,tolerance))/100)
    status='Matches' if abs(delta)<=limit else 'Differs'
    return {'status':status,'local':local,'expected':expected,'delta':delta,'limit':limit,'label':f'{status}: {local/60:.1f} min / {expected/60:.0f} min database ({delta/60:+.1f} min)'}
