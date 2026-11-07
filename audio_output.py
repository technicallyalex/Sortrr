"""Bounded PCM playback through Windows waveOut; no external player or Python dependency."""
import ctypes,os,subprocess,threading,time

class WaveFormat(ctypes.Structure):
    _fields_=[('format',ctypes.c_ushort),('channels',ctypes.c_ushort),('rate',ctypes.c_uint32),('bytes_per_second',ctypes.c_uint32),('alignment',ctypes.c_ushort),('bits',ctypes.c_ushort),('extra',ctypes.c_ushort)]
class WaveHeader(ctypes.Structure):
    _fields_=[('data',ctypes.c_void_p),('length',ctypes.c_uint32),('recorded',ctypes.c_uint32),('user',ctypes.c_size_t),('flags',ctypes.c_uint32),('loops',ctypes.c_uint32),('next',ctypes.c_void_p),('reserved',ctypes.c_size_t)]
class TimeValue(ctypes.Union):
    _fields_=[('samples',ctypes.c_uint32),('bytes',ctypes.c_uint32),('ms',ctypes.c_uint32),('padding',ctypes.c_ubyte*8)]
class MediaTime(ctypes.Structure):
    _fields_=[('type',ctypes.c_uint32),('value',TimeValue)]

class WaveOutput:
    RATE=48000
    def __init__(self,volume=70,api=None):
        if api is None:
            if os.name!='nt': raise RuntimeError('Embedded audio requires Windows')
            api=ctypes.WinDLL('winmm')
        self.api=api; self.lock=threading.RLock(); self.buffers=[]; self.closed=False; self.handle=ctypes.c_void_p()
        signatures={'waveOutOpen':[ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint32,ctypes.POINTER(WaveFormat),ctypes.c_size_t,ctypes.c_size_t,ctypes.c_uint32],
            'waveOutPrepareHeader':[ctypes.c_void_p,ctypes.POINTER(WaveHeader),ctypes.c_uint32],
            'waveOutWrite':[ctypes.c_void_p,ctypes.POINTER(WaveHeader),ctypes.c_uint32],
            'waveOutUnprepareHeader':[ctypes.c_void_p,ctypes.POINTER(WaveHeader),ctypes.c_uint32],
            'waveOutGetPosition':[ctypes.c_void_p,ctypes.POINTER(MediaTime),ctypes.c_uint32],
            'waveOutSetVolume':[ctypes.c_void_p,ctypes.c_uint32]}
        for name in ('waveOutPause','waveOutRestart','waveOutReset','waveOutClose'): signatures[name]=[ctypes.c_void_p]
        for name,args in signatures.items(): getattr(api,name).argtypes=args; getattr(api,name).restype=ctypes.c_uint32
        self.format=WaveFormat(1,2,self.RATE,self.RATE*4,4,16,0)
        self.check(api.waveOutOpen(ctypes.byref(self.handle),0xffffffff,ctypes.byref(self.format),0,0,0),'No usable audio output device')
        try: self.check(api.waveOutPause(self.handle),'Cannot pause audio output'); self.volume(volume)
        except Exception:
            api.waveOutClose(self.handle); raise
    @staticmethod
    def check(code,message):
        if code: raise RuntimeError(f'{message} (Windows audio error {code})')
    def reap(self):
        keep=[]
        for buffer,header in self.buffers:
            if header.flags&1: self.api.waveOutUnprepareHeader(self.handle,ctypes.byref(header),ctypes.sizeof(header))
            else: keep.append((buffer,header))
        self.buffers=keep
    def write(self,raw,stop):
        while not stop.is_set():
            with self.lock:
                if self.closed: return False
                self.reap()
                if len(self.buffers)<4:
                    if stop.is_set(): return False
                    buffer=ctypes.create_string_buffer(raw); header=WaveHeader()
                    header.data=ctypes.cast(buffer,ctypes.c_void_p); header.length=len(raw)
                    self.check(self.api.waveOutPrepareHeader(self.handle,ctypes.byref(header),ctypes.sizeof(header)),'Cannot prepare audio')
                    self.buffers.append((buffer,header))
                    self.check(self.api.waveOutWrite(self.handle,ctypes.byref(header),ctypes.sizeof(header)),'Cannot play audio')
                    return True
            stop.wait(.01)
        return False
    def begin(self):
        with self.lock:
            if not self.closed: self.check(self.api.waveOutRestart(self.handle),'Cannot start audio')
    def position(self):
        with self.lock:
            if self.closed: return 0
            value=MediaTime(); value.type=2
            self.check(self.api.waveOutGetPosition(self.handle,ctypes.byref(value),ctypes.sizeof(value)),'Cannot read audio position')
            if value.type==2: return value.value.samples/self.RATE
            if value.type==4: return value.value.bytes/(self.RATE*4)
            if value.type==1: return value.value.ms/1000
            raise RuntimeError('Audio device does not expose its playback position')
    def volume(self,volume):
        with self.lock:
            if not self.closed:
                level=round(max(0,min(100,float(volume)))*65535/100)
                self.check(self.api.waveOutSetVolume(self.handle,level|(level<<16)),'Cannot set volume')
    def drain(self,stop):
        while not stop.is_set():
            with self.lock:
                self.reap()
                if not self.buffers: return
            stop.wait(.01)
    def abort(self):
        with self.lock:
            if not self.closed: self.api.waveOutReset(self.handle)
    def close(self):
        with self.lock:
            if self.closed: return
            self.api.waveOutReset(self.handle)
            for buffer,header in self.buffers: self.api.waveOutUnprepareHeader(self.handle,ctypes.byref(header),ctypes.sizeof(header))
            self.api.waveOutClose(self.handle); self.buffers.clear(); self.closed=True

def pcm_command(ffmpeg,path,seconds,index):
    return [ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-threads','1','-protocol_whitelist','file,pipe','-ss',str(seconds),'-i',str(path),'-map',f'0:{index}','-vn','-sn','-af','aresample=async=1:first_pts=0','-ac','2','-ar','48000','-f','s16le','pipe:1']

class AudioPlayback:
    def __init__(self,manager,path,seconds,index,volume=70):
        self.manager=manager; self.path=path; self.seconds=seconds; self.index=index; self.level=volume
        self.stop_event=threading.Event(); self.ready=threading.Event(); self.lock=threading.RLock()
        self.sink=None; self.proc=None; self.error=None; self.started=None; self.finished=None; self.final_position=0
        self.thread=threading.Thread(target=self.run,name='sortrr-audio',daemon=True); self.thread.start()
    def run(self):
        sink=None; proc=None
        try:
            sink=WaveOutput(self.level)
            with self.lock: self.sink=sink
            args=pcm_command(self.manager.ffmpeg,self.path,self.seconds,self.index)
            if self.stop_event.is_set(): return
            proc=self.manager.spawn(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            with self.lock: self.proc=proc
            if self.stop_event.is_set(): proc.kill(); return
            while not self.stop_event.is_set():
                raw=proc.stdout.read(9600)
                if not raw: break
                raw=raw[:len(raw)//4*4]
                if raw and sink.write(raw,self.stop_event): self.ready.set()
            if not self.stop_event.is_set():
                if proc.wait(timeout=5): raise RuntimeError('The selected audio track could not be decoded')
                self.ready.set(); sink.drain(self.stop_event)
                with self.lock: self.final_position=sink.position(); self.finished=time.monotonic()
        except Exception as exc:
            self.error=str(exc)
            with self.lock:
                if self.started is not None: self.final_position=max(0,time.monotonic()-self.started)
                self.finished=time.monotonic()
        finally:
            self.ready.set()
            with self.lock:
                if sink: sink.close()
                self.sink=None
            if proc: self.manager.release(proc)
    def begin(self):
        with self.lock:
            self.started=time.monotonic()
            if self.sink: self.sink.volume(self.level); self.sink.begin()
    def elapsed(self):
        with self.lock:
            if self.started is None: return 0
            if self.finished is not None: return self.final_position+max(0,time.monotonic()-max(self.finished,self.started))
            if self.sink:
                try: return self.sink.position()
                except RuntimeError: pass
            return max(0,time.monotonic()-self.started)
    def volume(self,level):
        with self.lock:
            self.level=level
            if self.sink: self.sink.volume(level)
    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.proc:
                try: self.proc.kill()
                except OSError: pass
            if self.sink: self.sink.abort()
