import json
import socket
import time
import pytest
from pyais.encode import encode_dict
from app.parser import AIS_TYPE_NAMES, Decoder, checksum

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


def test_legacy_ais_type_zero_is_retained():
    p='!AIVDM,1,1,,B,0S9edj0P03PecbBN`ja@0?w42cFC,0*7C'
    r=Decoder().parse(p,'legacy')
    assert r['status']=='ok' and r['ais_type']==0


AIS_TYPE_SAMPLES = {
    0: '!AIVDM,1,1,,B,0S9edj0P03PecbBN`ja@0?w42cFC,0*7C',
    1: '!AIVDO,1,1,,A,1S9edj?003PecbBN`ja@0?w5R000,0*24',
    2: '!AIVDM,1,1,,A,23aFfl0P00PCR?0MEB@h0?w020S7,0*68',
    3: '!AIVDM,1,1,,A,35NSH95001G?wopE`beasVk@0E5:,0*6F',
    4: '!AIVDO,1,1,,A,44R33:1uUK2F`q?mP0@@GoQ00000,0*08',
    5: (
        '!AIVDM,2,1,0,B,55?MbV02;H;s<HtKP00EHE:0@T4@Dl0000000000L961O5Gf0P3QEp6ClRh0,0*75',
        '!AIVDM,2,2,0,B,00000000000,2*27',
    ),
    6: '!AIVDM,1,1,,B,6B?n;be:cbapald3c;i6?Ow4,0*78',
    7: '!AIVDO,1,1,,A,739UOj0jFs9R0000000000000000,0*6D',
    8: '!AIVDM,1,1,,B,85Mwp`1Kf0>dg4Huwt@,2*5B',
    9: '!AIVDO,1,1,,A,91b55wi;hbOS@OdQAC062Ch2089h,0*31',
    10: '!AIVDO,1,1,,A,:6TMCD1GOS60,0*5A',
    11: '!AIVDM,1,1,,B,;4R33:1uUK2F`q?mOt@@GoQ00000,0*5D',
    12: '!AIVDO,1,1,,A,<42Lati0W:Ov=C7P6B?=Pjoihhjhqq,0*1B',
    13: '!AIVDM,1,1,,A,=39UOj0jFs9R,0*65',
    14: '!AIVDO,1,1,,A,>5?Per18=HB1U:1@E=B0m<L,2*53',
    15: '!AIVDO,1,1,,A,?h3Ovn1GP<K0<P@59a00000000000,2*05',
    16: '!AIVDO,1,1,,A,@01uEO@mMk7P<P0007R@0000,0*0F',
    17: '!AIVDO,1,1,,A,A0476BQ>J@`<h0>dg4Huwt@,2*36',
    18: '!AIVDO,1,1,,A,B5NJ;PP2aUl4ot5Isbl6GwsUkP06,0*35',
    19: '!AIVDO,1,1,,A,C5N3SRP0=nJGEBT>NhWAwwo862PaLELTBJ:V00000000S0D:R220,0*25',
    20: '!AIVDO,1,1,,A,D028rqP<QNfp000000000000000,2*0E',
    21: '!AIVDO,1,1,,A,E4eHJhPR37q0000000000000000KUOSc=rq4h00000a@2000000000000000,4*39',
    22: '!AIVDO,1,1,,A,F0@W>gCP00PH=JrN84000?hB0000,0*75',
    23: '!AIVDO,1,1,,A,G02:Kn01R`sn@291nj600000900,2*13',
    24: '!AIVDO,1,1,,A,H52KMe@Pm>0Htt85800000000000,0*36',
    25: '!AIVDM,1,1,,A,I6Ki`kuVv6HT4SBbE@,4*49',
    26: '!AIVDM,1,1,,A,J6Ki`kuVv6HT4SBbE@Rck@,4*50',
    27: '!AIVDO,1,1,,A,K35E2b@U19PFdLbL,0*71',
    28: '!AIVDO,1,1,,A,L1mg=5@@G:uk?S:I0@ph>A5E>L@1,0*43',
}


@pytest.mark.parametrize('message_type', range(29))
def test_all_ais_message_types_are_decoded(message_type):
    decoder=Decoder()
    sample=AIS_TYPE_SAMPLES[message_type]
    parts=sample if isinstance(sample, tuple) else (sample,)
    rows=[decoder.parse(part, f'type:{message_type}') for part in parts]
    row=rows[-1]
    assert row['status']=='ok', (message_type, row)
    assert row['decoded']['msg_type']==message_type
    assert row['ais_type']==message_type
    assert row['ais_type_name']==AIS_TYPE_NAMES[message_type]


# Fixed wire fixtures include the addressed spare bits and variable Type 26
# trailer in ITU-R M.1371-6 tables 79/81. They intentionally do not use the
# pyais encoder, which omits those spare fields in version 3.2.3.
@pytest.mark.parametrize('message_type,addressed,structured,frame', [
    (25,False,False,'!AIVDM,1,1,,A,I6Ki`kjbE@,4*79'),
    (25,False,True, '!AIVDM,1,1,,A,I6Ki`klB=:aE,0*7D'),
    (25,True,False, '!AIVDM,1,1,,A,I6Ki`kqVv6HTbUD,2*7A'),
    (25,True,True,  '!AIVDM,1,1,,A,I6Ki`kuVv6HT4SBbE@,4*49'),
    (26,False,False,'!AIVDM,1,1,,A,J6Ki`kjbE@Rck@,4*60'),
    (26,False,True, '!AIVDM,1,1,,A,J6Ki`klB=:aE2:g=,0*2C'),
    (26,True,False, '!AIVDM,1,1,,A,J6Ki`kqVv6HTbUD8btl,2*3B'),
    (26,True,True,  '!AIVDM,1,1,,A,J6Ki`kuVv6HT4SBbE@Rck@,4*50'),
])
def test_binary_variants_keep_only_application_bits(message_type,addressed,structured,frame):
    row=Decoder().parse(frame,'binary')
    assert row['status']=='ok',row
    data=row['decoded']
    assert data['msg_type']==message_type
    assert data['addressed'] is addressed and data['structured'] is structured
    assert data['data']=='aa55' and data['data_bit_length']==16
    assert row['latitude'] is None and row['longitude'] is None
    if addressed:
        assert data['dest_mmsi']==431888777 and data['destination_spare']==0
    if structured:
        assert data['app_id']==0x1234 and data['dac']==72 and data['fid']==52
    else:
        assert 'app_id' not in data
    if message_type==26:
        assert data['radio']==0x8abcd and data['radio_spare']==0
        assert data['communication_state_selector']==1 and data['communication_state']==0xabcd
    assert json.loads(json.dumps(row))['decoded']==data


@pytest.mark.parametrize('frame', [
    '!AIVDM,1,1,,A,J6Ki`kjbE@Rck@,4*60',
    '!AIVDM,1,1,,A,I6Ki`kuVv6HT4SBbE@,4*49',
])
def test_binary_truncation_is_an_error(frame):
    fields=frame[1:].split('*')[0].split(',')
    fields[5]=fields[5][:8]
    fields[6]='0'
    body=','.join(fields)
    row=Decoder().parse('!'+body+'*'+checksum(body),'truncated')
    assert row['status']=='error' and row['raw'].startswith('!AIVDM')


def test_type26_multipart_preserves_large_binary_and_radio():
    frames=["!AIVDM,3,1,7,A,J6Ki`kuVv6HT4SBbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaE,0*6D","!AIVDM,3,2,7,A,bUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFb,0*3B","!AIVDM,3,3,7,A,EJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaE2:g=,0*50"]
    decoder=Decoder()
    rows=[decoder.parse(frame,'multi-binary') for frame in frames]
    assert [row['status'] for row in rows]==['pending','pending','ok']
    data=rows[-1]['decoded']
    assert data['data']=='aa55'*56 and data['data_bit_length']==896
    assert data['dest_mmsi']==431888777 and data['app_id']==0x1234
    assert data['radio']==0x8abcd and data['radio_spare']==0


def test_type17_signed_coordinates_and_no_correction_position():
    row=Decoder().parse('!AIVDM,1,1,,A,A6Ki`kjp>CChh0,4*68','reference')
    assert row['status']=='ok'
    assert row['latitude']==-37.75 and row['longitude']==-122.5
    assert row['decoded']['data']=='' and row['decoded']['data_bit_length']==0
    unavailable=Decoder().parse('!AIVDM,1,1,,A,A6Ki`kib3Qba00,4*16','reference')
    assert unavailable['status']=='ok' and unavailable['latitude'] is None
    assert unavailable['decoded']['lat']==91 and unavailable['decoded']['lon']==181
    positive=Decoder().parse(AIS_TYPE_SAMPLES[17],'reference')
    assert positive['longitude']==pytest.approx(133.82)
    assert positive['latitude']==pytest.approx(34.303333)


@pytest.mark.parametrize('frame,message_type', [
    ('!AIVDO,1,1,,A,F6Ki`kh00005hLQJ?;NS2gj00000,0*09',22),
    ('!AIVDO,1,1,,A,G6Ki`kjp>@e7UgAQGq000000000,2*6C',23),
])
def test_region_coordinates_use_degrees_without_vessel_position(frame,message_type):
    row=Decoder().parse(frame,'area');data=row['decoded']
    assert row['status']=='ok' and data['msg_type']==message_type
    assert (data['ne_lon'],data['ne_lat'],data['sw_lon'],data['sw_lat'])==(-122.5,38.5,-123.5,37.5)
    assert row['latitude'] is None and row['longitude'] is None


def test_type24_parts_auxiliary_and_type19_preserve_identity(tmp_path):
    from app.store import Store
    store=Store(f'sqlite:///{tmp_path}/identities.db')
    decoder=Decoder();mmsi=431777999
    def save(fields):
        rows=[decoder.parse(part,'identity') for part in encode_dict(fields,talker_id='AI')]
        assert rows[-1]['status']=='ok',rows[-1]
        store.add(rows)
        return rows[-1]
    try:
        save({'msg_type':5,'mmsi':mmsi,'shipname':'INITIAL','imo':1234567})
        save({'msg_type':19,'mmsi':mmsi,'shipname':'CLASS B','lat':35.65,'lon':139.75})
        save({'msg_type':24,'mmsi':mmsi,'partno':0,'shipname':'PART A'})
        part_b=save({'msg_type':24,'mmsi':mmsi,'partno':1,'callsign':'CALL123','ship_type':70,'to_bow':40})
        assert part_b['decoded']['callsign']=='CALL123' and part_b['decoded']['to_bow']==40
        save({'msg_type':24,'mmsi':mmsi,'partno':0,'shipname':'@@ @'})
        assert store.identity(str(mmsi))=={'mmsi':str(mmsi),'imo':'1234567','shipname':'PART A'}
        auxiliary=save({'msg_type':24,'mmsi':981234567,'partno':1,'mothership_mmsi':431888777})
        assert auxiliary['decoded']['mothership_mmsi']==431888777
        persisted=store.recent(mmsi=str(mmsi))
        assert any(r['decoded'].get('callsign')=='CALL123' for r in persisted)
    finally:
        store.engine.dispose()

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


@pytest.mark.parametrize('input_kind',['udp','tcp','file'])
def test_all_types_ingest_publish_persist_and_export(client,input_kind):
    c,main,port=client;login(c)
    frames=[];expected={}
    for message_type,sample in AIS_TYPE_SAMPLES.items():
        parts=sample if isinstance(sample,tuple) else (sample,)
        frames.extend(parts)
        decoder=Decoder()
        expected[message_type]=[decoder.parse(part,'expected') for part in parts][-1]['decoded']
    payload=('\r\n'.join(frames)+'\r\n').encode()
    with c.websocket_connect('/ws') as ws:
        assert ws.receive_json()['type']=='hello'
        if input_kind=='file':
            response=c.post('/api/files?filename=ais-all-types.log',content=payload)
            assert response.status_code==202
            job_id=response.json()['id'];source='file:'+job_id
            for _ in range(200):
                job=next(j for j in c.get('/api/jobs').json() if j['id']==job_id)
                if job['status']=='completed':break
                time.sleep(.01)
            assert job['status']=='completed' and job['ok']==29 and job['pending']==1 and job['error']==0
        else:
            protocol=socket.SOCK_DGRAM if input_kind=='udp' else socket.SOCK_STREAM
            with socket.socket(socket.AF_INET,protocol) as sock:
                sock.connect(('127.0.0.1',port if input_kind=='udp' else main.TCP_PORT))
                source=f'{input_kind}:127.0.0.1:{sock.getsockname()[1]}'
                sock.sendall(payload)
        published=[]
        while len(published)<len(frames):
            message=ws.receive_json()
            assert message['type']=='events'
            published.extend(message['rows'])
        assert {r['ais_type'] for r in published if r['status']=='ok'}==set(range(29))
    for _ in range(200):
        events=c.get('/api/events',params={'source':source,'limit':100}).json()
        if len(events)==len(frames):break
        time.sleep(.01)
    assert len(events)==len(frames)
    assert {r['raw'] for r in events}==set(frames)
    actual={r['ais_type']:r['decoded'] for r in events if r['status']=='ok'}
    assert actual==expected
    exported=[json.loads(line) for line in c.get('/api/export/jsonl',params={'source':source}).text.splitlines()]
    assert {r['ais_type']:r['decoded'] for r in exported if r['status']=='ok'}==expected
    from app.store import Store
    reopened=Store(str(main.state.store.engine.url))
    try:
        assert {r['ais_type']:r['decoded'] for r in reopened.recent(100,source=source) if r['status']=='ok'}==expected
    finally:
        reopened.engine.dispose()

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
