"""Qt Quick controller: UI changes are dispatched onto the GUI thread."""
import json,logging,os,urllib.request,hashlib,tempfile,re,sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import replace
from datetime import datetime
from PySide6.QtCore import QObject,Signal,Slot,Property,QAbstractListModel,QModelIndex,Qt,QSortFilterProxyModel,QUrl,QTimer,QLocale,QFile,QLockFile
from PySide6.QtGui import QDesktopServices,QGuiApplication,QImage
from PySide6.QtWidgets import QFileDialog
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QMediaMetaData,QAudioDevice,QMediaDevices
import core
from previews import PreviewManager,timestamp
log=logging.getLogger('sortrr')
class ArtworkCache:
    def __init__(self,path): self.path=Path(path)
    def poster(self,url):
        parsed=core.urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc not in {'image.tmdb.org','static.tvmaze.com'}: raise ValueError('Invalid artwork source')
        target=self.path/(hashlib.sha256(url.encode()).hexdigest()+'.png')
        if target.is_file() and not QImage(str(target)).isNull(): return target
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Sortrr/2.0'}),timeout=12) as response: raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024: raise ValueError('Artwork exceeds preview limit')
        image=QImage.fromData(raw)
        if image.isNull() or image.width()*image.height()>16000000: raise ValueError('Invalid artwork image')
        image=image.scaled(240,360,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self.path.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.path,suffix='.tmp',delete=False) as f: tmp=Path(f.name)
        try:
            if not image.save(str(tmp),'PNG'): raise ValueError('Artwork conversion failed')
            os.replace(tmp,target)
        finally: tmp.unlink(missing_ok=True)
        return target
    def clear(self):
        if self.path.exists():
            for p in self.path.iterdir():
                if re.fullmatch(r'[a-f0-9]{64}\.png',p.name) and not p.is_symlink(): p.unlink()
def runtime_key(candidate,kind,season,episode):
    return [str(candidate.get('provider','')).upper(),str(candidate.get('id','')),kind,season,episode]

def saved_runtime(m):
    return m.runtime_check if m.chosen and m.runtime_check.get('key')==runtime_key(m.chosen,m.kind,m.season,m.episode) else {}

class MediaModel(QAbstractListModel):
    names=['uid','mediaTitle','fileName','filePath','mediaKind','releaseYear','seasonText','episodeText','statusText','statusTone','thumbnail','isSelected','isRemembered','runtimeStatus','runtimeLabel']
    def __init__(self,c): super().__init__(c); self.c=c
    def roleNames(self): return {int(Qt.ItemDataRole.UserRole)+i+1:name.encode() for i,name in enumerate(self.names)}
    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.c.items)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.c.items): return None
        if role==Qt.ItemDataRole.DisplayRole: return self.c.items[index.row()].source.name
        position=int(role)-int(Qt.ItemDataRole.UserRole)-1
        return self.c.row(index.row()).get(self.names[position]) if 0<=position<len(self.names) else None
    def append(self,m):
        i=len(self.c.items); self.beginInsertRows(QModelIndex(),i,i); self.c.items.append(m); self.endInsertRows()
    def changed(self,uid):
        if 0<=uid<len(self.c.items): self.dataChanged.emit(self.index(uid),self.index(uid),list(self.roleNames()))
    def reset(self, items=None):
        self.beginResetModel()
        self.c.items = [] if items is None else items
        self.endResetModel()
class MediaProxy(QSortFilterProxyModel):
    def __init__(self,c):
        super().__init__(c); self.c=c; self.query=''; self.kind='All media'; self.review=False; self.ready_only=False; self.rejected_only=False; self.runtime='Any length'; self.field='file'; self.setDynamicSortFilter(True)
    def filterAcceptsRow(self,row,parent):
        m=self.c.items[row]
        if self.ready_only and m.status != 'Ready':
            return False
        if self.rejected_only and m.status != core.REJECTED:
            return False
        return (self.runtime=='Any length' or self.runtime==saved_runtime(m).get('status','Unchecked')) and (self.kind=='All media' or m.kind==('Movie' if self.kind=='Movies' else 'TV')) and (not self.review or bool(core.unresolved_media([m]))) and (not self.query or self.query in (m.source.name+' '+(m.chosen['title'] if m.chosen else m.query)).casefold())
    def lessThan(self,left,right):
        def key(index):
            m=self.c.items[index.row()]; title=m.chosen['title'] if m.chosen else m.query
            value={'file':m.source.name.casefold(),'match':title.casefold(),'kind':m.kind,'year':(m.chosen or {}).get('year',m.year),'season':m.season,'episode':m.episode,'status':m.status}.get(self.field)
            if self.field=='year': value=int(value) if str(value).isdigit() else None
            return value
        a,b=key(left),key(right)
        if a is None or b is None:
            if a is None and b is None: return left.row()<right.row()
            return a is not None if self.sortOrder()==Qt.SortOrder.AscendingOrder else a is None
        return a<b if a!=b else left.row()<right.row()
class Controller(QObject):
    invoke=Signal(object); stateChanged=Signal(); wizardChanged=Signal(); playbackChanged=Signal()
    darkModeChanged = Signal()
    changeHistoryChanged = Signal()
    audioOutputsChanged=Signal()
    progressResumed=Signal(str,str,str)
    scanStarted=Signal(); dialogRequested=Signal('QVariantMap'); toast=Signal(str); hoverReady=Signal(int,int,str,str)
    def __init__(self,parent=None):
        super().__init__(parent); self.invoke.connect(self.deliver,Qt.ConnectionType.QueuedConnection)
        self.items=[]; self.selected=set(); self.thumbs={}; self.thumb_requested=set(); self.busy=False; self.mutating=False; self.status='Choose a source folder to begin.'
        self.source=''; self.destination=''; self.reject_folder=''; self.in_place=False; self.options=core.SortOptions(); self.auto_cleanup=False; self.sort_by='Source name'; self.descending=False
        self.catalog=core.Catalog(); self.pending=None; self.last_sort=''; self.epoch=0; self.closed=False
        self.change_runs = {}
        self.file_trails = {}
        self.change_errors = {}
        self.ops=ThreadPoolExecutor(max_workers=1,thread_name_prefix='sortrr-work'); self.details_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='sortrr-info')
        self.previews=PreviewManager(core.DATA/'previews',self.invoke.emit); self.art=ArtworkCache(core.DATA/'posters')
        self.model=MediaModel(self); self.proxy=MediaProxy(self); self.proxy.setSourceModel(self.model)
        self.notify_timer=QTimer(self); self.notify_timer.setSingleShot(True); self.notify_timer.setInterval(45); self.notify_timer.timeout.connect(self.stateChanged)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.player.setAudioOutput(self.audio)
        self.frame_ready = False
        self.audio_device_id = ''
        self.dark_mode = False
        self.output_devices = []
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self.refresh_audio_outputs)
        self.audio.deviceChanged.connect(self.audioOutputsChanged.emit)
        self.player.tracksChanged.connect(self.ensure_audio_track)
        for signal in (self.player.positionChanged, self.player.durationChanged,
                       self.player.playbackStateChanged, self.player.errorChanged,
                       self.player.tracksChanged, self.player.activeTracksChanged,
                       self.player.seekableChanged, self.audio.volumeChanged, self.audio.mutedChanged):
            signal.connect(lambda *_: self.playbackChanged.emit())
        self.w={'open':False}; self.wids=[]; self.windex=0; self.wdrafts={}; self.detail_generation=0; self.detail_future=None
        self.player.seekableChanged.connect(self.apply_wizard_seek)
        self.load_settings()
        self.refresh_audio_outputs()
        self.saved_progress = self.read_progress()
    @Slot(object)
    def deliver(self,fn):
        if self.closed: return
        try: fn()
        except Exception: log.exception('GUI callback failed')
    def notify(self):
        if not self.notify_timer.isActive(): self.notify_timer.start()
    @Property(bool, notify=darkModeChanged)
    def darkMode(self):
        return self.dark_mode

    @Slot(bool)
    def setDarkMode(self, enabled):
        if self.dark_mode == enabled:
            return
        self.dark_mode = enabled
        self.darkModeChanged.emit()
        try:
            self.save()
        except OSError:
            log.exception('Could not save appearance preference')
            self.toast.emit('Appearance changed, but the preference could not be saved.')

    @Property(QObject,constant=True)
    def mediaModel(self): return self.proxy
    @Property('QVariantMap',notify=stateChanged)
    def state(self):
        visible = [self.items[i] for i in self.visible_ids()]
        selected = [self.items[i] for i in self.selected_visible()]
        connected = bool(os.environ.get('SORTRR_TMDB_TOKEN', '').strip())
        return {
            'source': self.source, 'destination': self.destination, 'inPlace': self.in_place,
            'savedSource': self.saved_progress['source'] if self.saved_progress else '',
            'savedStage': self.saved_progress['stage'] if self.saved_progress else '',
            'rejectFolder': self.reject_folder,
            'rejected': sum(m.status == core.REJECTED for m in self.items),
            'canRecycle': QFile.supportsMoveToTrash(),
            'autoRename': self.options.rename_files, 'autoCleanup': self.auto_cleanup,
            'busy': self.busy, 'mutating': self.mutating, 'status': self.status,
            'total': len(self.items), 'ready': sum(m.status == 'Ready' for m in self.items),
            'unresolved': len(core.unresolved_media(self.items)),
            'visible': len(visible), 'visibleReady': sum(m.status == 'Ready' for m in visible),
            'visibleUnresolved': len(core.unresolved_media(visible)),
            'visibleMatched': sum(bool(m.chosen) for m in visible),
            'selected': len(selected), 'selectedReady': sum(m.status == 'Ready' for m in selected),
            'selectedMatched': sum(bool(m.chosen) for m in selected),
            'selectedSkippable': sum(m.status == 'Ready' for m in selected) + len(core.unresolved_media(selected)),
            'lastSort': self.last_sort,
            'query': self.proxy.query, 'filter': self.proxy.kind, 'runtimeFilter': self.proxy.runtime,
            'reviewOnly': self.proxy.review, 'readyOnly': self.proxy.ready_only,
            'rejectedOnly': self.proxy.rejected_only,
            'selectedReidentifiable': sum(m.status not in {core.REJECTED, core.REJECT_MOVED, core.REJECT_RECYCLED} for m in selected),
            'sortBy': self.sort_by, 'descending': self.descending,
            'preset': core.preset_name(replace(self.options, rename_files=True)),
            'movieLayout': self.options.movie_layout, 'showLayout': self.options.show_layout,
            'idStyle': self.options.id_style, 'connected': connected,
        }
    @Property('QVariantMap',notify=wizardChanged)
    def wizard(self): return dict(self.w)
    @Property('QVariantMap',notify=playbackChanged)
    def playback(self):
        labels=[]
        for i,track in enumerate(self.player.audioTracks()):
            language=track.stringValue(QMediaMetaData.Key.Language); title=track.stringValue(QMediaMetaData.Key.Title)
            labels.append(f'{i+1}: '+(language or title or 'Audio track')+((' - '+title) if language and title else ''))
        return {'playing':self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState,'position':self.player.position(),'duration':self.player.duration(),'seekable':self.player.isSeekable(),'volume':self.audio.volume(),'muted':self.audio.isMuted(),'tracks':labels,'activeTrack':self.player.activeAudioTrack(),'error':self.player.errorString(),'frameReady':self.frame_ready}
    @Property('QVariantMap', notify=audioOutputsChanged)
    def audioOutputs(self):
        default = QMediaDevices.defaultAudioOutput()
        names = ['Windows default' + (f' ({default.description()})' if not default.isNull() else '')]
        names.extend(device.description() for device in self.output_devices)
        selected = next((i for i, device in enumerate(self.output_devices, 1)
                         if bytes(device.id()).hex() == self.audio_device_id), 0)
        return {'names': names, 'selected': selected, 'current': self.audio.device().description()}

    def refresh_audio_outputs(self):
        self.output_devices = QMediaDevices.audioOutputs()
        preferred = next((device for device in self.output_devices
                          if bytes(device.id()).hex() == self.audio_device_id), QAudioDevice())
        self.audio.setDevice(preferred)
        self.audioOutputsChanged.emit()

    @Slot(int)
    def setAudioOutputDevice(self, index):
        if not 0 <= index <= len(self.output_devices):
            return
        self.audio_device_id = bytes(self.output_devices[index - 1].id()).hex() if index else ''
        self.refresh_audio_outputs()
        try:
            self.save()
        except OSError:
            log.exception('Could not save the playback device')

    def ensure_audio_track(self):
        if self.player.audioTracks() and self.player.activeAudioTrack() < 0:
            self.player.setActiveAudioTrack(0)

    @Property('QVariantList',constant=True)
    def presets(self): return list(core.LAYOUT_PRESETS)
    @Property('QVariantList',constant=True)
    def movieLayouts(self): return [{'label':k,'value':v} for k,v in core.MOVIE_LAYOUTS.items()]
    @Property('QVariantList',constant=True)
    def showLayouts(self): return [{'label':k,'value':v} for k,v in core.SHOW_LAYOUTS.items()]
    @Property('QVariantList',constant=True)
    def idStyles(self): return [{'label':k,'value':v} for k,v in core.ID_STYLES.items()]
    def actual(self,m): return m.organized_path if m.organized_path and m.status in {'Moved','Renamed',core.REJECT_MOVED} else m.source
    def row(self,uid):
        m=self.items[uid]; c=m.chosen or {}; status=m.status
        tone='good' if status=='Ready' else ('done' if status in {'Copied','Moved','Renamed','Already organized','Previously copied','Previously moved',core.REJECT_MOVED,core.REJECT_RECYCLED} else ('muted' if status=='Skipped by you' else ('error' if status.startswith('Lookup failed') or status=='Connect TMDb' else 'review')))
        return dict(uid=uid,mediaTitle=c.get('title',m.query),fileName=self.actual(m).name,filePath=str(self.actual(m)),mediaKind=m.kind,releaseYear=c.get('year',m.year),seasonText=str(m.season) if m.season is not None else '',episodeText=f'S{m.season:02d}E{m.episode:02d}' if m.season is not None and m.episode is not None else '',statusText=status,statusTone=tone,thumbnail=self.thumbs.get(uid,''),isSelected=uid in self.selected,isRemembered=m.cached,runtimeStatus=saved_runtime(m).get('status','Unchecked'),runtimeLabel=saved_runtime(m).get('label','Runtime not checked'))
    def visible_ids(self): return [self.proxy.mapToSource(self.proxy.index(i,0)).row() for i in range(self.proxy.rowCount())]
    def selected_visible(self): return [i for i in self.visible_ids() if i in self.selected]
    def load_settings(self):
        try:
            d=json.loads((core.DATA/'settings.json').read_text(encoding='utf-8-sig')); self.source=d.get('source',''); self.destination=d.get('library',''); self.reject_folder=d.get('reject_folder',''); self.in_place=bool(d.get('in_place',False)); self.options=core.SortOptions(**d.get('sorting',{})); self.auto_cleanup=bool(d.get('auto_cleanup',False)); self.proxy.kind=d.get('media_filter','All media'); self.sort_by=d.get('sort_by','Source name'); self.descending=bool(d.get('descending',False)); self.audio_device_id=str(d.get('audio_output_device') or ''); self.dark_mode=d.get('dark_mode') is True
        except (OSError,ValueError,TypeError): pass
        token=core.DATA/'tmdb-token.txt'
        try:
            if token.exists(): os.environ['SORTRR_TMDB_TOKEN']=token.read_text(encoding='utf-8-sig').strip()
        except OSError: log.exception('Could not read TMDb connection')
        self.proxy.field=core.VIEW_SORT_FIELDS.get(self.sort_by,'file'); self.proxy.sort(0,Qt.SortOrder.DescendingOrder if self.descending else Qt.SortOrder.AscendingOrder)
    def save(self):
        core.DATA.mkdir(parents=True,exist_ok=True)
        (core.DATA/'settings.json').write_text(json.dumps(dict(source=self.source,library=self.destination,reject_folder=self.reject_folder,in_place=self.in_place,sorting=self.options.to_dict(),auto_cleanup=self.auto_cleanup,media_filter=self.proxy.kind,sort_by=self.sort_by,descending=self.descending,audio_output_device=self.audio_device_id,dark_mode=self.dark_mode)),encoding='utf-8')
    def read_progress(self):
        try:
            progress = json.loads((core.DATA / 'progress.json').read_text(encoding='utf-8'))
            if (progress.get('version') == 1
                    and isinstance(progress.get('source'), str)
                    and progress.get('stage') in {'review', 'wizard', 'organize'}
                    and isinstance(progress.get('rows'), list)
                    and isinstance(progress.get('plan'), dict)
                    and isinstance(progress.get('view'), dict)):
                return progress
        except (OSError, ValueError, AttributeError, TypeError):
            pass
        return None

    @Slot(str, str, str, result=bool)
    def saveProgress(self, stage, scope, reject_mode):
        if self.busy:
            return False
        rows = []
        for media in self.items:
            path = self.actual(media)
            unresolved = bool(core.unresolved_media([media]))
            rows.append({
                'path': str(path), 'signature': list(media.signature),
                'status': media.status if unresolved else 'Not identified',
                'candidates': media.candidates if unresolved else [],
            })
        if not rows or not self.source:
            self.toast.emit('Scan a source folder before saving progress.')
            return False
        checkpoint = {
            'version': 1, 'source': self.source, 'stage': stage,
            'rows': rows, 'selected': sorted(self.selected),
            'view': {'query': self.proxy.query, 'kind': self.proxy.kind, 'runtime': self.proxy.runtime,
                     'tab': 'review' if self.proxy.review else 'ready' if self.proxy.ready_only
                     else 'rejected' if self.proxy.rejected_only else 'all',
                     'sort': self.sort_by, 'descending': self.descending},
            'plan': {'scope': scope, 'reject_mode': reject_mode, 'destination': self.destination,
                     'reject_folder': self.reject_folder, 'in_place': self.in_place,
                     'auto_cleanup': self.auto_cleanup, 'options': self.options.to_dict()},
        }
        if stage == 'wizard':
            self.draft()
            checkpoint['wizard'] = {
                'order': self.wids, 'index': self.windex, 'queue': self.wqueue,
                'drafts': {str(i): draft for i, draft in self.wdrafts.items()},
                'deferred': list(self.wdeferred),
            }
        temporary = None
        try:
            core.DATA.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=core.DATA, delete=False) as file:
                temporary = Path(file.name)
                json.dump(checkpoint, file, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, core.DATA / 'progress.json')
        except (OSError, ValueError) as exc:
            if temporary:
                temporary.unlink(missing_ok=True)
            message = f'Could not save progress: {exc}'
            if self.w.get('open'):
                self.w['message'] = message
                self.wizardChanged.emit()
            else:
                self.toast.emit(message)
            return False
        self.saved_progress = checkpoint
        self.status = 'Progress saved. Resume it from Source or Review files.'
        self.stateChanged.emit()
        return True

    @Slot(bool)
    def saveReviewAndClose(self, search_open):
        if self.w.get('open') and not self.w.get('complete'):
            self.w['searchOpen'] = search_open
            if self.saveProgress('wizard', 'all', 'leave'):
                self.closeWizard()

    @Slot()
    def resumeProgress(self):
        if self.busy or not self.saved_progress or self.w.get('open'):
            return
        checkpoint = self.saved_progress
        plan = checkpoint['plan']
        view = checkpoint['view']
        try:
            source = Path(checkpoint['source']).expanduser().resolve()
            options = core.SortOptions(**plan['options'])
            in_place = bool(plan['in_place'])
            destination = str(plan['destination'])
            output = source if in_place else Path(destination).expanduser().resolve() if destination else None
            if not source.is_dir():
                raise ValueError('The saved source folder is unavailable.')
        except (KeyError, TypeError, OSError, ValueError) as exc:
            self.toast.emit(f'Could not resume progress: {exc}')
            return

        self.status = 'Opening saved progress...'

        def load():
            history = core.History()
            items = []
            remap = {}
            for old_uid, row in enumerate(checkpoint['rows']):
                try:
                    path = core.source_boundary(Path(row['path']), source)
                    if path.suffix.lower() not in core.VIDEO:
                        continue
                    media = core.parse(path)
                    if list(media.signature) != row['signature']:
                        continue
                    if not history.restore(media, output, 'move' if in_place else 'copy', options):
                        media.status = row['status']
                        media.candidates = row['candidates']
                except (OSError, ValueError, TypeError, KeyError):
                    continue
                remap[old_uid] = len(items)
                items.append(media)
            return items, remap

        def resume(result):
            items, remap = result
            self.source = checkpoint['source']
            self.destination = destination
            self.in_place = in_place
            self.options = options
            self.auto_cleanup = bool(plan.get('auto_cleanup'))
            self.reject_folder = str(plan.get('reject_folder', ''))
            self.last_sort = ''
            self.epoch += 1
            self.thumbs.clear()
            self.thumb_requested.clear()
            self.selected = {remap[i] for i in checkpoint.get('selected', []) if i in remap}
            self.model.reset(items)
            self.scanStarted.emit()
            self.proxy.query = view.get('query', '')
            self.proxy.kind = view.get('kind', 'All media')
            self.proxy.runtime = view.get('runtime', 'Any length')
            self.setReviewView(view.get('tab', 'all'))
            self.setSort(view.get('sort', 'Source name'), bool(view.get('descending')))
            missing = len(checkpoint['rows']) - len(items)
            self.status = f'Resumed {len(items)} saved files.'
            if missing:
                self.status += f' {missing} changed or missing files were left out. Scan again to refresh.'
            self.stateChanged.emit()
            self.progressResumed.emit(checkpoint['stage'], plan.get('scope', 'all'), plan.get('reject_mode', 'leave'))
            if checkpoint['stage'] == 'wizard' and checkpoint.get('wizard'):
                self.resume_wizard(checkpoint['wizard'], remap)

        self.work(load, resume)

    def resume_wizard(self, wizard, remap):
        if not isinstance(wizard, dict):
            return
        order = wizard.get('order', [])
        drafts = wizard.get('drafts', {})
        position = wizard.get('index', 0)
        deferred = wizard.get('deferred', [])
        if not (isinstance(order, list) and all(isinstance(i, int) for i in order)
                and isinstance(drafts, dict) and isinstance(position, int) and isinstance(deferred, list)):
            return
        self.wqueue = bool(wizard.get('queue'))
        self.wids = [remap[i] for i in order if i in remap]
        if not self.wids:
            return
        self.wdrafts = {
            remap[i]: drafts[str(i)] for i in order
            if i in remap and isinstance(drafts.get(str(i)), dict)
        }
        self.wdeferred = {remap[i] for i in deferred if isinstance(i, int) and i in remap}
        start = sum(i in remap for i in order[:position])
        if self.wqueue:
            pending = [i for i, uid in enumerate(self.wids)
                       if uid not in self.wdeferred and core.unresolved_media([self.items[uid]])]
            self.windex = next((i for i in pending if i >= start), pending[0] if pending else len(self.wids))
        else:
            self.windex = min(start, len(self.wids) - 1)
        self.show_step()

    def output(self): return self.source if self.in_place else self.destination
    def work(self,fn,done=None,mutation=False):
        if self.busy: return
        self.busy=True; self.mutating=mutation; self.stateChanged.emit()
        if mutation: self.player.stop(); self.player.setSource(QUrl())
        def task():
            result=None; error=None
            try:
                if mutation:
                    self.previews.close(wait=True)
                    core.DATA.mkdir(parents=True, exist_ok=True)
                    lock = QLockFile(str(core.DATA / 'file-changes.lock'))
                    lock.setStaleLockTime(0)
                    if not lock.tryLock(0):
                        raise OSError('Another Sortrr window is changing files. Try again when it finishes.')
                    try:
                        result = fn()
                    finally:
                        lock.unlock()
                else:
                    result = fn()
            except Exception as exc: error=str(exc); log.exception('Operation failed')
            def finish():
                self.busy=False; self.mutating=False
                if self.previews.closed: self.previews=PreviewManager(core.DATA/'previews',self.invoke.emit); self.thumb_requested.clear()
                if error: self.status=error; self.toast.emit(error)
                elif done: done(result)
                self.stateChanged.emit()
            self.invoke.emit(finish)
        self.ops.submit(task)
    @Slot(str,str)
    def setPath(self,field,value):
        if self.busy: return
        if field=='source':
            if self.source!=value:
                self.source=value; self.epoch+=1; self.selected.clear(); self.thumbs.clear(); self.thumb_requested.clear(); self.model.reset()
                self.status='Source changed. Scan to identify files.'; self.last_sort=''
        elif field == 'reject':
            self.reject_folder = value
        elif self.destination!=value:
            self.destination=value; self.recheck()
        self.save(); self.stateChanged.emit()
    @Slot(str)
    def pickFolder(self,field):
        if self.busy: return
        title, initial = {
            'source': ('Choose media folder', self.source),
            'reject': ('Choose a folder for rejected files', self.reject_folder),
            'destination': ('Choose library destination', self.destination),
        }[field]
        path=QFileDialog.getExistingDirectory(None,title,initial)
        if path: self.setPath(field,path)
    @Slot(bool,bool,bool)
    def setAutomatic(self,move,rename,cleanup):
        if self.busy: return
        self.in_place=move; self.options=replace(self.options,rename_files=rename); self.auto_cleanup=cleanup; self.recheck(); self.save(); self.stateChanged.emit()
    @Slot(str)
    def setQuery(self,text): self.proxy.query=text.casefold(); self.proxy.invalidateFilter(); self.notify()
    @Slot(str)
    def setMediaFilter(self, kind):
        self.proxy.kind = kind
        self.proxy.invalidateFilter()
        self.save()
        self.notify()

    @Slot(str)
    def setReviewView(self, view):
        self.proxy.review = view == 'review'
        self.proxy.ready_only = view == 'ready'
        self.proxy.rejected_only = view == 'rejected'
        self.proxy.invalidateFilter()
        self.notify()

    @Slot()
    def resetFilters(self):
        self.proxy.query = ''
        self.proxy.kind = 'All media'
        self.proxy.runtime = 'Any length'
        self.proxy.invalidateFilter()
        self.save()
        self.notify()

    @Slot(str,bool)
    def setSort(self,name,descending): self.sort_by=name; self.descending=descending; self.proxy.field=core.VIEW_SORT_FIELDS.get(name,'file'); self.proxy.invalidate(); self.proxy.sort(0,Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder); self.save(); self.notify()
    @Slot(int,bool)
    def select(self,uid,checked):
        if checked: self.selected.add(uid)
        else: self.selected.discard(uid)
        self.model.changed(uid); self.notify()
    @Slot(bool)
    def selectVisible(self,checked):
        for uid in self.visible_ids():
            if checked: self.selected.add(uid)
            else: self.selected.discard(uid)
            self.model.changed(uid)
        self.notify()
    def all_changed(self):
        if self.items: self.model.dataChanged.emit(self.model.index(0),self.model.index(len(self.items)-1),list(self.model.roleNames()))
    @Slot()
    def scan(self):
        if self.busy: return
        src = Path(self.source).expanduser()
        if not self.source or not src.is_dir():
            self.toast.emit('Choose an existing source folder.')
            return
        src = src.resolve()
        dest = Path(self.output()).expanduser().resolve() if self.output() else None
        if not self.in_place and dest and (src == dest or src.is_relative_to(dest)):
            dest = None
        reject_folder = Path(self.reject_folder).expanduser().resolve() if self.reject_folder else None
        excluded = [path for path in (dest if not self.in_place else None, reject_folder)
                    if path and path != src and path.is_relative_to(src)]
        self.save(); self.epoch+=1; self.selected.clear(); self.thumbs.clear(); self.thumb_requested.clear(); self.model.reset(); options=self.options; mode='move' if self.in_place else 'copy'; self.status='Discovering and identifying files...'; self.last_sort=''
        def append(m): self.model.append(m); self.notify()
        def changed(uid,m): self.model.changed(uid); self.status='Scanned '+m.source.name; self.notify()
        def job():
            history=core.History(); found=[]
            def files():
                for folder,dirs,names in os.walk(src,followlinks=False):
                    dirs[:]=[d for d in dirs if d.casefold()!='.sortrr-trash' and not core.is_link(Path(folder)/d) and not any((Path(folder)/d).resolve().is_relative_to(path) for path in excluded)]
                    for name in sorted(names):
                        path=Path(folder)/name
                        if path.suffix.lower() not in core.VIDEO or core.is_link(path): continue
                        try: m=core.parse(path)
                        except OSError: continue
                        uid=len(found); found.append(m)
                        if m.status=='Waiting': m.status='Identifying'
                        self.invoke.emit(lambda m=m:append(m)); yield uid,m
            return core.identify_batch(files(),self.catalog,history,dest,mode,options=options,report=lambda uid,m:self.invoke.emit(lambda uid=uid,m=m:changed(uid,m)), finish_scan_on_setup=True)
        def done(result):
            if result['setup']:
                self.status = 'Scan complete. Connect TMDb for movie lookup, or create entries manually.'
            else: self.status=f"Scan complete. {result['completed']} files, {result['remembered']} remembered, {result['errors']} errors."
        self.work(job,done)
        self.scanStarted.emit()
    @Slot(int)
    def requestThumbnail(self,uid):
        if self.mutating or not 0<=uid<len(self.items): return
        m=self.items[uid]; path=self.actual(m); key=(uid,str(path),self.epoch)
        if key in self.thumb_requested: return
        self.thumb_requested.add(key); epoch=self.epoch
        def done(frame,error):
            if epoch!=self.epoch or uid>=len(self.items) or self.items[uid] is not m: return
            if frame: self.thumbs[uid]=QUrl.fromLocalFile(str(frame.path)).toString(); self.model.changed(uid)
        if not self.previews.request(path,done,size=(160,90),fraction=.1): self.thumb_requested.discard(key)
    @Slot(int,float,int)
    def requestHover(self,uid,fraction,token):
        if self.mutating or not 0<=uid<len(self.items): return
        epoch=self.epoch
        def done(frame,error):
            if epoch==self.epoch and frame: self.hoverReady.emit(uid,token,QUrl.fromLocalFile(str(frame.path)).toString(),timestamp(frame.seconds)+' / '+timestamp(frame.duration))
        self.previews.request(self.actual(self.items[uid]),done,size=(320,180),fraction=max(0,min(1,fraction)))
    @Slot()
    def skipSelected(self):
        if self.busy: return
        history = core.History()
        skipped = 0
        for uid in self.selected_visible():
            media = self.items[uid]
            if media.status != 'Ready' and not core.unresolved_media([media]):
                continue
            try:
                history.save(replace(media, chosen=None, runtime_check={}, status='Skipped by you'))
            except OSError:
                self.toast.emit(f'Could not update {media.source.name}. Scan the folder again.')
                continue
            media.chosen = None
            media.runtime_check = {}
            media.status = 'Skipped by you'
            self.model.changed(uid)
            skipped += 1
        if skipped:
            self.status = f'Marked {skipped} files as skipped.'
        self.notify()
    @Slot()
    def reidentifySelected(self):
        ids=[i for i in self.selected_visible() if self.items[i].status not in {core.REJECTED,core.REJECT_MOVED,core.REJECT_RECYCLED}]
        if not ids or self.busy: return
        for uid in ids:
            m=self.items[uid]; m.source=self.actual(m); m.chosen=None; m.runtime_check={}; m.cached=False; m.status='Re-identifying'; self.model.changed(uid)
        def job(): return core.identify_batch([(i,self.items[i]) for i in ids],self.catalog,reidentify=True,report=lambda uid,m:self.invoke.emit(lambda uid=uid:self.model.changed(uid)))
        def done(result):
            self.status=f"Re-identified {result['completed']} files; {result['errors']} errors."
            if result['setup']: self.status=result['setup']; self.dialogRequested.emit({'kind':'database','title':'Connect TMDb'})
        self.work(job,done)
    @Slot(str)
    def setRuntimeFilter(self,value):
        if value not in {'Any length','Matches','Differs','Unknown','Unchecked'}: return
        self.proxy.runtime=value; self.proxy.invalidateFilter(); self.notify()
    def measure_runtime(self,path,candidate,kind,season,episode):
        if candidate.get('provider') == 'Manual':
            return {**core.compare_runtime(None, None), 'label': 'No database runtime for this manual entry'}
        try: local=self.previews.probe(path)[2]['duration']
        except (OSError,RuntimeError,ValueError) as exc: return {**core.compare_runtime(None,None),'label':'File runtime unavailable: '+str(exc)}
        try: expected=self.catalog.expected_runtime(candidate,kind,season,episode)
        except (OSError,RuntimeError,ValueError) as exc: return {**core.compare_runtime(local,None),'label':'Database runtime unavailable: '+str(exc)}
        return core.compare_runtime(local,expected)
    @Slot()
    def checkRuntimes(self):
        if self.busy: return
        ids=[i for i in (self.selected_visible() or self.visible_ids()) if self.items[i].chosen]
        if not ids: self.toast.emit('Identify files before checking their runtimes.'); return
        jobs=[(i,self.actual(m),m.chosen,m.kind,m.season,m.episode) for i in ids for m in [self.items[i]]]
        self.status=f'Checking runtimes for {len(jobs)} files...'
        def apply(uid,result):
            self.items[uid].runtime_check=result; self.model.changed(uid); self.notify()
        def check(job):
            uid,path,candidate,kind,season,episode=job
            try:
                stat=path.stat()
                if (stat.st_size,stat.st_mtime_ns)!=self.items[uid].signature: raise ValueError('File changed; scan again.')
                result=self.measure_runtime(path,candidate,kind,season,episode)
                updated=path.stat()
                if (updated.st_size,updated.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns): raise ValueError('File changed; scan again.')
            except (OSError,ValueError) as exc:
                result={**core.compare_runtime(None,None),'label':str(exc)}
            result['key']=runtime_key(candidate,kind,season,episode)
            return uid,path,result
        def run():
            counts={'Matches':0,'Differs':0,'Unknown':0}
            history=core.History()
            with ThreadPoolExecutor(max_workers=8) as pool:
                for start in range(0,len(jobs),32):
                    for future in as_completed([pool.submit(check,j) for j in jobs[start:start+32]]):
                        uid,path,result=future.result(); counts[result['status']]+=1
                        if result['status']!='Unknown':
                            try: history.save(replace(self.items[uid],source=path,runtime_check=result))
                            except OSError: pass
                        self.invoke.emit(lambda uid=uid,result=result:apply(uid,result))
            return counts
        def done(counts):
            self.status=f"Runtime check complete: {counts['Matches']} match, {counts['Differs']} differ, {counts['Unknown']} unknown."
        self.work(run,done)
    @Slot()
    def requestDatabase(self):
        self.dialogRequested.emit({'kind':'database'})
    @Slot(str,str,str)
    def setLayouts(self,movie,show,ids):
        if self.busy: return
        try: self.options=core.SortOptions(movie,show,ids,self.options.rename_files)
        except ValueError as exc: self.toast.emit(str(exc)); return
        self.recheck(); self.save(); self.stateChanged.emit()
    @Slot(str)
    def setPreset(self,name):
        if not self.busy and name in core.LAYOUT_PRESETS:
            self.options=replace(core.LAYOUT_PRESETS[name].options,rename_files=self.options.rename_files); self.recheck(); self.save(); self.stateChanged.emit()
    @Slot(str,str,str,bool,result='QVariantList')
    def layoutExamples(self,movie,show,ids,rename):
        options=core.SortOptions(movie,show,ids,rename)
        examples=[
            core.Media(Path('Example.Movie.2020.mp4'),'Example Movie','2020',chosen={'title':'Example Movie','year':'2020','provider':'TMDB','id':12345}),
            core.Media(Path('Example.Show.S01E02.mkv'),'Example Show','2018',1,2,chosen={'title':'Example Show','year':'2018','provider':'TVmaze','id':1,'external_ids':{'thetvdb':54321}}),
        ]
        return [core.destination(m,Path('.'),options).as_posix() for m in examples]
    @Slot(str)
    def openGuide(self,server):
        docs={'Plex':core.PLEX_DOCS,'Jellyfin':core.JELLYFIN_DOCS,'Emby':core.EMBY_DOCS}.get(server)
        if docs: QDesktopServices.openUrl(QUrl(docs[0][1]))
    @Slot(str)
    def saveToken(self,token):
        if self.busy: return
        token=token.strip(); core.DATA.mkdir(parents=True,exist_ok=True); (core.DATA/'tmdb-token.txt').write_text(token,encoding='utf-8')
        if token: os.environ['SORTRR_TMDB_TOKEN']=token
        else: os.environ.pop('SORTRR_TMDB_TOKEN',None)
        self.catalog=core.Catalog(); self.status='TMDb connection saved. Scan again to use it.'; self.stateChanged.emit()
    @Slot(str)
    def openUrl(self,url):
        parsed=core.urllib.parse.urlsplit(url)
        if parsed.scheme=='https' and parsed.hostname in {'www.themoviedb.org','www.tvmaze.com','support.plex.tv','jellyfin.org','emby.media'}: QDesktopServices.openUrl(QUrl(url))
    def recheck_match(self, media, output, history):
        if media.status in {'Moved', 'Renamed'}:
            media.source = self.actual(media)
        if not media.source.exists():
            media.status = 'File unavailable; scan again'
        elif history.key(media.source) == history.key(core.destination(media, output, self.options)):
            media.status = 'Already organized'
        elif history.processed(media, output, 'move' if self.in_place else 'copy', self.options):
            media.status = 'Previously moved' if self.in_place else 'Previously copied'
        else:
            media.status = 'Ready'

    def recheck(self):
        if not self.output():
            return
        output = Path(self.output()).expanduser()
        history = core.History()
        for uid, media in enumerate(self.items):
            if media.chosen and media.status in {'Ready', 'Copied', 'Moved', 'Renamed',
                                                'Already organized', 'Previously copied', 'Previously moved'}:
                self.recheck_match(media, output, history)
                self.model.changed(uid)

    @Slot(str)
    @Slot(str, str)
    def prepareSort(self, scope, reject_mode='leave'):
        if self.busy or reject_mode not in {'leave', 'folder', 'recycle'}:
            return
        if scope == 'all':
            ids = range(len(self.items))
        elif scope == 'selected':
            ids = self.selected_visible()
        elif scope == 'visible':
            ids = self.visible_ids()
        elif scope == 'none':
            ids = []
        else:
            return
        items = [self.items[i] for i in ids if self.items[i].chosen and self.items[i].status == 'Ready']
        rejected = [m for m in self.items if m.status == core.REJECTED] if reject_mode != 'leave' else []
        if not items and not rejected:
            self.toast.emit('Choose ready or rejected files to include in the plan.')
            return

        source = Path(self.source).expanduser().resolve()
        mode = 'Move' if self.in_place else 'Copy'
        output = None
        rows = []
        messages = []
        if items:
            if not self.output():
                self.toast.emit('Choose a library destination for the ready files.')
                return
            output = Path(self.output()).expanduser().resolve()
            if not self.in_place and source.is_relative_to(output):
                self.toast.emit('Choose a library folder that does not contain the source folder.')
                return
            if output.exists() and not output.is_dir():
                self.toast.emit('The library destination must be a folder.')
                return
            rows.extend({'label': m.source.name, 'detail': str(core.destination(m, output, self.options))}
                        for m in items)
            ready_label = 'ready file' if len(items) == 1 else 'ready files'
            messages.append(f'{mode} {len(items)} {ready_label} to {output}.')
            if self.auto_cleanup:
                messages.append('Common source junk will be archived after each successful group.')

        reject_root = None
        reject_paths = []
        if rejected:
            reject_label = 'rejected file' if len(rejected) == 1 else 'rejected files'
            if reject_mode == 'folder':
                if not self.reject_folder:
                    self.toast.emit('Choose a destination for rejected files.')
                    return
                reject_root = Path(self.reject_folder).expanduser().resolve()
                if source.is_relative_to(reject_root) or (reject_root.exists() and not reject_root.is_dir()):
                    self.toast.emit('Choose a reject folder that is separate from the source root.')
                    return
                messages.append(f'Move {len(rejected)} {reject_label} to {reject_root}, keeping their relative paths.')
            else:
                messages.append(f'Send {len(rejected)} {reject_label} to the Recycle Bin. Restore them in Windows if needed. Files on network shares or other drives that cannot recycle will be left in place.')
            for media in rejected:
                path = media.source.absolute()
                if not path.is_relative_to(source):
                    self.toast.emit('A rejected path is outside the source. Scan again before organizing.')
                    return
                target = reject_root / path.relative_to(source) if reject_root else None
                reject_paths.append((media, path, target))
                rows.append({'label': 'Rejected · ' + str(path), 'detail': str(target) if target else 'Recycle Bin'})

        count = len(items) + len(reject_paths)
        file_label = f'{count} file' + ('s' if count != 1 else '')
        if rejected:
            title = f'Organize {file_label}' if items else f'Handle {file_label} marked as rejected'
            button = 'Apply plan' if items else ('Move rejected files' if reject_root else 'Send to Recycle Bin')
        else:
            title = button = f'{mode} {file_label}'
        self.pending = ('sort', (items, output, source, mode.lower(), self.options, self.auto_cleanup,
                                 reject_paths, reject_root))
        self.dialogRequested.emit({'kind': 'confirm', 'action': 'sort', 'title': title,
                                   'text': ' '.join(messages), 'rows': rows, 'button': button})

    @staticmethod
    def recycle_file(path):
        if os.name == 'nt':
            from ctypes import windll
            # Windows Recycle Bin is only used here on fixed local volumes.
            if windll.kernel32.GetDriveTypeW(str(path.anchor)) != 3:
                raise OSError('Recycle Bin needs a local fixed drive. Choose a reject folder instead.')
        file = QFile(path.as_posix())
        if not file.moveToTrash():
            raise OSError('Could not send to the Recycle Bin: ' + file.errorString())

    @staticmethod
    def read_change_history():
        runs = {}
        for path in core.change_journals():
            try:
                changes = core.read_file_changes(path)
                if changes:
                    runs[path.name] = (changes, '')
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                runs[path.name] = ([], 'This operation log could not be read.')
        trails = core.file_trails({name: changes for name, (changes, _) in runs.items()})
        return runs, {f'{trail.key[0]}:{trail.key[1]}': trail for trail in reversed(trails)}

    def update_change_history(self, snapshot):
        self.change_runs, self.file_trails = snapshot
        self.changeHistoryChanged.emit()

    @Slot()
    def loadChangeHistory(self):
        self.work(self.read_change_history, self.update_change_history)

    @Property('QVariantList', notify=changeHistoryChanged)
    def changeHistory(self):
        rows = []
        for name, (changes, error) in self.change_runs.items():
            labels = dict.fromkeys(core.CHANGE_LABELS[c.record['mode']] for c in changes)
            stamp = datetime.fromtimestamp(int(Path(name).stem[4:]) / 1e9)
            rows.append({
                'id': name, 'date': stamp.strftime('%b %d, %Y  %I:%M:%S %p'),
                'label': ' + '.join(labels) or 'Unreadable operation',
                'count': len(changes), 'remaining': sum(c.reversible for c in changes),
                'reverted': sum(c.reverted for c in changes), 'error': error,
            })
        return rows

    @Slot(str, result='QVariantList')
    def fileChanges(self, run):
        changes, _ = self.change_runs.get(run, ([], ''))
        errors = self.change_errors.get(run, {})
        return [{
            'id': str(c.index), 'label': core.CHANGE_LABELS[c.record['mode']],
            'source': c.record['source'], 'target': c.record['target'],
            'mode': c.record['mode'], 'reversible': c.reversible,
            'status': ('Reverted' if c.reverted else 'Restore in Windows Recycle Bin' if c.record['mode'] == 'recycle'
                       else errors.get(c.index) or ('Check on revert' if c.record['event'] == 'intent' else '')),
        } for c in changes]

    @Slot(str, result='QVariantList')
    def searchFileHistory(self, query):
        query = query.strip().casefold().replace('\\', '/')
        if not query:
            return []
        results = []
        for key, trail in self.file_trails.items():
            if not any(query in path.casefold().replace('\\', '/') for path in trail.aliases):
                continue
            first = trail.steps[0][1].record
            stamp = datetime.fromtimestamp(int(Path(trail.steps[-1][0]).stem[4:]) / 1e9)
            results.append({
                'id': key, 'name': Path(trail.original).name, 'original': trail.original,
                'current': trail.current, 'count': len(trail.steps), 'status': trail.unavailable,
                'copy': first['mode'] == 'copy', 'canRestore': trail.can_restore,
                'date': stamp.strftime('%b %d, %Y  %I:%M:%S %p'),
            })
        return results

    @Slot(str)
    def prepareOriginalRestore(self, key):
        trail = self.file_trails.get(key)
        if self.busy or not trail or not trail.can_restore:
            return
        count = len(trail.steps)
        is_copy = trail.steps[0][1].record['mode'] == 'copy'
        self.pending = ('restore-original', tuple((name, change.index) for name, change in trail.steps))
        self.dialogRequested.emit({
            'kind': 'confirm', 'action': 'restore-original', 'title': 'Restore original file',
            'text': (
                'Sortrr will keep the unchanged original and remove this verified copy.'
                if is_copy else 'Sortrr will return this file to its original name and folder.'
            ) + (f' This reverses {count} recorded changes for this file.' if count > 1 else ''),
            'rows': [{'label': 'Latest recorded path', 'detail': trail.current},
                     {'label': 'Original path', 'detail': trail.original}],
            'button': 'Restore original',
        })

    @Slot(str, 'QVariantList')
    def prepareFileRevert(self, run, selected):
        if self.busy or run not in self.change_runs:
            return
        chosen = set(selected)
        rows = [row for row in self.fileChanges(run) if row['reversible'] and (not chosen or row['id'] in chosen)]
        if not rows:
            return
        self.pending = ('revert', (run, [int(row['id']) for row in rows]))
        count = len(rows)
        self.dialogRequested.emit({
            'kind': 'confirm', 'action': 'revert',
            'title': 'Revert 1 change' if count == 1 else f'Revert {count} changes',
            'text': ('Sortrr will restore original paths and names, or remove unchanged copies it created. '
                     'Edited files, occupied paths, and paths needed by newer changes are skipped.'),
            'rows': [{'label': row['label'] + '  |  ' + Path(row['source']).name,
                      'detail': row['target'] if row['mode'] == 'copy' else row['source']} for row in rows],
            'button': 'Revert changes',
        })

    @Slot(str)
    def prepare(self,action):
        if self.busy: return
        if action=='sort':
            self.prepareSort('visible')
        elif action=='rename':
            items=[self.items[i] for i in self.selected_visible() if self.items[i].chosen]
            if not items: self.toast.emit('Select identified files to rename.'); return
            for m in items: m.source=self.actual(m)
            def done(changes):
                self.pending=(action,items); self.dialogRequested.emit({'kind':'confirm','action':action,'title':'Rename in current folders','text':'Media, matching subtitles and assets follow the selected preset. Existing files are preserved.','rows':[{'label':c.source.name,'detail':c.target.name+(' - '+c.error if c.error else '')} for c in changes],'button':'Rename files'})
            self.work(lambda:core.plan_renames(items,self.options),done)
        elif action=='cleanup':
            if not self.source or not Path(self.source).is_dir(): self.toast.emit('Choose a source folder first.'); return
            root=Path(self.source).resolve(); output=Path(self.output()).resolve() if self.output() else None; excluded=[output] if output and output!=root else [root/'Movies',root/'TV Shows']
            def done(plan):
                possible_empty = core.cleanup_empty_folders(plan, {item.path for item in plan.files})
                if not plan.files and not possible_empty:
                    self.toast.emit('No cleanup candidates or empty folders were found in the source.')
                    return
                self.pending = (action, plan)
                rows = [{'label': str(item.path.relative_to(plan.root)), 'detail': item.category,
                         'path': str(item.path), 'checked': item.recommended} for item in plan.files]
                self.dialogRequested.emit({
                    'kind': 'confirm', 'action': action, 'title': 'Review source cleanup',
                    'text': ('Selected items move to .sortrr-trash for recovery. '
                             'Sortrr preselects system junk and checksums. Archived files still use disk space.'),
                    'rows': rows, 'canRemoveEmpty': bool(possible_empty), 'button': 'Archive selected items',
                })
            self.work(lambda:core.plan_cleanup(root,excluded),done)
        elif action in {'undo','clear'}:
            self.pending=(action,None); self.dialogRequested.emit({'kind':'confirm','action':action,'title':'Undo last operation' if action=='undo' else 'Clear identification cache','text':'Restore unchanged moved, renamed and cleaned files; remove unchanged copies. Occupied paths are preserved.' if action=='undo' else 'Forget saved progress, matches, skips, reject marks, API responses and artwork. Media and file change history are preserved.','rows':[],'button':'Undo operation' if action=='undo' else 'Clear cache'})
    @Slot()
    def cancelPlan(self):
        self.pending = None

    @Slot(str,'QVariantList',bool)
    def confirm(self,action,paths,remove_empty):
        if self.busy or not self.pending or self.pending[0]!=action: return
        payload=self.pending[1]; self.pending=None
        def job():
            if action == 'sort':
                items, output, source, mode, options, auto_cleanup, reject_paths, reject_root = payload
                journal = None
                messages = []
                if items:
                    result, journal = core.sort_and_finish(
                        items, output, source, mode, options, auto_cleanup,
                        lambda text: self.invoke.emit(lambda text=text: self.progress(text)),
                    )
                    verb = 'Moved' if mode == 'move' else 'Copied'
                    message = f"{verb} {result['sorted']} of {len(items)} planned files."
                    if result['sorted'] < len(items):
                        message += ' See Review files for individual outcomes.'
                    if auto_cleanup:
                        cleanup = result['cleanup']
                        message += f" Archived {cleanup['files']} junk files and removed {cleanup['folders']} empty folders."
                        if cleanup['skipped']:
                            message += f" Skipped {len(cleanup['skipped'])} cleanup items."
                        if result['warnings']:
                            message += ' ' + ' '.join(result['warnings'])
                    messages.append(message)
                outcomes = []
                if reject_paths:
                    outcomes, journal = core.dispose_rejects(reject_paths, source, reject_root, self.recycle_file, journal)
                    failures = [error for _, _, error in outcomes if error]
                    action_label = 'Moved to the reject folder' if reject_root else 'Sent to the Recycle Bin'
                    messages.append(f'{action_label}: {len(outcomes) - len(failures)} of {len(outcomes)} rejected files.')
                    if failures:
                        messages.append(f'{len(failures)} remain in place. First issue: {failures[0]}')
                return journal, ' '.join(messages), outcomes
            if action=='rename':
                for m in payload: m.status='Ready'
                count,journal=core.organize(payload,self.output() or self.source,mode='rename',options=self.options)
                return journal,f'Renamed {count} media files and matching companions.'
            if action=='cleanup':
                result,journal=core.apply_cleanup(payload,set(Path(p) for p in paths),remove_empty)
                return journal,f"Archived {result['files']} files; removed {result['folders']} empty folders; {len(result['skipped'])} skipped."
            if action == 'restore-original':
                try:
                    trail = core.restore_original_file(payload)
                except (OSError, ValueError) as exc:
                    return None, f'Restore stopped. {exc}'
                return None, f'Restored {Path(trail.original).name} to its original location.'
            if action in {'undo', 'revert'}:
                journals = core.change_journals()
                if action == 'revert':
                    name, selected = payload
                    journal = core.DATA / name
                    if journal not in journals:
                        raise ValueError('The selected operation log is unavailable.')
                else:
                    selected = None
                    journal = next((path for path in journals if core.read_file_changes(path)), None)
                    if journal is not None and not any(c.reversible for c in core.read_file_changes(journal)):
                        return None, 'No reversible changes in the latest operation. Open Change history to choose an older one.'
                if journal is None:
                    return None, 'No operation to revert.'
                count, skipped = core.revert_file_changes(journal, selected)
                message = f'Reverted {count} of {count + len(skipped)} changes.'
                if skipped:
                    message += f' Skipped {len(skipped)}. ' + (next(iter(skipped.values())) if action == 'undo'
                                                              else 'See the affected rows for details.')
                return journal, message, (selected, skipped)
            core.History().clear(); self.catalog.clear_cache(); self.art.clear()
            (core.DATA / 'progress.json').unlink(missing_ok=True)
            for m in self.items:
                if m.status not in {core.REJECT_MOVED, core.REJECT_RECYCLED}:
                    m.chosen=None; m.candidates=[]; m.runtime_check={}; m.cached=False; m.status='Not identified'
            return None,'Cache cleared. Scan to identify files again.'
        def done(result):
            journal,text,*extra=result
            if action == 'sort':
                for media, target, error in extra[0]:
                    if not error:
                        media.status = core.REJECT_MOVED if target else core.REJECT_RECYCLED
                        media.organized_path = target
            if action=='sort': self.last_sort=text
            if action=='clear': self.saved_progress=None
            if action in {'undo', 'revert', 'restore-original'}:
                self.last_sort=''
                self.epoch+=1; self.selected.clear(); self.thumbs.clear(); self.thumb_requested.clear(); self.model.reset()
                text+=' Scan again to refresh the library.'
            self.status=text; self.all_changed()
            if action == 'revert':
                selected, skipped = extra[0]
                errors = self.change_errors.setdefault(journal.name, {})
                for index in selected:
                    errors.pop(index, None)
                errors.update(skipped)
            if action in {'revert', 'restore-original'}:
                self.loadChangeHistory()
        self.save(); self.work(job,done,mutation=action in {'sort','rename','cleanup','undo','revert','restore-original'})
    def progress(self,text): self.status=text; self.all_changed(); self.notify()
    @Slot(int)
    def openLocation(self,uid):
        if 0<=uid<len(self.items): QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.actual(self.items[uid]).parent)))
    @Slot(int)
    def openWizard(self,uid=-1):
        if self.busy or uid >= len(self.items):
            return
        if uid >= 0 and self.items[uid].status in {core.REJECT_MOVED, core.REJECT_RECYCLED}:
            return
        unmatched = [i for i in self.visible_ids() if core.unresolved_media([self.items[i]])]
        if uid < 0 and not unmatched:
            self.toast.emit('No unresolved files in this view.')
            return
        self.wqueue = uid < 0 or uid in unmatched
        self.wids = unmatched if self.wqueue else [uid]
        self.windex = self.wids.index(uid) if uid in self.wids else 0
        self.wdrafts = {}
        self.wdeferred = set()
        self.show_step()

    def show_step(self):
        self.detail_generation += 1
        if self.detail_future:
            self.detail_future.cancel()
        self.player.stop()
        self.player.setSource(QUrl())
        self.frame_ready = False
        resolved = sum(bool(self.items[i].chosen) for i in self.wids)
        count = len(self.wids)
        if self.windex >= count:
            self.w = {'open': True, 'complete': True, 'queue': self.wqueue,
                      'index': count, 'count': count, 'resolved': resolved,
                      'rejectedCount': sum(self.items[i].status == core.REJECTED for i in self.wids)}
            self.wizardChanged.emit()
            return
        uid = self.wids[self.windex]
        media = self.items[uid]
        media.source = self.actual(media)
        draft = self.wdrafts.get(uid, {})
        candidates = draft.get('candidates', list(media.candidates))
        if media.chosen and not candidates:
            candidates = [media.chosen]
        selected = next((i for i, candidate in enumerate(candidates) if candidate == media.chosen), 0)
        path = media.source.absolute()
        unsupported = media.status.startswith('Unsupported')
        entry = {
            'open': True, 'complete': False, 'queue': self.wqueue, 'uid': uid,
            'index': self.windex, 'count': count, 'resolved': resolved, 'deferred': uid in self.wdeferred,
            'fileStatus': media.status, 'rejected': media.status == core.REJECTED, 'file': path.name, 'path': str(path),
            'query': draft.get('query', media.query), 'year': draft.get('year', media.year),
            'searchOpen': draft.get('searchOpen'),
            'manualMode': draft.get('manualMode', (media.chosen or {}).get('provider') == 'Manual'),
            'kind': draft.get('kind', media.kind), 'season': draft.get('season', media.season if media.season is not None else 1),
            'episode': draft.get('episode', media.episode or 1), 'candidates': candidates,
            'chosen': draft.get('chosen', selected) if candidates else -1, 'busy': False,
            'details': {}, 'poster': '', 'frame': '', 'metadata': [], 'timeline': [],
            'timelineLoading': True, 'previewIndex': -1,
            'unsupported': unsupported,
            'message': 'Correct the unsupported filename and rescan, or skip this file.' if unsupported else '',
        }
        if media.signature:
            entry['metadata'] = [QLocale.system().formattedDataSize(media.signature[0])]
        self.w = entry
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.wizardChanged.emit()
        self.load_wizard_timeline(path, entry)
        if not entry['manualMode'] and 0 <= entry['chosen'] < len(candidates):
            self.chooseCandidate(entry['chosen'])

    def load_wizard_timeline(self, path, entry):
        # One frame per active entry is queued at a time. Navigation discards stale callbacks.
        fractions = (0.02, 0.20, 0.40, 0.60, 0.80, 0.96)

        def request_frame(index):
            if self.closed or self.w is not entry:
                return
            if index == len(fractions):
                entry['timelineLoading'] = False
                if not any(frame['url'] for frame in entry['timeline']):
                    entry['previewMessage'] = 'Timeline thumbnails unavailable. Try playing the file.'
                self.wizardChanged.emit()
                return

            def frame_ready(frame, error):
                if self.w is not entry:
                    return
                if frame:
                    url = QUrl.fromLocalFile(str(frame.path)).toString()
                    entry['timeline'][index] = {
                        'url': url, 'time': timestamp(frame.seconds), 'position': round(frame.seconds * 1000),
                    }
                    if not entry['frame']:
                        entry['frame'] = url
                    self.wizardChanged.emit()
                request_frame(index + 1)

            if not self.previews.request(path, frame_ready, size=(240, 135), fraction=fractions[index]):
                QTimer.singleShot(160, lambda: request_frame(index))

        def probe_ready(info, error):
            if self.w is not entry:
                return
            if not info or not info['duration']:
                entry['timelineLoading'] = False
                entry['previewMessage'] = 'Could not read a timeline. Try playing the file.'
            if info:
                metadata = entry['metadata']
                if info['duration']:
                    metadata.insert(0, timestamp(info['duration']))
                if info.get('width') and info.get('height'):
                    metadata.append(f"{info['width']} × {info['height']}")
                if info.get('codec'):
                    metadata.append(info['codec'].upper())
                tracks = len(info['audio_tracks'])
                metadata.append(f"{tracks} audio track" + ('s' if tracks != 1 else ''))
                if info['duration']:
                    entry['timeline'] = [
                        {'url': '', 'time': timestamp(fraction * info['duration'])}
                        for fraction in fractions
                    ]
            self.wizardChanged.emit()
            if entry['timeline']:
                request_frame(0)

        def request_probe():
            if not self.closed and self.w is entry:
                if not self.previews.request_probe(path, probe_ready):
                    QTimer.singleShot(160, request_probe)

        request_probe()

    @Slot()
    def copyWizardPath(self):
        if self.w.get('path'):
            QGuiApplication.clipboard().setText(self.w['path'])

    @Slot(int)
    def previewWizardFrame(self, index):
        frames = self.w.get('timeline', [])
        if not 0 <= index < len(frames) or not frames[index]['url']:
            return
        frame = frames[index]
        self.w['previewIndex'] = index
        self.w['frame'] = frame['url']
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.frame_ready = False
        self.w['pendingSeek'] = frame['position']
        self.apply_wizard_seek(self.player.isSeekable())
        self.playbackChanged.emit()
        self.wizardChanged.emit()

    def apply_wizard_seek(self, seekable):
        if seekable and 'pendingSeek' in self.w:
            self.player.setPosition(self.w.pop('pendingSeek'))

    def draft(self):
        if not self.w.get('complete') and 'uid' in self.w: self.wdrafts[self.w['uid']]={k:self.w.get(k) for k in ('query','year','kind','season','episode','candidates','chosen','searchOpen','manualMode')}
    @Slot(str,str,str,int,int)
    def updateWizard(self,q,y,k,s,e):
        if self.w.get('busy') or self.w.get('complete'): return
        changed=self.w.get('kind')!=k; episode_changed=(self.w.get('season'),self.w.get('episode'))!=(s,e); self.w.update(query=q.strip(),year=y.strip(),kind=k,season=s,episode=e)
        if changed: self.w.update(candidates=[],details={},poster='',runtime='',chosen=-1); self.detail_generation+=1
        self.draft(); self.wizardChanged.emit()
        if not self.w.get('manualMode') and not changed and k=='TV' and episode_changed: self.chooseCandidate(self.w.get('chosen',-1))
    @Slot()
    def searchWizard(self):
        if self.w.get('busy') or not self.w.get('query') or self.w.get('unsupported') or self.w.get('manualMode'): return
        m=self.items[self.w['uid']]; request=core.Media(m.source,self.w['query'],self.w['year'],0 if self.w['kind']=='TV' else None,1 if self.w['kind']=='TV' else None)
        self.w['busy']=True; self.w['message']='Searching '+core.History.provider(request)+'...'; self.wizardChanged.emit(); uid=self.w['uid']
        def wrapped():
            try:
                with self.catalog.fresh(): results=self.catalog.search(request)
                return results,None
            except Exception as exc: return [],str(exc)
        def done(result):
            if self.w.get('uid')!=uid: return
            results,error=result; self.w.update(busy=False,candidates=results,chosen=0 if results else -1,details={},poster='',runtime='',message=error or ('Select the result that matches the source file.' if results else 'No results. Try another title or media type.')); self.draft(); self.wizardChanged.emit()
            if results: self.chooseCandidate(0)
        self.work(wrapped,done)
    @Slot(int)
    def chooseCandidate(self,index):
        candidates=self.w.get('candidates',[])
        if not 0<=index<len(candidates): return
        self.w['chosen']=index; candidate=dict(candidates[index]); self.detail_generation+=1; generation=self.detail_generation; kind=self.w['kind']; season=self.w['season']; episode=self.w['episode']; path=self.items[self.w['uid']].source
        self.w.update(runtime='Checking runtime...', runtimeResult={})
        self.w['details']={'title':candidate['title'],'info':core.entry_info_text(candidate),'provider':candidate.get('provider',''),'url':''}; self.w['poster']=''; self.w['detailLoading']=True; self.draft(); self.wizardChanged.emit()
        if self.detail_future: self.detail_future.cancel()
        def apply(data,error=None):
            if generation!=self.detail_generation or not self.w.get('open'): return
            self.w['detailLoading']=False
            if data: self.w['details']={'title':data.get('title') or data.get('name',candidate['title']),'info':core.entry_info_text(data),'provider':data.get('provider',''),'url':data.get('entry_url','')}
            elif error: self.w['details']['info']+='\n\nDetails unavailable: '+error
            self.wizardChanged.emit()
        def job():
            try: data=self.catalog.entry_details(candidate,kind)
            except Exception as exc: data={}; self.invoke.emit(lambda error=str(exc):apply(None,error))
            if data: self.invoke.emit(lambda:apply(data))
            try:
                url=self.catalog.poster_url(data); poster=self.art.poster(url) if url else None
            except Exception: poster=None
            def artwork():
                if generation==self.detail_generation and self.w.get('open'):
                    self.w['poster']=QUrl.fromLocalFile(str(poster)).toString() if poster else ''; self.wizardChanged.emit()
            self.invoke.emit(artwork)
            result=self.measure_runtime(path,candidate,kind,season,episode)
            def runtime_ready():
                if generation==self.detail_generation and self.w.get('open'):
                    self.w['runtime']=result['label']
                    self.w['runtimeResult']={**result,'key':runtime_key(candidate,kind,season if kind=='TV' else None,episode if kind=='TV' else None)}
                    self.wizardChanged.emit()
            self.invoke.emit(runtime_ready)
        self.detail_future=self.details_pool.submit(job)
    @Slot(int)
    def wizardMove(self,delta):
        if self.w.get('busy') or not self.w.get('open') or not self.wqueue:
            return
        index = self.windex + delta
        if 0 <= index < len(self.wids):
            self.draft()
            self.windex = index
            self.show_step()

    def advance_wizard(self):
        self.draft()
        pending = [
            i for i in range(len(self.wids))
            if self.wids[i] not in self.wdeferred and core.unresolved_media([self.items[self.wids[i]]])
        ]
        self.windex = next((i for i in pending if i > self.windex), pending[0] if pending else len(self.wids))
        self.show_step()

    @Slot()
    def skipWizard(self):
        if not self.w.get('open') or self.w.get('complete') or self.w.get('busy') or not self.wqueue:
            return
        self.wdeferred.add(self.w['uid'])
        self.advance_wizard()
    @Slot()
    def toggleWizardReject(self):
        if not self.w.get('open') or self.w.get('complete') or self.w.get('busy'):
            return
        media = self.items[self.w['uid']]
        was_rejected = media.status == core.REJECTED
        if was_rejected:
            status = 'Choose match' if media.candidates else 'No match'
        else:
            status = core.REJECTED
        try:
            source_root = Path(self.source).expanduser().resolve()
            core.source_boundary(media.source, source_root)
            stat = media.source.stat()
            if (stat.st_size, stat.st_mtime_ns) != media.signature:
                raise ValueError('File changed. Scan again before updating its reject status.')
            if was_rejected:
                parsed = core.parse(media.source)
                if parsed.status.startswith('Unsupported'):
                    status = parsed.status
            candidates = media.candidates or ([media.chosen] if media.chosen else [])
            decision = replace(media, chosen=None, status=status, runtime_check={}, candidates=candidates)
            if not core.History().save(decision):
                raise ValueError('File changed. Scan again before updating its reject status.')
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.w['message'] = str(exc)
            self.wizardChanged.emit()
            return
        media.chosen = None
        media.runtime_check = {}
        media.candidates = candidates
        media.status = status
        self.model.changed(self.w['uid'])
        self.status = ('Returned to review: ' if was_rejected else 'Marked as rejected: ') + media.source.name
        self.notify()
        if was_rejected:
            self.w.update(rejected=False, fileStatus=status, unsupported=status.startswith('Unsupported'),
                          message='Returned to review.')
            self.wizardChanged.emit()
        elif self.wqueue:
            self.advance_wizard()
        else:
            self.closeWizard()

    @Slot(bool)
    def setWizardManualMode(self, manual):
        if (not self.w.get('open') or self.w.get('complete') or self.w.get('busy')
                or self.w.get('unsupported') or self.w.get('rejected')):
            return
        self.w.update(manualMode=manual, message='')
        if manual:
            self.detail_generation += 1
            if self.detail_future:
                self.detail_future.cancel()
        else:
            candidates = self.w.get('candidates', [])
            if any(candidate.get('provider') == 'Manual' for candidate in candidates):
                candidates = [candidate for candidate in candidates if candidate.get('provider') != 'Manual']
                self.w.update(candidates=candidates, chosen=0 if candidates else -1)
            self.chooseCandidate(self.w.get('chosen', -1))
        self.draft()
        self.wizardChanged.emit()

    @Slot(int, str, str, str, int, int, result='QVariantMap')
    def manualEntryPreview(self, uid, title, year, kind, season, episode):
        if not 0 <= uid < len(self.items):
            return {}
        try:
            entry = core.build_manual_entry(self.items[uid], title, year, kind, season, episode)
            root = Path(self.output()).expanduser() if self.output() else Path('.')
            return {'path': str(core.destination(entry, root, self.options))}
        except ValueError as exc:
            return {'error': str(exc)}

    @Slot()
    def acceptWizard(self):
        if not self.w.get('open') or self.w.get('busy') or self.w.get('complete') or self.w.get('rejected'):
            return
        media = self.items[self.w['uid']]
        query, year, kind = self.w['query'], self.w['year'], self.w['kind']
        season, episode = self.w['season'], self.w['episode']
        manual = self.w.get('manualMode', False)
        try:
            if manual:
                candidate = core.build_manual_entry(media, query, year, kind, season, episode).chosen
            else:
                index = self.w.get('chosen', -1)
                candidates = self.w.get('candidates', [])
                if not 0 <= index < len(candidates):
                    raise ValueError('Select a database result first.')
                candidate = candidates[index]
            core.resolve_manually(media, candidate, query, year, season, episode, kind)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.w['message'] = str(exc)
            self.wizardChanged.emit()
            return
        m = media
        if manual:
            self.w.update(candidates=m.candidates, chosen=0)
        runtime=self.w.get('runtimeResult',{})
        if runtime.get('key')==runtime_key(m.chosen,m.kind,m.season,m.episode) and runtime.get('status') in {'Matches','Differs'}:
            m.runtime_check=runtime
            try: core.History().save(m)
            except OSError: log.exception('Could not save runtime check')
        if self.output():
            self.recheck_match(m, Path(self.output()).expanduser(), core.History())
        self.model.changed(self.w['uid'])
        self.status = ('Saved manual entry for ' if manual else 'Saved match for ') + m.source.name
        if not self.wqueue:
            self.closeWizard()
            return
        self.notify()
        self.wdeferred.discard(self.w['uid'])
        self.advance_wizard()

    @Slot()
    def closeWizard(self):
        self.draft(); self.detail_generation+=1; self.w={'open':False}; self.player.stop(); self.player.setSource(QUrl()); self.wizardChanged.emit(); self.notify()
    @Slot(QObject)
    def attachVideoSink(self,sink):
        self.player.setVideoSink(sink); sink.videoFrameChanged.connect(self.video_frame)
    def video_frame(self,frame):
        if frame.isValid() and not self.frame_ready: self.frame_ready=True; self.playbackChanged.emit()
    @Slot()
    def playPause(self):
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState: self.player.pause()
        else:
            self.ensure_audio_track()
            if self.player.duration() and self.player.position()>=self.player.duration()-100: self.player.setPosition(0)
            self.player.play()
    @Slot(int)
    def seek(self,value): self.player.setPosition(value)
    @Slot(float)
    def setVolume(self, value):
        self.audio.setVolume(max(0, min(1, value)))
        if value > 0 and self.audio.isMuted():
            self.audio.setMuted(False)

    @Slot(bool)
    def setMuted(self, value):
        if not value and self.audio.volume() == 0:
            self.audio.setVolume(.7)
        self.audio.setMuted(value)

    @Slot(int)
    def setAudioTrack(self, index):
        if 0 <= index < len(self.player.audioTracks()):
            self.player.setActiveAudioTrack(index)
    @Slot()
    def shutdown(self):
        if self.closed: return
        self.closed=True; self.player.stop(); self.player.setSource(QUrl()); self.previews.close(); self.ops.shutdown(wait=False,cancel_futures=True); self.details_pool.shutdown(wait=False,cancel_futures=True)
