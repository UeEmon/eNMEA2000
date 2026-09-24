"""End-to-end check across two independent Compose projects on the same host."""
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.request

app='http://127.0.0.1:8080'
emulator='http://127.0.0.1:8090'
token=next(line.split('=',1)[1].strip() for line in Path('.env').read_text().splitlines() if line.startswith('APP_TOKEN='))
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(url, body=None):
    r=urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                             headers={'Content-Type':'application/json'})
    with client.open(r,timeout=10) as response:return json.load(response)
request(app+'/api/login',{'token':token})
before=request(app+'/api/stats')['runtime']['tcp_sentences']
for asset in ('/static/cesium/Cesium.js','/static/cesium/Assets/Textures/NaturalEarthII/tilemapresource.xml','/static/app.js'):
    with client.open(emulator+asset,timeout=15) as response: assert response.status==200 and response.read(48)
try:
    cfg=dict(latitude=35.65,longitude=139.75,course=90,speed=12,interval=.2,vessel_count=2,gps=True,ais=True,route={'waypoints':[{'lat':35.66,'lon':139.76}],'loop':False})
    request(emulator+'/api/start',cfg)
    for _ in range(120):
        emulator_status=request(emulator+'/api/status')
        status=request(app+'/api/stats')
        events=request(app+'/api/events?limit=100')
        if emulator_status['config']['route']['waypoints'] and abs(emulator_status['course']-90)>1 and status['runtime']['tcp_sentences']>before+4 and any(r['source'].startswith('tcp:') and r['mmsi']=='431234567' for r in events):
            assert any(r['source'].startswith('tcp:') and r['sentence_type']=='RMC' and r['latitude'] is not None for r in events)
            print('PASS: Cesium assets + waypoint navigation + independent Docker emulator -> host TCP:10111 -> app -> PostgreSQL -> REST')
            break
        time.sleep(.25)
    else:raise AssertionError(f'TCP/AIS not observed: {status}, {request(emulator+"/api/status")}')
finally:request(emulator+'/api/stop',{})
