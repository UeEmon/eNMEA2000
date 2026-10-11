"""Dedicated CI only: SDR router -> host TCP/UDP -> main parser -> PostgreSQL -> REST."""
import http.cookiejar
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from smoke import api, wait, ROOT
sys.path.insert(0,str(ROOT/'tests'))
from fixtures import radio_frames

jar=http.cookiejar.CookieJar()
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def main_api(path,data=None):
    req=urllib.request.Request('http://127.0.0.1:18081/api/'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with client.open(req,timeout=10) as r:return json.load(r)

def main():
    token=next(l.split('=',1)[1] for l in (ROOT.parent/'.env').read_text().splitlines() if l.startswith('APP_TOKEN='))
    main_api('login',{'token':token})
    enabled=main_api('stats')['udp_enabled'];original=api('config')
    try:
        main_api('udp/start',{})
        for protocol,port in [('tcp',10111),('udp',10110)]:
            config=json.loads(json.dumps(original));config['destinations']=[{'enabled':True,'protocol':protocol,'host':'host.docker.internal','port':port}]
            api('config',config);wait(lambda:api('status')['destinations'][0]['connected'])
            before=max([e['id'] for e in main_api('events?limit=100')],default=0)
            code='import socket,sys;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(sys.stdin.buffer.read(),("nmea-router",10112))'
            subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'exec','-T','ais-receiver','python','-c',code],input=b'\r\n'.join(radio_frames())+b'\r\n',check=True)
            def complete():
                events=main_api(f'events?limit=200&after={before}')
                types={e.get('ais_type') for e in events if e['source'].startswith(protocol+':')}
                return set(range(29))<=types
            wait(complete)
            print(f'PASS: SDR {protocol.upper()} -> main -> PostgreSQL -> REST, all AIS type IDs 0..28')
    finally:
        api('config',original);main_api('udp/'+('start' if enabled else 'stop'),{})

if __name__=='__main__':main()
