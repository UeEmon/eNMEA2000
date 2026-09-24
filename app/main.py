import asyncio
import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from uuid import uuid4
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .parser import Decoder, SENTENCE, utcnow
from .store import Store

log = logging.getLogger('nmea')
DATA = Path(os.getenv('DATA_DIR', './data'))
DATA.mkdir(parents=True, exist_ok=True)
TOKEN = os.getenv('APP_TOKEN', '')
SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
UDP_PORT = int(os.getenv('UDP_PORT', '10110'))
MAX_FILE = int(os.getenv('MAX_FILE_MB', '100')) * 1024 * 1024
ALLOW = [ipaddress.ip_network(v.strip()) for v in os.getenv('UDP_ALLOW_CIDRS', '').split(',') if v.strip()]

class Runtime:
    def __init__(self):
        self.decoder = Decoder()
        self.queue = asyncio.Queue(maxsize=int(os.getenv('QUEUE_SIZE','10000')))
        self.clients = set()
        self.jobs = {}
        self.tasks = set()
        self.metrics = {'datagrams':0, 'queue_dropped':0, 'rejected_sources':0,
                        'socket_errors':0, 'db_errors':0, 'ws_dropped':0, 'last_received':None}
        self.enabled = True
        self.transport = None
        self.failed = False

    def publish(self, rows):
        for q in list(self.clients):
            if q.full():
                q.get_nowait()
                self.metrics['ws_dropped'] += 1
                # Tell the browser to recover from the durable REST history.
                with contextlib.suppress(asyncio.QueueFull): q.put_nowait({'type':'gap'})
            else: q.put_nowait({'type':'events', 'rows':rows})

    async def consume(self):
        while True:
            item = await self.queue.get()
            batch = [item]
            while len(batch) < 200 and not self.queue.empty(): batch.append(self.queue.get_nowait())
            rows = [self.decoder.parse(raw, source, at) for raw, source, at in batch]
            try:
                saved = await asyncio.to_thread(self.store.add, rows)
                self.publish(saved)
            except Exception:
                self.metrics['db_errors'] += len(rows)
                log.exception('Database write failed; UDP rows lost')
            finally:
                for _ in batch: self.queue.task_done()

class UDP(asyncio.DatagramProtocol):
    def __init__(self, state): self.state = state
    def datagram_received(self, data, addr):
        s = self.state
        if not s.enabled: return
        if ALLOW and not any(ipaddress.ip_address(addr[0]) in net for net in ALLOW):
            s.metrics['rejected_sources'] += 1
            return
        s.metrics['datagrams'] += 1
        s.metrics['last_received'] = utcnow()
        source = f'udp:{addr[0]}:{addr[1]}'
        text = data.decode('ascii', errors='replace')
        # A datagram is an independent envelope. Never join arbitrary senders/fragments.
        lines = text.splitlines() or ['']
        for line in lines:
            sentences = SENTENCE.findall(line) or [line]
            for raw in sentences:
                try: s.queue.put_nowait((raw[:8192], source, s.metrics['last_received']))
                except asyncio.QueueFull: s.metrics['queue_dropped'] += 1
    def error_received(self, exc):
        self.state.metrics['socket_errors'] += 1
        log.error('UDP error: %s', exc)

state = Runtime()

@asynccontextmanager
async def lifespan(app):
    global state
    if len(TOKEN) < 24: raise RuntimeError('APP_TOKEN must contain at least 24 characters. Run scripts/setup.py.')
    state = Runtime()
    state.store = Store(os.getenv('DATABASE_URL', f'sqlite:///{DATA / "nmea.db"}'))
    for job in await asyncio.to_thread(state.store.load_jobs):
        if job['status'] in ('running','queued','uploading'):
            job.update(status='interrupted', error='サーバ再起動により中断。再アップロードしてください。')
            await asyncio.to_thread(state.store.save_job, job)
        state.jobs[job['id']] = job
    loop = asyncio.get_running_loop()
    state.transport, _ = await loop.create_datagram_endpoint(lambda: UDP(state), local_addr=('0.0.0.0', UDP_PORT))
    worker = asyncio.create_task(state.consume())
    try: yield
    finally:
        state.transport.close()
        for task in list(state.tasks): task.cancel()
        await asyncio.gather(*state.tasks, return_exceptions=True)
        with contextlib.suppress(asyncio.TimeoutError): await asyncio.wait_for(state.queue.join(), 10)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError): await worker
        state.store.engine.dispose()

app = FastAPI(title='NMEA Observatory', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

def signed_session():
    payload = str(int(time.time()) + 12*3600) + ':' + secrets.token_hex(12)
    return payload + ':' + hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()

def authorized(cookie):
    try:
        exp, nonce, signature = cookie.split(':')
        expected = hmac.new(TOKEN.encode(), f'{exp}:{nonce}'.encode(), hashlib.sha256).hexdigest()
        return int(exp) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError): return False

def origin_ok(headers):
    origin = headers.get('origin')
    if not origin: return True
    return urlparse(origin).netloc == headers.get('host')

@app.middleware('http')
async def access(request, call_next):
    if request.url.path.startswith('/api/') and request.url.path != '/api/login':
        if not authorized(request.cookies.get('session')): return JSONResponse({'detail':'ログインが必要です'}, 401)
    if request.method not in ('GET','HEAD','OPTIONS') and not origin_ok(request.headers):
        return JSONResponse({'detail':'Origin mismatch'},403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith('/api/'): response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/')
async def index(): return FileResponse(Path(__file__).parent/'static/index.html')

@app.get('/health')
async def health():
    return {'status':'ok', 'udp_port':UDP_PORT}

@app.get('/ready')
async def ready():
    try:
        await asyncio.to_thread(state.store.recent, 1)
        if state.transport.is_closing(): raise RuntimeError('UDP closed')
    except Exception: raise HTTPException(503,'not ready')
    return {'status':'ok'}

@app.post('/api/login')
async def login(request: Request):
    data = await request.json()
    if not hmac.compare_digest(str(data.get('token','')), TOKEN):
        await asyncio.sleep(0.3)
        raise HTTPException(401, 'トークンが違います')
    response = JSONResponse({'ok':True})
    response.set_cookie('session', signed_session(), httponly=True, secure=SECURE, samesite='strict', max_age=43200)
    return response

@app.post('/api/logout')
async def logout():
    response = JSONResponse({'ok':True}); response.delete_cookie('session'); return response

@app.get('/api/stats')
async def stats():
    state.decoder.expire()
    return {**await asyncio.to_thread(state.store.stats), 'runtime':dict(state.metrics),
            'queue_size':state.queue.qsize(), 'udp_enabled':state.enabled, 'udp_port':UDP_PORT,
            'ais_pending':len(state.decoder.groups), 'ais_expired':state.decoder.expired}

@app.post('/api/udp/{action}')
async def udp_control(action: str):
    if action not in ('start','stop'): raise HTTPException(400,'start / stop')
    state.enabled = action == 'start'
    if not state.enabled: state.decoder.groups.clear()
    return {'enabled':state.enabled}

@app.get('/api/events')
async def events(limit: int=Query(200,ge=1,le=2000), before:int|None=None, source:str|None=None,
                 kind:str|None=None, mmsi:str|None=None, after:int|None=None):
    return await asyncio.to_thread(state.store.recent, limit, before, source, kind, mmsi, after)

@app.get('/api/jobs')
async def jobs(): return sorted(state.jobs.values(), key=lambda j:j['created_at'], reverse=True)[:100]

@app.post('/api/jobs/{job_id}/cancel')
async def cancel_job(job_id: str):
    job = state.jobs.get(job_id)
    if not job: raise HTTPException(404,'Job not found')
    if job['status'] in ('queued','running'): job['cancel'] = True
    return job

async def import_file(job, path):
    decoder = Decoder(ttl=3600)
    batch = []
    job['status'] = 'running'
    try:
        with path.open('rb') as f:
            while True:
                if job.get('cancel'): break
                line = await asyncio.to_thread(f.readline, 8193)
                if not line: break
                job['bytes_read'] += len(line)
                job['lines'] += 1
                if len(line) > 8192:
                    # Reject an oversized record, consume its remainder with a bounded buffer.
                    while not line.endswith(b'\n'):
                        line = await asyncio.to_thread(f.readline, 8193)
                        job['bytes_read'] += len(line)
                        if not line: break
                    rows = [decoder.parse('行の長さが8192バイトを超えています', 'file:'+job['id'])]
                else:
                    text = line.decode('utf-8-sig',errors='replace').strip()
                    if not text: continue
                    rows = [decoder.parse(raw, 'file:'+job['id']) for raw in (SENTENCE.findall(text) or [text])]
                for row in rows:
                    row['filename'] = job['filename']
                    row['line_number'] = job['lines']
                    job[row['status']] = job.get(row['status'],0)+1
                    batch.append(row)
                if len(batch) >= 200:
                    state.publish(await asyncio.to_thread(state.store.add, batch)); batch=[]
                    await asyncio.to_thread(state.store.save_job, dict(job))
                    await asyncio.sleep(0)
            if batch: state.publish(await asyncio.to_thread(state.store.add,batch))
        job['status'] = 'cancelled' if job.get('cancel') else 'completed'
        job['incomplete_ais_groups'] = len(decoder.groups) + decoder.expired
    except asyncio.CancelledError:
        job.update(status='interrupted',error='サーバ停止により中断')
        raise
    except Exception as exc:
        log.exception('Import failed'); job.update(status='failed',error=str(exc)[:240])
    finally:
        await asyncio.to_thread(state.store.save_job, dict(job))

@app.post('/api/files')
async def upload(request: Request, filename: str=Query('input.log',max_length=200)):
    if int(request.headers.get('content-length','0')) > MAX_FILE: raise HTTPException(413,'ファイル上限超過')
    if sum(j['status'] in ('running','queued','uploading') for j in state.jobs.values()) >= 2:
        raise HTTPException(429,'同時インポートは2件までです')
    job_id = uuid4().hex
    job = dict(id=job_id,filename=Path(filename.replace('\\','/')).name,created_at=utcnow(),
               status='uploading',size=0,bytes_read=0,lines=0,ok=0,error=0,pending=0,unsupported=0)
    state.jobs[job_id] = job
    path = DATA / (job_id+'.log')
    try:
        with path.open('wb') as f:
            async for chunk in request.stream():
                job['size'] += len(chunk)
                if job['size'] > MAX_FILE: raise HTTPException(413,'ファイル上限超過')
                await asyncio.to_thread(f.write,chunk)
    except BaseException:
        path.unlink(missing_ok=True); state.jobs.pop(job_id,None); raise
    def digest():
        with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
    job['sha256'] = await asyncio.to_thread(digest)
    job['status'] = 'queued'
    await asyncio.to_thread(state.store.save_job, dict(job))
    task = asyncio.create_task(import_file(job,path)); state.tasks.add(task); task.add_done_callback(state.tasks.discard)
    return JSONResponse(job,status_code=202)

@app.get('/api/export/{fmt}')
async def export(fmt:str, source:str|None=None, mmsi:str|None=None):
    if fmt not in ('jsonl','geojson'): raise HTTPException(400,'jsonl / geojson')
    # Freeze an ID upper boundary so export terminates during continuous ingest.
    latest = await asyncio.to_thread(state.store.recent,1)
    upper = latest[0]['id'] if latest else 0
    async def stream():
        after=0; first=True
        if fmt == 'geojson': yield '{"type":"FeatureCollection","features":['
        while after < upper:
            rows = await asyncio.to_thread(state.store.recent,1000,None,source,None,mmsi,after)
            if not rows: break
            for row in rows:
                after=row['id']
                if after > upper: break
                if fmt == 'jsonl': yield json.dumps(row,ensure_ascii=False)+'\n'
                elif row['latitude'] is not None and row['longitude'] is not None:
                    obj={'type':'Feature','geometry':{'type':'Point','coordinates':[row['longitude'],row['latitude']]},
                         'properties':{k:v for k,v in row.items() if k not in ('latitude','longitude')}}
                    yield ('' if first else ',')+json.dumps(obj,ensure_ascii=False); first=False
            await asyncio.sleep(0)
        if fmt == 'geojson': yield ']}'
    return StreamingResponse(stream(), media_type='application/x-ndjson' if fmt=='jsonl' else 'application/geo+json',
        headers={'Content-Disposition':f'attachment; filename="nmea-export.{fmt}"'})

@app.websocket('/ws')
async def ws(socket: WebSocket):
    if not authorized(socket.cookies.get('session')) or not origin_ok(socket.headers):
        await socket.close(code=1008); return
    await socket.accept()
    q=asyncio.Queue(maxsize=32); state.clients.add(q)
    try:
        await socket.send_json({'type':'hello'})
        while authorized(socket.cookies.get('session')):
            try: msg=await asyncio.wait_for(q.get(),15)
            except asyncio.TimeoutError: msg={'type':'heartbeat'}
            await asyncio.wait_for(socket.send_json(msg),10)
    except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError): pass
    finally:
        state.clients.discard(q)
        with contextlib.suppress(Exception): await socket.close()

app.mount('/static', StaticFiles(directory=Path(__file__).parent/'static'), name='static')
