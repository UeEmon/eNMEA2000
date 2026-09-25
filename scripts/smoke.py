"""Run INSIDE the app container; checks HTTP, UDP ingest, file import, exports."""
import json
import os
import socket
import time
import urllib.request
import http.cookiejar
from pathlib import Path
base='http://127.0.0.1:80'
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def req(path, data=None, content='application/json'):
    r=urllib.request.Request(base+path,data=data,headers={'Content-Type':content})
    with opener.open(r,timeout=15) as response: return json.load(response)
req('/api/login', json.dumps({'token':os.environ['APP_TOKEN']}).encode())
before=req('/api/stats')['total']
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
    s.sendto(b'$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n',('127.0.0.1',10110))
for _ in range(100):
    if req('/api/stats')['total']>before: break
    time.sleep(.1)
else: raise AssertionError('UDP ingest failed')
job=req('/api/files?filename=smoke.log',Path('samples/demo.log').read_bytes(),'application/octet-stream')
for _ in range(100):
    found=next(j for j in req('/api/jobs') if j['id']==job['id'])
    if found['status']=='completed': break
    if found['status']=='failed': raise AssertionError(found)
    time.sleep(.1)
else: raise AssertionError('File import timed out')
assert found['ok']>0
assert req('/api/export/geojson')['type']=='FeatureCollection'
with opener.open(base+'/static/cesium/Cesium.js',timeout=15) as response:
    assert response.status == 200 and response.read(50)
with opener.open(base+'/static/cesium/Assets/Textures/NaturalEarthII/tilemapresource.xml',timeout=15) as response:
    assert response.status == 200
print('PASS: login, UDP, file import, database read, GeoJSON, Cesium assets')
