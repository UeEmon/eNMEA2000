"""Software-only NMEA to paced RTL-TCP CU8 source. No RF hardware output."""
import collections
import hmac
import json
import os
import queue
import signal
import socket
import socketserver
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import numpy as np
from modulator import Assembler,RATE,RATES,cu8,waveform,render,settings
from ais_suite import SCENARIOS
DATA=Path(os.environ.get('SDR_TX_DATA','/data'))
TOKEN=os.environ.get('SDR_TX_TOKEN','')
STATIC=Path(__file__).parent/'static'

class State:
    def __init__(self):
        DATA.mkdir(parents=True,exist_ok=True);path=DATA/'settings.json'
        self.config=settings(json.loads(path.read_text()) if path.exists() else {})
        self.lock=threading.RLock();self.client_lock=threading.Lock();self.queue=queue.Queue(256)
        self.enabled=False;self.client=None;self.epoch=0;self.rate=RATE
        self.counts=collections.Counter();self.error='';self.last_nmea=None
    def clear(self):
        while True:
            try:self.queue.get_nowait();self.counts['dropped']+=1
            except queue.Empty:break
    def stop(self):
        with self.lock:self.enabled=False;self.epoch+=1;self.clear()
    def ingest(self,raw,assembler):
        with self.lock:
            self.counts['sentences']+=1;self.last_nmea=time.time()
            try:packet=assembler.feed(raw)
            except (ValueError,UnicodeError) as exc:self.counts['invalid']+=1;self.error=str(exc);return
            if not packet:return
            self.counts['packets']+=1
            if not self.enabled or self.client is None:self.counts['dropped']+=1;return
            try:self.queue.put_nowait((time.monotonic(),packet))
            except queue.Full:self.counts['dropped']+=1
    def status(self):
        with self.lock:return dict(enabled=self.enabled,client=self.client,sample_rate=self.rate,queue=self.queue.qsize(),counts=dict(self.counts),last_error=self.error,last_nmea=self.last_nmea)
state=None

class TCPInput(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(60);assembler=Assembler()
        try:
            while True:
                line=self.rfile.readline(1026)
                if not line or len(line)>1024:break
                state.ingest(line,assembler)
        except OSError:pass

class UDPInput(socketserver.BaseRequestHandler):
    sources={}
    def handle(self):
        now=time.monotonic();cls=type(self)
        cls.sources={k:v for k,v in cls.sources.items() if now-v[0]<10}
        if self.client_address not in cls.sources:
            if len(cls.sources)>=64:cls.sources.pop(next(iter(cls.sources)))
            cls.sources[self.client_address]=(now,Assembler())
        assembler=cls.sources[self.client_address][1];cls.sources[self.client_address]=(now,assembler)
        for line in self.request[0].splitlines():state.ingest(line,assembler)

class IQOutput(socketserver.BaseRequestHandler):
    def handle(self):
        if not state.client_lock.acquire(blocking=False):return
        sock=self.request;sock.settimeout(2);closed=threading.Event();negotiated={'rate':RATE}
        rng=np.random.default_rng(42);reader=None
        try:
            with state.lock:state.clear();state.client=f'{self.client_address[0]}:{self.client_address[1]}';state.rate=RATE
            sock.sendall(struct.pack('>4sII',b'RTL0',0,0))
            def commands():
                pending=b''
                try:
                    while not closed.is_set():
                        try:data=sock.recv(1024)
                        except socket.timeout:continue
                        if not data:break
                        pending+=data
                        while len(pending)>=5:
                            cmd,value=struct.unpack('>BI',pending[:5]);pending=pending[5:]
                            if cmd==1 and value!=162000000:raise ValueError('Center must be 162000000 Hz')
                            if cmd==2:
                                if value not in RATES:raise ValueError('Unsupported sample rate')
                                negotiated['rate']=value
                                with state.lock:state.rate=value;state.epoch+=1
                            # Tuner gain/AGC commands have no hardware effect in this virtual source.
                except (OSError,ValueError) as exc:
                    with state.lock:state.error=str(exc)
                finally:closed.set()
            reader=threading.Thread(target=commands,daemon=True);reader.start()
            pending=np.zeros(0,dtype=complex);epoch=-1;deadline=time.monotonic()
            while not closed.is_set():
                with state.lock:config=dict(state.config);enabled=state.enabled;current=state.epoch
                rate=negotiated['rate'];size=rate//100
                if epoch!=current:pending=np.zeros(0,dtype=complex);epoch=current
                if not len(pending) and enabled:
                    try:
                        stamp,packet=state.queue.get_nowait()
                        if time.monotonic()-stamp>10:
                            with state.lock:state.counts['dropped']+=1
                        else:
                            pending=waveform(*packet,rate=rate,amplitude=config['amplitude'],offset=config['offset'],corrupt=config['corrupt'])
                            with state.lock:state.counts['modulated']+=1;state.counts['channel_'+packet[1]]+=1
                    except queue.Empty:pass
                block=np.zeros(size,dtype=complex);n=min(len(pending),size);block[:n]=pending[:n];pending=pending[n:]
                with state.lock:
                    if state.epoch!=epoch:block[:]=0
                sock.sendall(cu8(block,config['noise'],rng));deadline+=.01
                delay=deadline-time.monotonic()
                if delay<-.2:raise TimeoutError('Slow IQ client; reconnect required')
                if delay>0:closed.wait(delay)
        except OSError as exc:
            with state.lock:state.error=str(exc)
        finally:
            closed.set()
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            if reader:reader.join(3)
            with state.lock:state.client=None;state.clear();state.epoch+=1
            state.client_lock.release()

class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True
    def __init__(self,*args,**kwargs):self.slots=threading.BoundedSemaphore(32);super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

render_lock=threading.Lock()
class Web(BaseHTTPRequestHandler):
    def setup(self):super().setup();self.connection.settimeout(20)
    def log_message(self,*args):pass
    def reply(self,status,value,mime='application/json'):
        data=json.dumps(value,ensure_ascii=False).encode() if mime=='application/json' else value
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(data)
    def do_GET(self):self.route(False)
    def do_POST(self):self.route(True)
    def route(self,post):
        path=self.path.split('?')[0]
        if path=='/health' and not post:return self.reply(200,{'ok':True})
        assets={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
        if not post and path in assets:
            name,mime=assets[path];return self.reply(200,(STATIC/name).read_bytes(),mime)
        if not TOKEN or not hmac.compare_digest(self.headers.get('X-SDR-TX-Token',''),TOKEN):return self.reply(401,{'error':'管理トークンが一致しません'})
        try:
            data={}
            if post:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=131072:raise ValueError('Request size')
                data=json.loads(self.rfile.read(size))
            if path=='/api/status' and not post:return self.reply(200,state.status())
            if path=='/api/config':
                if post:
                    config=settings(data);state.stop()
                    with state.lock:
                        temp=DATA/'settings.tmp';temp.write_text(json.dumps(config));temp.replace(DATA/'settings.json');state.config=config
                return self.reply(200,state.config)
            if path=='/api/start' and post:
                with state.lock:state.clear();state.enabled=True;state.epoch+=1
                return self.reply(200,state.status())
            if path=='/api/stop' and post:state.stop();return self.reply(200,state.status())
            if path=='/api/scenarios' and not post:return self.reply(200,[s.public() for s in SCENARIOS])
            if path=='/api/enqueue' and post:
                if not isinstance(data['nmea'],str):raise ValueError('NMEA text required')
                assembler=Assembler()
                for line in data['nmea'].splitlines():
                    if line.strip():state.ingest(line,assembler)
                return self.reply(200,state.status())
            if path=='/api/render' and post:
                # Serialize generation to bound peak I/Q memory across simultaneous requests.
                with render_lock:
                    iq,count=render(data['nmea'],dict(state.config));temp=DATA/'test.tmp';temp.write_bytes(iq);temp.replace(DATA/'test.cu8')
                return self.reply(200,dict(packets=count,bytes=len(iq),sample_rate=RATE,center_frequency=162000000,format='CU8'))
            if path=='/api/iq' and not post:
                with render_lock:iq=(DATA/'test.cu8').read_bytes()
                return self.reply(200,iq,'application/octet-stream')
            return self.reply(404,{'error':'Not found'})
        except (ValueError,KeyError,TypeError,UnicodeError) as exc:self.reply(400,{'error':str(exc)})
        except FileNotFoundError:self.reply(404,{'error':'先にI/Qファイルを生成してください'})
        except OSError as exc:self.reply(503,{'error':str(exc)})

def main():
    global state
    if len(TOKEN)<16:raise SystemExit('Run sdr-tx/setup.py first')
    state=State();servers=[TCPServer(('0.0.0.0',10113),TCPInput),socketserver.UDPServer(('0.0.0.0',10113),UDPInput),TCPServer(('0.0.0.0',1235),IQOutput)]
    for server in servers:threading.Thread(target=server.serve_forever,daemon=True).start()
    web=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('SDR_TX_HTTP_PORT','80'))),Web)
    def stop(*_):threading.Thread(target=web.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:web.serve_forever()
    finally:
        state.stop();web.server_close()
        for server in servers:server.shutdown();server.server_close()
if __name__=='__main__':main()
