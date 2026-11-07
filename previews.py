"""Local FFmpeg previews. Media is read only; Tk objects are created on the UI thread."""
import hashlib,json,os,queue,shutil,struct,subprocess,tempfile,threading,time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from audio_output import AudioPlayback
from app_paths import RESOURCES

@dataclass(frozen=True)
class Frame:
    path: Path
    seconds: float
    duration: float
    audio_tracks: tuple=()

def timestamp(value):
    seconds=max(0,int(value)); return f'{seconds//3600}:{seconds//60%60:02d}:{seconds%60:02d}'

def media_tool(name):
    bundled = RESOURCES / 'tools' / f'{name}.exe'
    return str(bundled) if bundled.is_file() else shutil.which(name)


class PreviewManager:
    def __init__(self,cache,dispatch):
        self.cache=Path(cache); self.dispatch=dispatch
        self.ffmpeg=media_tool('ffmpeg'); self.ffprobe=media_tool('ffprobe')
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='sortrr-preview')
        self.lock=threading.RLock(); self.pending={}; self.processes=set(); self.closed=False
        self.probe_locks={}
    @property
    def available(self): return bool(self.ffmpeg and self.ffprobe)
    def identity(self,path):
        path=Path(path).resolve(); st=path.stat()
        if not path.is_file(): raise ValueError('Preview source is not a file')
        key=hashlib.sha256(json.dumps([str(path),st.st_size,st.st_mtime_ns]).encode()).hexdigest()
        return path,key
    def spawn(self,args,**kwargs):
        with self.lock:
            if self.closed: raise RuntimeError('Preview service closed')
            proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)
            self.processes.add(proc); return proc
    def release(self,proc):
        if proc.poll() is None:
            try: proc.kill()
            except OSError: pass
        proc.wait(timeout=5)
        if proc.stdout: proc.stdout.close()
        if proc.stderr: proc.stderr.close()
        with self.lock: self.processes.discard(proc)
    def run(self,args,timeout=18):
        proc=self.spawn(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            try: out,error=proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.communicate(); raise RuntimeError('Video preview timed out')
            if proc.returncode: raise RuntimeError(error.decode('utf-8','replace')[-500:].strip() or 'Video cannot be decoded')
            return out
        finally: self.release(proc)
    def atomic(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.tmp',delete=False) as out:
            temporary=Path(out.name); out.write(data)
        try: os.replace(temporary,path)
        finally: temporary.unlink(missing_ok=True)
    def probe(self,path):
        if not self.available: raise RuntimeError('Install FFmpeg and ffprobe to enable video previews')
        path,key=self.identity(path); folder=self.cache/key
        with self.lock: lock=self.probe_locks.setdefault(key,threading.Lock())
        with lock:
            cached=folder/'probe.json'
            try:
                data=json.loads(cached.read_text())
                if data.get('version')==3 and isinstance(data['index'],int) and data['duration']>=0: return path,folder,data
            except (OSError,ValueError,KeyError,TypeError): pass
            raw=json.loads(self.run([self.ffprobe,'-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration:stream=index,codec_type,duration,codec_name,width,height,channels:stream_tags=language,title:stream_disposition=attached_pic,default','-of','json',str(path)]))
            videos=[v for v in raw.get('streams',[]) if v.get('codec_type')=='video' and not v.get('disposition',{}).get('attached_pic')]
            if not videos: raise RuntimeError('No playable video track')
            duration = 0
            for value in (videos[0].get('duration'), raw.get('format', {}).get('duration')):
                try:
                    seconds = float(value)
                except (TypeError, ValueError):
                    continue
                if 0 < seconds < 1e8:
                    duration = seconds
                    break
            audio=[]
            for track in raw.get('streams',[]):
                if track.get('codec_type')!='audio': continue
                tags=track.get('tags',{}); language=tags.get('language','und')
                label=f"{track['index']}: {language} / {track.get('codec_name','audio')} / {track.get('channels','?')}ch"
                if tags.get('title'): label+=' / '+tags['title']
                audio.append({'index':track['index'],'label':label,'default':bool(track.get('disposition',{}).get('default'))})
            video=videos[0]
            data={
                'version':3, 'index':video['index'], 'duration':duration, 'audio_tracks':audio,
                'width':video.get('width'), 'height':video.get('height'),
                'codec':video.get('codec_name',''),
            }
            self.atomic(cached,json.dumps(data).encode()); return path,folder,data
    @staticmethod
    def filters(size):
        width,height=size
        if not 16<=width<=1280 or not 16<=height<=720: raise ValueError('Invalid preview size')
        return f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1'
    def frame(self,path,fraction=.1,size=(96,54),seconds=None):
        path,folder,info=self.probe(path); duration=info['duration']
        seek=max(0,float(seconds)) if seconds is not None else max(0,min(1,float(fraction)))*duration
        seek=round(min(seek,max(0,duration-.2)) if duration else 0,1)
        target=folder/f'frame-{size[0]}x{size[1]}-{seek:.1f}.png'
        def valid(raw):
            return len(raw)>32 and raw.startswith(b'\x89PNG\r\n\x1a\n') and struct.unpack('>II',raw[16:24])==size and raw.endswith(b'IEND\xaeB`\x82')
        try:
            if valid(target.read_bytes()): return Frame(target,seek,duration,tuple(info.get('audio_tracks',[])))
        except OSError: pass
        args=[self.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-threads','1','-protocol_whitelist','file,pipe','-ss',str(seek),'-i',str(path),'-map',f'0:{info["index"]}','-an','-sn','-frames:v','1','-vf',self.filters(size),'-threads','1','-f','image2pipe','-vcodec','png','pipe:1']
        raw=self.run(args)
        if not valid(raw): raise RuntimeError('No preview frame at this position')
        self.atomic(target,raw)
        # Bound seek-cache growth within each source fingerprint directory.
        def modified(path):
            try: return path.stat().st_mtime
            except OSError: return 0
        frames=sorted(folder.glob('frame-*.png'),key=modified,reverse=True)
        for old in frames[80:]:
            try: old.unlink()
            except OSError: pass
        return Frame(target,seek,duration,tuple(info.get('audio_tracks',[])))
    def request(self,path,callback,**kwargs):
        return self._request(path,callback,tuple(sorted(kwargs.items())),lambda path:self.frame(path,**kwargs))

    def request_probe(self,path,callback):
        return self._request(path,callback,'probe',lambda path:self.probe(path)[2])

    def _request(self,path,callback,request_key,load):
        try: _,identity=self.identity(path)
        except (OSError,ValueError) as exc:
            self.dispatch(lambda error=str(exc):callback(None,error)); return True
        key=(identity,request_key)
        with self.lock:
            if self.closed: return False
            future=self.pending.get(key)
            if future is None:
                if len(self.pending)>=12: return False
                future=self.pool.submit(load,path); self.pending[key]=future
                def remove(done):
                    with self.lock: self.pending.pop(key,None)
                future.add_done_callback(remove)
        def finished(done):
            try: result,error=done.result(),None
            except Exception as exc: result,error=None,str(exc)
            with self.lock:
                if self.closed: return
            self.dispatch(lambda:callback(result,error))
        future.add_done_callback(finished); return True
    def stream(self,path,seconds,size,stop,attach,emit,clock=None,gate=None):
        proc=None
        try:
            path,folder,info=self.probe(path)
            if stop.is_set(): return
            args=[self.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-threads','1','-protocol_whitelist','file,pipe','-ss',str(seconds)]+([] if clock else ['-re'])+['-i',str(path),'-map',f'0:{info["index"]}','-an','-sn','-vf','fps=8,'+self.filters(size),'-threads','1','-f','image2pipe','-vcodec','ppm','pipe:1']
            proc=self.spawn(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL); attach(proc)
            number=0
            def token():
                value=b''
                while len(value)<32:
                    c=proc.stdout.read(1)
                    if not c: return value
                    if c.isspace():
                        if value: return value
                    else: value+=c
                raise RuntimeError('Invalid preview frame header')
            while not stop.is_set():
                magic=token()
                if not magic: break
                width,height,maximum=int(token()),int(token()),int(token())
                if magic!=b'P6' or (width,height)!=size or maximum!=255: raise RuntimeError('Unexpected preview frame')
                count=width*height*3; raw=bytearray()
                while len(raw)<count:
                    block=proc.stdout.read(count-len(raw))
                    if not block: break
                    raw.extend(block)
                if len(raw)!=count: break
                if clock and number:
                    while not stop.is_set() and clock()<number/8: stop.wait(.005)
                if stop.is_set(): break
                emit(b'P6\n'+f'{width} {height}\n255\n'.encode()+raw,seconds+number/8,None)
                if number==0 and gate:
                    while not stop.is_set() and not gate.wait(.03): pass
                number+=1
            if clock:
                while not stop.is_set() and clock()<number/8: stop.wait(.005)
            if not stop.is_set(): emit(None,seconds+number/8,'Playback finished')
        except Exception as exc:
            if not stop.is_set(): emit(None,seconds,str(exc))
        finally:
            if proc: self.release(proc)
    def close(self,wait=False):
        with self.lock:
            self.closed=True; processes=list(self.processes)
        for proc in processes:
            try: proc.kill()
            except OSError: pass
        if wait:
            for proc in processes:
                try: proc.wait(timeout=3)
                except (OSError,subprocess.TimeoutExpired): pass
        self.pool.shutdown(wait=False,cancel_futures=True)

class VideoPreview(ttk.Frame):
    def __init__(self,parent,manager,size=(352,198)):
        super().__init__(parent,padding=(12,0,0,0)); self.manager=manager; self.size=size
        self.path=None; self.generation=0; self.duration=0; self.position=0; self.playing=False; self.process=None; self.stop_event=threading.Event(); self.frames=queue.Queue(maxsize=1); self.seek_timer=None; self.updating=False
        ttk.Label(self,text='Video preview',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,8))
        self.canvas=tk.Canvas(self,width=size[0],height=size[1],background='#182234',highlightthickness=0); self.canvas.pack()
        self.canvas.create_text(size[0]//2,size[1]//2,text='Select a file',fill='white',width=size[0]-20,tags='message')
        self.clock=tk.StringVar(value='0:00:00 / 0:00:00'); ttk.Label(self,textvariable=self.clock).pack(anchor='w',pady=(6,0))
        self.slider=ttk.Scale(self,from_=0,to=1,command=self.scrub); self.slider.pack(fill='x',pady=6)
        bar=ttk.Frame(self); bar.pack(fill='x')
        self.play_button=ttk.Button(bar,text='Play',command=self.play); self.play_button.pack(side='left')
        ttk.Button(bar,text='Open in player',command=self.open_player).pack(side='left',padx=6)
        self.audio=None; self.tracks=[]; self.first_frame=False; self.gate=threading.Event(); self.wall_start=None; self.audio_notice=False
        self.track_var=tk.StringVar(); self.volume_var=tk.DoubleVar(value=70); self.muted=tk.BooleanVar(value=False)
        sound=ttk.Frame(self); sound.pack(fill='x',pady=(7,0))
        self.track_box=ttk.Combobox(sound,textvariable=self.track_var,state='readonly',width=19); self.track_box.pack(side='left')
        self.track_box.bind('<<ComboboxSelected>>',self.change_track)
        ttk.Checkbutton(sound,text='Mute',variable=self.muted,command=self.volume_changed).pack(side='left',padx=4)
        ttk.Scale(sound,from_=0,to=100,variable=self.volume_var,command=self.volume_changed,length=75).pack(side='left')
        self.info=tk.StringVar(value='Drag the timeline to inspect the file.'); ttk.Label(self,textvariable=self.info,wraplength=size[0]).pack(anchor='w',pady=8)
        self.timer=self.after(60,self.poll); self.bind('<Destroy>',self.destroyed)
    def message(self,text):
        self.canvas.delete('all'); self.canvas.create_text(self.size[0]//2,self.size[1]//2,text=text,fill='white',width=self.size[0]-20)
    def stop(self):
        if self.audio:
            if self.audio.started is not None: self.position=max(self.position,self.play_start+self.audio.elapsed())
            self.audio.stop(); self.audio=None
        self.gate.set()
        self.generation+=1; self.stop_event.set(); self.playing=False
        if self.play_button.winfo_exists(): self.play_button.configure(text='Play')
        if self.process:
            try: self.process.kill()
            except OSError: pass
            self.process=None
        if self.seek_timer: self.after_cancel(self.seek_timer); self.seek_timer=None
    def load(self,path):
        self.stop(); self.path=Path(path) if path else None; self.duration=0; self.position=0
        self.tracks=[]; self.track_var.set(''); self.track_box.configure(values=())
        self.clock.set('0:00:00 / 0:00:00'); self.message('Loading preview...' if path else 'Review complete')
        if path: self.still(fraction=.05)
    def still(self,**kwargs):
        generation=self.generation
        def done(frame,error):
            if not self.winfo_exists() or generation!=self.generation: return
            if error: self.message('Preview unavailable'); self.info.set(error); return
            try: self.image=tk.PhotoImage(file=str(frame.path)); self.draw(self.image)
            except (tk.TclError,OSError): self.message('Preview unavailable'); return
            self.duration=frame.duration; self.position=frame.seconds; self.slider.configure(to=max(1,self.duration)); self.update_clock()
            if self.tracks!=list(frame.audio_tracks):
                self.tracks=list(frame.audio_tracks)
                self.track_box.configure(values=[track['label'] for track in self.tracks])
                track=next((track for track in self.tracks if track['default']),self.tracks[0] if self.tracks else None)
                self.track_var.set(track['label'] if track else 'No audio track')
            self.track_box.state(['!disabled','readonly'] if self.tracks else ['disabled'])
            self.info.set('Play includes the selected audio track. Adjust volume or mute.' if self.tracks else 'This file has no audio track.')
        if not self.manager.request(self.path,done,size=self.size,**kwargs): self.info.set('Previews are busy. Try seeking again shortly.')
    def draw(self,image):
        self.canvas.delete('all'); self.canvas.create_image(0,0,anchor='nw',image=image)
    def update_clock(self):
        self.clock.set(timestamp(self.position)+' / '+timestamp(self.duration)); self.updating=True
        try: self.slider.set(self.position)
        finally: self.updating=False
    def scrub(self,value):
        if self.updating or self.path is None or not self.duration: return
        self.stop(); self.position=float(value); self.clock.set(timestamp(self.position)+' / '+timestamp(self.duration))
        self.seek_timer=self.after(180,lambda:self.still(seconds=self.position))
    def play(self):
        if self.playing: self.stop(); self.update_clock(); return
        if not self.path: return
        self.stop(); self.playing=True; self.play_button.configure(text='Pause'); self.stop_event=threading.Event(); generation=self.generation
        stop_event=self.stop_event
        def attach(proc):
            if stop_event.is_set() or generation!=self.generation: proc.kill()
            else: self.process=proc
        self.first_frame=False; self.gate=threading.Event(); self.wall_start=None; self.audio_notice=False; self.play_start=self.position
        selected=next((track for track in self.tracks if track['label']==self.track_var.get()),None)
        if selected: self.audio=AudioPlayback(self.manager,self.path,self.position,selected['index'],0 if self.muted.get() else self.volume_var.get())
        audio=self.audio
        def clock(): return audio.elapsed() if audio else (time.monotonic()-self.wall_start if self.wall_start is not None else 0)
        def emit(frame,seconds,error):
            try: self.frames.get_nowait()
            except queue.Empty: pass
            try: self.frames.put_nowait((generation,frame,seconds,error))
            except queue.Full: pass
        threading.Thread(target=self.manager.stream,args=(self.path,self.position,self.size,self.stop_event,attach,emit,clock,self.gate),daemon=True).start()
    def poll(self):
        try:
            generation,raw,seconds,error=self.frames.get_nowait()
            if generation==self.generation:
                if raw:
                    self.first_frame=True
                    self.image=tk.PhotoImage(data=raw,format='PPM'); self.draw(self.image); self.position=seconds; self.update_clock()
                if error:
                    if self.audio: self.audio.stop(); self.audio=None
                    self.playing=False; self.play_button.configure(text='Play'); self.info.set(error)
        except queue.Empty: pass
        if self.playing and self.first_frame and not self.gate.is_set() and (self.audio is None or self.audio.ready.is_set()):
            try:
                if self.audio: self.audio.begin()
            except RuntimeError as exc:
                self.audio.stop(); self.audio=None; self.info.set('Audio unavailable: '+str(exc))
            self.wall_start=time.monotonic(); self.gate.set()
        if self.audio and self.audio.error and not self.audio_notice:
            self.info.set('Audio unavailable: '+self.audio.error); self.audio_notice=True
        self.timer=self.after(60,self.poll)
    def volume_changed(self,value=None):
        if self.audio:
            try: self.audio.volume(0 if self.muted.get() else self.volume_var.get())
            except RuntimeError as exc: self.info.set('Audio volume unavailable: '+str(exc))
    def change_track(self,event=None):
        playing=self.playing; self.stop()
        if playing: self.play()
    def open_player(self):
        if not self.path: return
        try:
            if os.name=='nt': os.startfile(str(self.path))
            else: subprocess.Popen(['xdg-open',str(self.path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as exc: self.info.set(str(exc))
    def destroyed(self,event):
        if event.widget!=self: return
        self.stop(); self.after_cancel(self.timer)

class HoverScrubber:
    def __init__(self,root,tree,manager,resolve):
        self.root=root; self.tree=tree; self.manager=manager; self.resolve=resolve
        self.window=None; self.timer=None; self.row=None; self.bucket=None; self.generation=0
        tree.bind('<Motion>',self.motion,add='+'); tree.bind('<Leave>',lambda event:self.hide(),add='+')
    def hide(self):
        self.generation+=1; self.row=None; self.bucket=None
        if self.timer: self.root.after_cancel(self.timer); self.timer=None
        if self.window: self.window.destroy(); self.window=None
    def motion(self,event):
        if self.manager.closed: self.hide(); return
        row=self.tree.identify_row(event.y)
        if not row or self.tree.identify_column(event.x)!='#0': self.hide(); return
        bucket=max(0,min(40,round(event.x/max(1,self.tree.column('#0','width'))*40)))
        if row==self.row and bucket==self.bucket: return
        if row!=self.row: self.hide(); self.row=row
        self.bucket=bucket; self.generation+=1; generation=self.generation
        if self.timer: self.root.after_cancel(self.timer)
        self.timer=self.root.after(180,lambda:self.show(row,bucket,generation,event.y_root))
    def show(self,row,bucket,generation,y):
        self.timer=None
        if generation!=self.generation: return
        try: path=self.resolve(row)
        except (OSError,IndexError,ValueError): return
        if not self.window:
            self.window=tk.Toplevel(self.root); self.window.overrideredirect(True)
            self.label=tk.Label(self.window,text='Loading preview...',width=45,height=12,background='#182234',foreground='white'); self.label.pack()
            self.caption=tk.Label(self.window,text='Move across the thumbnail to scrub',background='#f5f6fa'); self.caption.pack(fill='x')
            x=min(self.tree.winfo_rootx()+120,self.root.winfo_screenwidth()-330); y=min(y+14,self.root.winfo_screenheight()-235)
            self.window.geometry(f'+{max(0,x)}+{max(0,y)}')
        def done(frame,error):
            if generation!=self.generation or not self.window: return
            if error: self.label.configure(image='',text='Preview unavailable',width=45,height=12); return
            try: self.image=tk.PhotoImage(file=str(frame.path))
            except (tk.TclError,OSError): return
            self.label.configure(image=self.image,text='',width=320,height=180)
            self.caption.configure(text=timestamp(frame.seconds)+' / '+timestamp(frame.duration)+'  |  Move to scrub')
        self.manager.request(path,done,fraction=bucket/40,size=(320,180))
