"""Existing emulator -> modulator -> RTL-TCP -> receiver -> main DB/REST."""
import http.cookiejar
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def secret(path,key):return next(l.split('=',1)[1] for l in path.read_text().splitlines() if l.startswith(key+'='))
TX=secret(ROOT/'sdr-tx/.env','SDR_TX_TOKEN');RX=secret(ROOT/'sdr/.env','SDR_TOKEN')
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(port,path,data=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['X-SDR-TX-Token' if port==18083 else 'X-SDR-Token']=token
    req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
    with client.open(req,timeout=20) as r:return json.load(r)
def tx(path,data=None):return request(18083,'/api/'+path,data,TX)
def rx(path,data=None):return request(18082,'/api/'+path,data,RX)
def app(path,data=None):return request(18081,'/api/'+path,data)
def emu(path,data=None):return request(8090,'/api/'+path,data)
def wait(fn):
    until=time.monotonic()+30
    while not fn():
        if time.monotonic()>until:raise AssertionError('Timed out: '+json.dumps(tx('status')))
        time.sleep(.15)

def main():
    try:request(18083,'/api/config');raise AssertionError('Anonymous management allowed')
    except urllib.error.HTTPError as e:assert e.code==401
    app('login',{'token':secret(ROOT/'.env','APP_TOKEN')})
    enabled=app('stats')['udp_enabled'];old_rx=rx('config');old_tx=tx('config');old_output=emu('output')
    # /api/output GET returns the saved configuration under output in current emulator.
    if 'output' in old_output:old_output=old_output['output']
    try:
        app('udp/start',{});tx('config',{'amplitude':.65,'noise':0,'offset':0,'corrupt':False})
        config=json.loads(json.dumps(old_rx));config['input'].update(kind='rtltcp',host='host.docker.internal',port=1235,sample_rate=288000)
        config['destinations']=[{'enabled':True,'protocol':'tcp','host':'host.docker.internal','port':10111}]
        rx('config',config);rx('start',{});wait(lambda:tx('status')['client'] is not None);time.sleep(1)
        tx('start',{})
        for protocol in ('tcp','udp'):
            emu('output',{'protocol':protocol,'host':'host.docker.internal','port':10113})
            before=max([e['id'] for e in app('events?limit=100')],default=0)
            emu('ais/send',{'scenario_ids':['type-5']})
            wait(lambda:any(e.get('ais_type')==5 and e['source'].startswith('tcp:') for e in app(f'events?limit=100&after={before}')))
            print(f'PASS: emulator {protocol.upper()} NMEA -> GMSK I/Q -> RTL-TCP -> AIS-catcher -> main PostgreSQL/REST Type 5')
        tx('stop',{});time.sleep(.2);count=tx('status')['counts'].get('modulated',0)
        emu('ais/send',{'scenario_ids':['type-5']});time.sleep(.5)
        assert tx('status')['counts'].get('modulated',0)==count,'Stop failed'
        assert tx('status')['queue']==0
        rx('stop',{});wait(lambda:tx('status')['client'] is None)
        rx('start',{});wait(lambda:tx('status')['client'] is not None);tx('start',{})
        time.sleep(.5);assert tx('status')['counts'].get('modulated',0)==count,'Stale replay on reconnect'
        print('PASS: authenticated control, stop, reconnect without stale replay')
    finally:
        tx('stop',{});tx('config',old_tx);rx('stop',{});rx('config',old_rx)
        emu('output',{k:old_output[k] for k in ('host','port','protocol')});app('udp/'+('start' if enabled else 'stop'),{})
if __name__=='__main__':main()
