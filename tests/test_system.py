import json
import socket
import time
import pytest
from pyais.encode import encode_dict
from app.parser import Decoder, checksum

GGA='$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47'
def sentence(body): return '$'+body+'*'+checksum(body)

def test_gga_and_invalid_checksum():
    d=Decoder(); r=d.parse(GGA,'a')
    assert r['status']=='ok' and r['latitude']==pytest.approx(48.1173)
    assert r['longitude']==pytest.approx(11.5166667)
    assert d.parse(GGA[:-2]+'00','a')['status']=='error'
    assert d.parse(GGA.split('*')[0],'a')['checksum_valid'] is None

def test_gn_rmc_invalid_fix_and_time():
    d=Decoder()
    r=d.parse(sentence('GNRMC,120000.00,A,3530.000,N,13942.000,E,12.4,90.0,230926,,,A'),'a')
    assert r['event_time']=='2026-09-23T12:00:00+00:00'
    assert r['latitude']==35.5
    r=d.parse(sentence('GNRMC,120000.00,V,3530.000,N,13942.000,E,12.4,90.0,230926,,,A'),'a')
    assert r['latitude'] is None

def test_unsupported_retained():
    r=Decoder().parse(sentence('GPXYZ,1,2,3'),'a')
    assert r['status']=='unsupported' and r['raw'].startswith('$GPXYZ')

def test_ais_multipart_source_isolation_and_expiry():
    parts=encode_dict({'msg_type':5,'mmsi':431234567,'shipname':'TEST SHIP'},talker_id='AI')
    assert len(parts)==2
    d=Decoder(ttl=.01)
    assert d.parse(parts[0],'a')['status']=='pending'
    assert d.parse(parts[1],'b')['status']=='error'
    r=d.parse(parts[1],'a')
    assert r['status']=='ok' and r['mmsi']=='431234567' and 'TEST SHIP' in r['decoded']['shipname']
    d.parse(parts[0],'a'); time.sleep(.02); d.expire()
    assert not d.groups and d.expired==1

def test_ais_unavailable_position():
    p=encode_dict({'msg_type':1,'mmsi':431234567,'lat':91,'lon':181},talker_id='AI')[0]
    r=Decoder().parse(p,'a');assert r['status']=='ok' and r['latitude'] is None

@pytest.fixture(scope='module')
def client(tmp_path_factory):
    import os
    root=tmp_path_factory.mktemp('server')
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as tcp:
        tcp.bind(('127.0.0.1',0)); tcp_port=tcp.getsockname()[1]
    os.environ.update(APP_TOKEN='test-token-with-at-least-24-chars',DATA_DIR=str(root),
                      DATABASE_URL=f'sqlite:///{root}/test.db',UDP_PORT=str(port),TCP_PORT=str(tcp_port))
    import app.main as main
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c: yield c,main,port

def login(c):
    assert c.post('/api/login',json={'token':'test-token-with-at-least-24-chars'}).status_code==200

def test_auth_and_origin(client):
    c,_,_=client
    assert c.get('/api/stats').status_code==401
    assert c.post('/api/login',json={'token':'wrong'}).status_code==401
    login(c)
    assert c.post('/api/udp/stop',headers={'Origin':'https://evil.example'}).status_code==403
    assert c.get('/ready').status_code==200

def test_real_udp_ws_and_export(client):
    c,main,port=client;login(c)
    with c.websocket_connect('/ws') as ws:
        assert ws.receive_json()['type']=='hello'
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.sendto((GGA+'\r\n'+GGA+'\r\n').encode(),('127.0.0.1',port))
        msg=ws.receive_json();assert msg['type']=='events' and len(msg['rows'])==2
    assert c.get('/api/stats').json()['runtime']['datagrams']==1
    geo=c.get('/api/export/geojson').json()
    assert len(geo['features'])==2 and geo['features'][0]['geometry']['coordinates'][0]==pytest.approx(11.5166667)
    assert len(c.get('/api/export/jsonl').text.splitlines())==2
    assert c.get('/api/events?limit=0').status_code==422

def test_file_progress_errors_and_persistence(client):
    c,main,_=client;login(c)
    r=c.post('/api/files?filename=../../example.log',content=(GGA+'\nBAD\n'+GGA[:-2]+'00\n').encode())
    assert r.status_code==202;job_id=r.json()['id']
    for _ in range(200):
        job=next(j for j in c.get('/api/jobs').json() if j['id']==job_id)
        if job['status']=='completed': break
        time.sleep(.01)
    assert job['status']=='completed' and job['ok']==1 and job['error']==2
    assert job['filename']=='example.log'
    events=c.get('/api/events',params={'source':'file:'+job_id}).json()
    assert len(events)==3
    from app.store import Store
    store=Store(str(main.state.store.engine.url))
    assert store.stats()['total']>=5 and store.load_jobs()[0]['id']==job_id
    store.engine.dispose()

def test_upload_limit_and_pause(client):
    c,main,port=client;login(c)
    assert c.post('/api/files',content=b'a',headers={'Content-Length':str(main.MAX_FILE+1)}).status_code==413
    c.post('/api/udp/stop');before=c.get('/api/stats').json()['runtime']['datagrams']
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s: s.sendto(GGA.encode(),('127.0.0.1',port))
    time.sleep(.05)
    assert c.get('/api/stats').json()['runtime']['datagrams']==before
    c.post('/api/udp/start')

def test_emulator_tcp_end_to_end(client):
    c,main,_=client;login(c)
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'emulator'))
    from server import Simulator
    emulator=Simulator()
    emulator.config.interval=.2
    frames=emulator.generate()
    assert any(line.startswith('!AIVDM') for line in frames)
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.connect(('127.0.0.1',main.TCP_PORT))
        sock.sendall(('\r\n'.join(frames)+'\r\n').encode())
        for _ in range(200):
            if c.get('/api/stats').json()['runtime']['tcp_sentences']>=len(frames):break
            time.sleep(.01)
    for _ in range(200):
        events=c.get('/api/events?limit=100').json()
        if any(r['source'].startswith('tcp:') and r['mmsi']=='431234567' for r in events):break
        time.sleep(.01)
    assert any(r['source'].startswith('tcp:') and r['sentence_type']=='RMC' and r['latitude'] for r in events)
    assert any(r['source'].startswith('tcp:') and r['sentence_type']=='VDM' and r['mmsi']=='431234567' for r in events)
    assert c.get('/health').json()['tcp_port']==main.TCP_PORT

def test_watchlist_matches_mmsi_and_imo_and_persists_alerts(client):
    c,main,port=client;login(c)
    a={'mmsi':'431555111','name':'監視船A','notes':'確認対象'}
    b={'imo':'1234567','name':'監視船B','notes':''}
    assert c.post('/api/watchlist',json={'name':'no identifiers'}).status_code==422
    assert c.post('/api/watchlist',json={'mmsi':'123','name':'bad'}).status_code==422
    first=c.post('/api/watchlist',json=a);second=c.post('/api/watchlist',json=b)
    assert first.status_code==201 and second.status_code==201
    conflict=c.post('/api/watchlist',json={'mmsi':a['mmsi'],'name':'duplicate'})
    assert conflict.status_code==409 and conflict.json()['existing'][0]['id']==first.json()['id']
    assert c.put('/api/watchlist/'+str(first.json()['id']),json={'imo':b['imo'],'name':'collision'}).status_code==409
    parts=encode_dict({'msg_type':5,'mmsi':a['mmsi'],'imo':int(b['imo']),'shipname':'WATCH VESSEL'},talker_id='AI')
    with c.websocket_connect('/ws') as ws:
        assert ws.receive_json()['type']=='hello'
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.sendto(('\r\n'.join(parts)+'\r\n').encode(),('127.0.0.1',port))
        alerts=[]
        for _ in range(3):
            msg=ws.receive_json()
            alerts+=msg.get('alerts',[])
            if len(alerts)==2:break
        assert {v['matched_by'] for v in alerts}=={'MMSI','IMO'}
    assert c.get('/api/identities/'+a['mmsi']).json()['imo']==b['imo']
    assert len(c.get('/api/watch-alerts').json())==2
    # Type 1 has no IMO field; matching uses the Type 5 identity learned above.
    from datetime import datetime, timedelta, timezone
    with main.state.store.engine.begin() as db:
        db.execute(main.state.store.watch.update().where(main.state.store.watch.c.id==second.json()['id'])
                   .values(last_alert_at=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()))
    position=encode_dict({'msg_type':1,'mmsi':a['mmsi'],'lat':35.65,'lon':139.75},talker_id='AI')[0]
    main.state.store.add([Decoder().parse(position,'test:identity')])
    assert c.get('/api/watch-alerts').json()[0]['matched_by']=='IMO'
    location=c.get('/api/vessels/'+a['mmsi']+'/position')
    assert location.status_code==200 and location.json()['latitude']==pytest.approx(35.65)
    assert c.get('/api/vessels/431999999/position').status_code==404
    assert c.get('/api/vessels/invalid/position').status_code==422
    assert c.put('/api/watchlist/'+str(first.json()['id']),json={**a,'name':'更新済み'}).json()['name']=='更新済み'
    assert c.delete('/api/watchlist/'+str(first.json()['id'])).status_code==200
    assert c.delete('/api/watchlist/'+str(second.json()['id'])).status_code==200
    assert c.get('/api/watchlist').json()==[]

def test_delete_saved_database_data_requires_confirmation_and_pauses_ingest(client):
    c,main,port=client
    c.cookies.clear()
    assert c.request('DELETE','/api/data',json={'confirm':'全件削除','expected_total':0}).status_code==401
    login(c)
    total=c.get('/api/stats').json()['total']
    watched=c.post('/api/watchlist',json={'mmsi':'431777333','name':'保持対象'}).json()
    assert total>0 and c.get('/api/jobs').json()
    assert c.request('DELETE','/api/data',json={'confirm':'全件削除','expected_total':total},
                    headers={'Origin':'https://evil.example'}).status_code==403
    assert c.request('DELETE','/api/data',json={'confirm':'wrong','expected_total':total}).status_code==400
    main.state.jobs['busy']={'status':'running'}
    try:
        assert c.request('DELETE','/api/data',json={'confirm':'全件削除','expected_total':total}).status_code==409
    finally:
        main.state.jobs.pop('busy')
    assert c.get('/api/stats').json()['total']==total
    with c.websocket_connect('/ws') as ws:
        assert ws.receive_json()['type']=='hello'
        response=c.request('DELETE','/api/data',json={'confirm':'全件削除','expected_total':total})
        assert response.status_code==200
        assert response.json()['events_deleted']==total
        assert response.json()['jobs_deleted']>=1
        assert response.json()['source_files_kept']
        assert ws.receive_json()['type']=='reset'
    assert c.get('/api/stats').json()['total']==0
    assert not c.get('/api/stats').json()['udp_enabled']
    assert c.get('/api/events').json()==[] and c.get('/api/jobs').json()==[]
    assert main.state.store.load_jobs()==[]
    assert c.get('/api/watchlist').json()[0]['id']==watched['id']
    assert c.get('/api/watch-alerts').json()==[]
    c.delete('/api/watchlist/'+str(watched['id']))
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.sendto(GGA.encode(),('127.0.0.1',port))
    time.sleep(.02)
    assert c.get('/api/stats').json()['total']==0
    assert c.post('/api/udp/start').status_code==200
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.sendto(GGA.encode(),('127.0.0.1',port))
    for _ in range(200):
        if c.get('/api/stats').json()['total']==1:break
        time.sleep(.01)
    assert c.get('/api/stats').json()['total']==1
