"""Stand-alone simulator: configuration from localhost UI; TCP/UDP destination configurable from the Web UI."""
import asyncio
import contextlib
from datetime import datetime, timezone
import math
import os
import json
import socket
import ipaddress
import re
from typing import Literal
import time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from pyais.encode import encode_dict
from ais_suite import SCENARIOS, BY_ID, with_mmsi

HOST=os.getenv('NMEA_TARGET_HOST','host.docker.internal')
PORT=int(os.getenv('NMEA_TARGET_PORT','10111'))

class OutputConfig(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    protocol: Literal['tcp', 'udp'] = 'tcp'

    @model_validator(mode='after')
    def valid_host(self):
        self.host = self.host.strip()
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            labels = self.host.rstrip('.').split('.')
            if not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in labels):
                raise ValueError('IPアドレスまたはホスト名を入力してください（URLは不可）')
        return self

OUTPUT_FILE = Path(os.getenv('NMEA_OUTPUT_FILE', '/data/output.json'))
output_override = None
if OUTPUT_FILE.exists():
    output_override = OutputConfig.model_validate_json(OUTPUT_FILE.read_text())

def output_config():
    return output_override or OutputConfig(host=HOST, port=PORT, protocol=os.getenv('NMEA_TARGET_PROTOCOL', 'tcp'))

def output_target():
    cfg = output_config()
    host = f'[{cfg.host}]' if ':' in cfg.host else cfg.host
    return f'{cfg.protocol.upper()} {host}:{cfg.port}'

class DatagramWriter:
    """StreamWriter-compatible adapter: each CRLF sentence becomes one datagram."""
    def __init__(self, sock):
        self.sock = sock
        self.pending = b''

    def write(self, data):
        self.pending += data

    async def drain(self):
        data, self.pending = self.pending, b''
        for line in data.split(b'\r\n'):
            if line:
                await asyncio.get_running_loop().sock_sendall(self.sock, line + b'\r\n')

    def close(self):
        self.sock.close()

    async def wait_closed(self):
        pass

async def open_output():
    cfg = output_config()
    if cfg.protocol == 'tcp':
        return await asyncio.open_connection(cfg.host, cfg.port)
    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(cfg.host, cfg.port, type=socket.SOCK_DGRAM)
    last_error = None
    for family, kind, proto, _, address in addresses:
        sock = socket.socket(family, kind, proto)
        sock.setblocking(False)
        try:
            await loop.sock_connect(sock, address)
            return None, DatagramWriter(sock)
        except OSError as exc:
            sock.close()
            last_error = exc
    raise last_error or OSError('送信先を解決できません')

class Waypoint(BaseModel):
    lat: float = Field(ge=-89, le=89)
    lon: float = Field(ge=-180, le=180)

class Route(BaseModel):
    waypoints: list[Waypoint] = Field(default_factory=list, max_length=30)
    loop: bool = False

class AisType5(BaseModel):
    repeat: int = Field(0, ge=0, le=3)
    ais_version: int = Field(0, ge=0, le=3)
    imo: int = Field(0, ge=0, le=999999980)
    callsign: str = Field('TEST', max_length=7, pattern=r'^[A-Z0-9 ]*$')
    shipname: str = Field('TEST VESSEL', max_length=17, pattern=r'^[A-Z0-9 ]*$')
    ship_type: int = Field(70, ge=0, le=99)
    to_bow: int = Field(20, ge=0, le=511)
    to_stern: int = Field(10, ge=0, le=511)
    to_port: int = Field(5, ge=0, le=63)
    to_starboard: int = Field(5, ge=0, le=63)
    epfd: int = Field(1, ge=0, le=15)
    month: int = Field(0, ge=0, le=12)
    day: int = Field(0, ge=0, le=31)
    hour: int = Field(24, ge=0, le=24)
    minute: int = Field(60, ge=0, le=60)
    draught: float = Field(0, ge=0, le=25.5)
    destination: str = Field('TOKYO', max_length=20, pattern=r'^[A-Z0-9 ]*$')
    dte: bool = False

    @model_validator(mode='after')
    def valid_draught(self):
        if round(self.draught * 10, 6) % 1:
            raise ValueError('draught must be in 0.1 m increments')
        return self

class Config(BaseModel):
    latitude: float = Field(35.65,ge=-89,le=89)
    longitude: float = Field(139.75,ge=-180,le=180)
    course: float = Field(90,ge=0,lt=360)
    speed: float = Field(12,ge=0,le=60)
    interval: float = Field(1,ge=.2,le=60)
    vessel_count: int = Field(2,ge=1,le=20)
    mmsi_start: int = Field(431234567, ge=100000000, le=999999980)
    ais: bool = True
    gps: bool = True
    rmc: bool = True
    gga: bool = True
    ais_type1: bool = True
    ais_type5: bool = True
    ais5: AisType5 = Field(default_factory=AisType5)
    route: Route = Field(default_factory=Route)

EARTH_NM = 3440.065

def navigation(lat, lon, target: Waypoint):
    a, b = math.radians(lat), math.radians(target.lat)
    delta_lon = math.radians(target.lon - lon)
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(delta_lon/2)**2
    distance = 2 * EARTH_NM * math.asin(min(1,math.sqrt(h)))
    bearing = math.degrees(math.atan2(math.sin(delta_lon)*math.cos(b),
        math.cos(a)*math.sin(b)-math.sin(a)*math.cos(b)*math.cos(delta_lon))) % 360
    return distance, bearing

def destination(lat,lon,bearing,step_nm):
    a,o,t,d=math.radians(lat),math.radians(lon),math.radians(bearing),step_nm/EARTH_NM
    b=math.asin(max(-1,min(1,math.sin(a)*math.cos(d)+math.cos(a)*math.sin(d)*math.cos(t))))
    l=o+math.atan2(math.sin(t)*math.sin(d)*math.cos(a),math.cos(d)-math.sin(a)*math.sin(b))
    return math.degrees(b),((math.degrees(l)+180)%360)-180

class Simulator:
    def __init__(self):
        self.config=Config();self.active=False;self.connected=False;self.lines=0;self.error='';self.preview=[]
        self.latitude=self.config.latitude;self.longitude=self.config.longitude
        self.writer=None;self.task=None;self.tick=0
        self.route_index=0;self.route_done=False;self.current_speed=0

    def status(self):
        vessels=[{'mmsi':self.config.mmsi_start+i,'lat':min(89.9,self.latitude+i*.006),
                  'lon':((self.longitude+i*.008+180)%360)-180}
                 for i in range(self.config.vessel_count)] if self.config.ais and self.config.ais_type1 else []
        return dict(config=self.config.model_dump(),active=self.active,connected=self.connected,
                    lines=self.lines,error=self.error,preview=self.preview[-12:],target=output_target(),output=output_config().model_dump(),
                    position={'lat':self.latitude,'lon':self.longitude},course=self.config.course,
                    current_speed=self.current_speed,route_index=self.route_index,route_done=self.route_done,
                    vessels=vessels)

    def advance(self):
        cfg=self.config
        step_nm=cfg.speed*cfg.interval/3600
        route=cfg.route.waypoints
        if route and not self.route_done:
            # Skip coincident waypoints while preserving the order chosen on the map.
            for _ in range(len(route)+1):
                target=route[self.route_index]
                distance,bearing=navigation(self.latitude,self.longitude,target)
                if distance > 1e-6: break
                if self.route_index+1<len(route): self.route_index+=1
                elif cfg.route.loop: self.route_index=0
                else: self.route_done=True;break
            if self.route_done:
                self.current_speed=0
                return
            if distance <= 1e-6:
                self.current_speed=0
                return
            cfg.course=bearing
            if distance<=step_nm:
                self.latitude,self.longitude=target.lat,target.lon
                self.current_speed=cfg.speed
                if self.route_index+1<len(route): self.route_index+=1
                elif cfg.route.loop:self.route_index=0
                else:self.route_done=True
            else:
                self.latitude,self.longitude=destination(self.latitude,self.longitude,bearing,step_nm)
                self.current_speed=cfg.speed
        elif route:
            self.current_speed=0
        else:
            self.latitude,self.longitude=destination(self.latitude,self.longitude,cfg.course,step_nm)
            self.current_speed=cfg.speed

    async def stop(self):
        self.active=False
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await self.task
            self.task=None
        await self.disconnect()

    async def disconnect(self):
        self.connected=False
        if self.writer:
            self.writer.close()
            with contextlib.suppress(Exception): await self.writer.wait_closed()
            self.writer=None

    async def run(self):
        self.active=True
        while self.active:
            try:
                _,self.writer=await asyncio.wait_for(open_output(),5)
                self.connected=True;self.error=''
                while self.active:
                    frames=self.generate()
                    if frames:
                        self.writer.write(('\r\n'.join(frames)+'\r\n').encode('ascii'))
                        await asyncio.wait_for(self.writer.drain(),5)
                        self.lines+=len(frames)
                        self.preview=(self.preview+frames)[-12:]
                    await asyncio.sleep(self.config.interval)
            except asyncio.CancelledError: raise
            except (OSError,asyncio.TimeoutError) as exc:
                self.error=str(exc)[:180]
                await asyncio.sleep(2)
            finally: await self.disconnect()

    def generate(self):
        cfg=self.config
        utc=datetime.now(timezone.utc)
        self.tick+=1
        self.advance()
        out=[]
        if cfg.gps and (cfg.rmc or cfg.gga):
            lat,ns=coord(self.latitude,2);lon,ew=coord(self.longitude,3)
            if cfg.rmc:
                out.append(nmea(f'GNRMC,{utc:%H%M%S}.00,A,{lat},{ns},{lon},{ew},{self.current_speed:.1f},{cfg.course:.1f},{utc:%d%m%y},,,A'))
            if cfg.gga:
                out.append(nmea(f'GNGGA,{utc:%H%M%S}.00,{lat},{ns},{lon},{ew},1,08,0.9,1.2,M,0.0,M,,') )
        if cfg.ais:
            for i in range(cfg.vessel_count):
                mmsi=cfg.mmsi_start+i
                alon=((self.longitude+i*.008+180)%360)-180;alat=min(89.9,self.latitude+i*.006)
                if cfg.ais_type1:
                    out+=encode_dict({'msg_type':1,'mmsi':mmsi,'lat':alat,'lon':alon,'speed':self.current_speed,'course':cfg.course,'heading':int(cfg.course)},talker_id='AI',sentence_type='VDM')
                if cfg.ais_type5 and (self.tick==1 or self.tick%60==0):
                    fields=cfg.ais5.model_dump()
                    fields.update(msg_type=5,mmsi=mmsi,shipname=f'{cfg.ais5.shipname} {i+1}',
                                  imo=cfg.ais5.imo+i if cfg.ais5.imo else 0)
                    out+=encode_dict(fields,talker_id='AI',sentence_type='VDM')
        return out

def coord(value,deg_width):
    deg=int(abs(value));minute=(abs(value)-deg)*60
    return f'{deg:0{deg_width}d}{minute:07.4f}', ('N' if value>=0 else 'S') if deg_width==2 else ('E' if value>=0 else 'W')

def nmea(body):
    code=0
    for char in body: code^=ord(char)
    return f'${body}*{code:02X}'

sim=Simulator()
@asynccontextmanager
async def lifespan(app):
    try:yield
    finally:
        await sim.stop()
        await ring_motion.stop()
app=FastAPI(title='NMEA TCP/UDP Emulator',lifespan=lifespan,openapi_url=None,docs_url=None,redoc_url=None)

@app.middleware('http')
async def same_origin(request:Request,next_call):
    if request.method=='POST':
        origin=request.headers.get('origin')
        if origin and origin.split('://',1)[-1]!=request.headers.get('host'):raise HTTPException(403,'Origin mismatch')
    return await next_call(request)

@app.get('/')
def index():return FileResponse(Path(__file__).parent/'static/index.html')
@app.get('/health')
def health():return {'ok':True}
@app.get('/api/status')
def status():return sim.status()
@app.post('/api/start')
async def start(config:Config):
    async with ring_motion.lock:
        await sim.stop()
        sim.config=config;sim.latitude=config.latitude;sim.longitude=config.longitude;sim.tick=0
        sim.route_index=0;sim.route_done=False;sim.current_speed=0
        sim.task=asyncio.create_task(sim.run())
        return sim.status()

@app.post('/api/position')
async def set_position(position:Waypoint):
    sim.latitude=sim.config.latitude=position.lat
    sim.longitude=sim.config.longitude=position.lon
    sim.route_index=0;sim.route_done=False
    return sim.status()

@app.post('/api/route')
async def set_route(route:Route):
    sim.config.route=route
    sim.route_index=0;sim.route_done=False
    return sim.status()

class Course(BaseModel):
    course:float=Field(ge=0,lt=360)

@app.post('/api/course')
async def set_course(course:Course):
    sim.config.course=course.course
    return sim.status()
@app.post('/api/stop')
async def stop():
    async with ring_motion.lock:
        await ring_motion.stop()
        await sim.stop()
        return {**sim.status(), 'motion': ring_motion.status()}

class AisSuiteRequest(BaseModel):
    scenario_ids: list[str] = Field(min_length=1, max_length=50)
    center: Waypoint | None = None
    spacing_nm: float = Field(2, ge=0.2, le=20)

    @model_validator(mode='after')
    def valid_scenarios(self):
        if len(set(self.scenario_ids)) != len(self.scenario_ids) or any(id not in BY_ID for id in self.scenario_ids):
            raise ValueError('Unknown or duplicate scenario id')
        return self


def ais_ring_layout(center: Waypoint, spacing_nm: float, selected, phase=0):
    """One marker per scenario; rings have approximately equal chord spacing."""
    phase %= 360
    markers = []
    offset = 0
    ring = 1
    while offset < len(selected):
        count = min(7 * ring, len(selected) - offset)
        for slot in range(count):
            scenario = selected[offset + slot]
            angle = (slot * 360 / count + phase) % 360
            lat, lon = destination(center.lat, center.lon, angle,
                                   ring * spacing_nm)
            index = SCENARIOS.index(scenario)
            mmsi = (980000000 if scenario.id == 'type-24-aux' else 431800000) + index
            markers.append(dict(id=scenario.id, label=scenario.label,
                                message_type=scenario.message_type, mmsi=mmsi,
                                lat=round(lat, 6), lon=round(lon, 6), ring=ring, angle=angle))
        offset += count
        ring += 1
    return markers

@app.get('/api/ais/scenarios')
def ais_scenarios():
    return {'scenarios': [scenario.public() for scenario in SCENARIOS],
            'types': sorted({scenario.message_type for scenario in SCENARIOS})}

@app.post('/api/ais/send')
async def send_ais_scenarios(request: AisSuiteRequest):
    async with ring_motion.lock:
        return await _send_ais_scenarios(request)

async def _send_ais_scenarios(request: AisSuiteRequest):
    if len(set(request.scenario_ids)) != len(request.scenario_ids):
        raise HTTPException(422, 'Duplicate scenario id')
    unknown = [id for id in request.scenario_ids if id not in BY_ID]
    if unknown:
        raise HTTPException(422, 'Unknown scenario id')
    selected = [BY_ID[id] for id in request.scenario_ids]
    markers = ais_ring_layout(request.center, request.spacing_nm, selected) if request.center else []
    if markers:
        frames = []
        for scenario, marker in zip(selected, markers):
            frames.extend(with_mmsi(scenario.frames, marker['mmsi']))
            frames.extend(encode_dict({'msg_type': 1, 'mmsi': marker['mmsi'],
                                       'lat': marker['lat'], 'lon': marker['lon'],
                                       'speed': 0, 'course': 0, 'heading': 0},
                                      talker_id='AI', sentence_type='VDM'))
    else:
        frames = [frame for scenario in selected for frame in scenario.frames]
    writer = None
    try:
        _, writer = await asyncio.wait_for(open_output(), 5)
        writer.write(('\r\n'.join(frames) + '\r\n').encode('ascii'))
        await asyncio.wait_for(writer.drain(), 5)
    except (OSError, asyncio.TimeoutError) as exc:
        raise HTTPException(503, f'送信に失敗しました: {str(exc)[:160]}') from exc
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
    sim.lines += len(frames)
    sim.preview = (sim.preview + frames)[-12:]
    return {'sent': len(selected), 'sentences': len(frames),
            'scenarios': [scenario.id for scenario in selected], 'target': output_target(),
            'markers': markers}

app.mount('/static', StaticFiles(directory=Path(__file__).parent/'static'),name='static')


class RingMotion:
    def __init__(self):
        self.task = None
        self.active = False
        self.connected = False
        self.error = ''
        self.markers = []
        self.phase = 0
        self.cycles = 0
        self.interval = 1
        self.rate = 0
        self.request = None
        self.lock = asyncio.Lock()

    def configure(self, request):
        self.request = request
        self.selected = [BY_ID[id] for id in request.scenario_ids]
        self.markers = ais_ring_layout(request.center, request.spacing_nm, self.selected)
        counts = [sum(m['ring'] == ring for m in self.markers)
                  for ring in {m['ring'] for m in self.markers}]
        outer_radius = max(m['ring'] for m in self.markers) * request.spacing_nm
        # Cross one symbol gap in two minutes, capped at 80 kt on the outer ring.
        self.rate = min(360 / max(counts) / 120,
                        math.degrees(80 / outer_radius / 3600))
        # Limit baseline load to 60 position sentences/s; reserve 75% processing time.
        self.interval = max(1, len(self.markers) / 60)
        self.phase = 0
        self.cycles = 0
        self.error = ''

    def status(self):
        return dict(active=self.active, connected=self.connected, error=self.error,
                    interval=self.interval, angular_step_deg=self.rate * self.interval,
                    angular_rate_deg_s=self.rate, cycles=self.cycles, markers=self.markers,
                    center=self.request.center.model_dump() if self.request else None,
                    spacing_nm=self.request.spacing_nm if self.request else None,
                    movement_nm=[dict(ring=ring, distance=math.radians(self.rate * self.interval)
                                     * ring * self.request.spacing_nm)
                                 for ring in sorted({m['ring'] for m in self.markers})]
                    if self.request else [])

    async def stop(self):
        self.active = False
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        self.connected = False

    def frames_at(self, phase):
        markers = ais_ring_layout(self.request.center, self.request.spacing_nm, self.selected, phase)
        frames = []
        for marker in markers:
            radius = marker['ring'] * self.request.spacing_nm
            next_lat, next_lon = destination(self.request.center.lat, self.request.center.lon,
                                            marker['angle'] + .01, radius)
            _, course = navigation(marker['lat'], marker['lon'], Waypoint.model_construct(lat=next_lat, lon=next_lon))
            speed = math.radians(self.rate) * radius * 3600
            frames.extend(encode_dict({'msg_type': 1, 'mmsi': marker['mmsi'],
                                       'lat': marker['lat'], 'lon': marker['lon'],
                                       'speed': round(speed, 1), 'course': round(course, 1) % 360,
                                       'heading': int(course)}, talker_id='AI', sentence_type='VDM'))
        return markers, frames

    async def run(self):
        while self.active:
            writer = None
            try:
                _, writer = await asyncio.wait_for(open_output(), 5)
                self.connected = True
                self.error = ''
                previous = time.monotonic()
                while self.active:
                    await asyncio.sleep(max(0, previous + self.interval - time.monotonic()))
                    started = time.monotonic()
                    phase = (self.phase + self.rate * (started - previous)) % 360
                    markers, frames = self.frames_at(phase)
                    writer.write(('\r\n'.join(frames) + '\r\n').encode('ascii'))
                    await asyncio.wait_for(writer.drain(), 5)
                    self.phase = phase
                    self.markers = markers
                    previous = started
                    self.cycles += 1
                    sim.lines += len(frames)
                    sim.preview = (sim.preview + frames)[-12:]
                    cost = time.monotonic() - started
                    target = max(1, len(markers) / 60, cost * 4)
                    self.interval = min(10, max(target, self.interval * .8))
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.TimeoutError) as exc:
                self.error = str(exc)[:180]
                self.connected = False
                await asyncio.sleep(2)
            finally:
                self.connected = False
                if writer:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()


ring_motion = RingMotion()

@app.get('/api/ais/motion')
def motion_status():
    return ring_motion.status()

@app.post('/api/ais/motion/start')
async def motion_start(request: AisSuiteRequest):
    if request.center is None:
        raise HTTPException(422, '中心位置を指定してください')
    async with ring_motion.lock:
        await ring_motion.stop()
        initial = await _send_ais_scenarios(request)
        ring_motion.configure(request)
        ring_motion.active = True
        ring_motion.task = asyncio.create_task(ring_motion.run())
        return {**ring_motion.status(), 'sent': initial['sent'],
                'sentences': initial['sentences'], 'target': initial['target']}

@app.post('/api/ais/motion/stop')
async def motion_stop():
    async with ring_motion.lock:
        await ring_motion.stop()
        return ring_motion.status()


@app.get('/api/output')
def get_output():
    return output_config().model_dump()

@app.post('/api/output')
async def set_output(config: OutputConfig):
    global output_override
    async with ring_motion.lock:
        # Persist atomically before changing the running destination.
        try:
            OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = OUTPUT_FILE.with_suffix('.tmp')
            temporary.write_text(config.model_dump_json())
            temporary.replace(OUTPUT_FILE)
        except OSError as exc:
            raise HTTPException(503, '送信先設定を保存できません') from exc
        await ring_motion.stop()
        await sim.stop()
        output_override = config
        return {**sim.status(), 'motion': ring_motion.status()}
