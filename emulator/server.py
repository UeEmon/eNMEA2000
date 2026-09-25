"""Stand-alone simulator: configuration from localhost UI; TCP destination fixed in env."""
import asyncio
import contextlib
from datetime import datetime, timezone
import math
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pyais.encode import encode_dict

HOST=os.getenv('NMEA_TARGET_HOST','host.docker.internal')
PORT=int(os.getenv('NMEA_TARGET_PORT','10111'))

class Waypoint(BaseModel):
    lat: float = Field(ge=-89, le=89)
    lon: float = Field(ge=-180, le=180)

class Route(BaseModel):
    waypoints: list[Waypoint] = Field(default_factory=list, max_length=30)
    loop: bool = False

class Config(BaseModel):
    latitude: float = Field(35.65,ge=-89,le=89)
    longitude: float = Field(139.75,ge=-180,le=180)
    course: float = Field(90,ge=0,lt=360)
    speed: float = Field(12,ge=0,le=60)
    interval: float = Field(1,ge=.2,le=60)
    vessel_count: int = Field(2,ge=1,le=20)
    ais: bool = True
    gps: bool = True
    rmc: bool = True
    gga: bool = True
    ais_type1: bool = True
    ais_type5: bool = True
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
        vessels=[{'mmsi':431234567+i,'lat':min(89.9,self.latitude+i*.006),
                  'lon':((self.longitude+i*.008+180)%360)-180}
                 for i in range(self.config.vessel_count)] if self.config.ais and self.config.ais_type1 else []
        return dict(config=self.config.model_dump(),active=self.active,connected=self.connected,
                    lines=self.lines,error=self.error,preview=self.preview[-12:],target=f'{HOST}:{PORT}',
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
                _,self.writer=await asyncio.wait_for(asyncio.open_connection(HOST,PORT),5)
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
                mmsi=431234567+i
                alon=((self.longitude+i*.008+180)%360)-180;alat=min(89.9,self.latitude+i*.006)
                if cfg.ais_type1:
                    out+=encode_dict({'msg_type':1,'mmsi':mmsi,'lat':alat,'lon':alon,'speed':self.current_speed,'course':cfg.course,'heading':int(cfg.course)},talker_id='AI',sentence_type='VDM')
                if cfg.ais_type5 and (self.tick==1 or self.tick%60==0):
                    out+=encode_dict({'msg_type':5,'mmsi':mmsi,'shipname':f'TEST VESSEL {i+1}','callsign':'TEST',
                                      'ship_type':70,'to_bow':20,'to_stern':10,'to_port':5,'to_starboard':5,'destination':'TOKYO'},talker_id='AI',sentence_type='VDM')
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
    finally:await sim.stop()
app=FastAPI(title='NMEA TCP Emulator',lifespan=lifespan,openapi_url=None,docs_url=None,redoc_url=None)

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
    await sim.stop();return sim.status()

app.mount('/static', StaticFiles(directory=Path(__file__).parent/'static'),name='static')
