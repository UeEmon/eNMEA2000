import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'emulator'))
from fastapi.testclient import TestClient
from server import Config, Route, Simulator, Waypoint, app, navigation
from app.parser import Decoder
from ais_suite import SCENARIOS, with_mmsi

def test_route_reaches_destination_and_emits_real_nmea():
    sim=Simulator()
    dest=Waypoint(lat=35.651,lon=139.751)
    sim.config=Config(latitude=35.65,longitude=139.75,course=180,speed=60,interval=60,vessel_count=1,route=Route(waypoints=[dest]))
    frames=sim.generate()
    assert sim.route_done and sim.route_index==0
    assert sim.latitude==dest.lat and sim.longitude==dest.lon
    assert sim.config.course!=180
    decoded=Decoder()
    rows=[decoded.parse(frame,'test') for frame in frames]
    assert any(r['sentence_type']=='RMC' and r['latitude'] and r['status']=='ok' for r in rows)
    assert any(r['sentence_type']=='VDM' and r['mmsi']=='431234567' for r in rows)
    second=sim.generate()
    assert sim.current_speed==0
    assert Decoder().parse(second[0],'test')['decoded']['spd_over_grnd']==0.0

def test_zero_length_loop_stays_stationary():
    sim=Simulator()
    sim.config=Config(route=Route(waypoints=[Waypoint(lat=35.65,lon=139.75)],loop=True))
    sim.generate()
    assert (sim.latitude,sim.longitude)==(35.65,139.75) and sim.current_speed==0

def test_message_type_selection_is_independent_and_legacy_flags_still_work():
    sim=Simulator()
    sim.config=Config(rmc=False,gga=True,ais_type1=False,ais_type5=True,vessel_count=1)
    first=sim.generate()
    assert len([line for line in first if line.startswith('$GNGGA')])==1
    assert not any(line.startswith('$GNRMC') for line in first)
    ais=[line for line in first if line.startswith('!AIVDM')]
    assert ais and Decoder().parse(ais[0],'test')['sentence_type']=='VDM'
    assert sim.status()['vessels']==[]  # Static Type 5 does not provide positions.
    second=sim.generate()
    assert len(second)==1 and second[0].startswith('$GNGGA')
    sim.config=Config(gps=False,ais=False)
    assert sim.generate()==[]
    sim.config=Config(rmc=True,gga=False,ais_type1=True,ais_type5=False,vessel_count=1)
    frames=sim.generate()
    assert any(line.startswith('$GNRMC') for line in frames)
    assert not any(line.startswith('$GNGGA') for line in frames)
    assert len([line for line in frames if line.startswith('!AIVDM')])==1

def test_route_api_live_edit_validation():
    with TestClient(app) as client:
        response=client.post('/api/route',json={'waypoints':[{'lat':35.66,'lon':139.76}], 'loop':True})
        assert response.status_code==200 and response.json()['config']['route']['loop']
        assert client.post('/api/position',json={'lat':35.62,'lon':139.7}).json()['position']['lat']==35.62
        assert client.post('/api/course',json={'course':405}).status_code==422
        assert client.post('/api/route',json={'waypoints':[{'lat':91,'lon':139.76}]}).status_code==422
        config=Config(latitude=35.62,longitude=139.7,course=90,speed=12,interval=.2,route=Route(waypoints=[Waypoint(lat=35.63,lon=139.71)]))
        started=client.post('/api/start',json=config.model_dump())
        assert started.status_code==200
        new_route=client.post('/api/route',json={'waypoints':[{'lat':35.61,'lon':139.69}]}).json()
        assert new_route['route_index']==0 and not new_route['route_done']
        client.post('/api/stop')


def test_ais_type5_fields_are_encoded_and_validated():
    from pyais import decode
    from server import AisType5
    sim=Simulator()
    sim.config=Config(gps=False,ais_type1=False,vessel_count=2,mmsi_start=431111111,
        ais5=AisType5(shipname='SEA TEST',callsign='CALL123',ship_type=80,
            imo=1234567,to_bow=42,to_stern=18,to_port=7,to_starboard=9,
            month=12,day=25,hour=13,minute=45,draught=7.2,destination='OSAKA',dte=True))
    frames=sim.generate()
    assert len(frames)==4
    first=decode(*frames[:2]).asdict()
    second=decode(*frames[2:]).asdict()
    assert first['mmsi']==431111111 and second['mmsi']==431111112
    assert first['shipname'].strip('@ ')== 'SEA TEST 1'
    assert second['shipname'].strip('@ ')== 'SEA TEST 2'
    assert first['callsign'].strip('@ ')== 'CALL123'
    assert first['ship_type']==80 and first['imo']==1234567
    assert first['draught']==7.2 and first['destination'].strip('@ ')== 'OSAKA'
    assert first['month']==12 and first['day']==25 and first['hour']==13 and first['minute']==45
    assert first['dte'] is True
    assert sim.generate()==[]
    with TestClient(app) as client:
        for field,value in [('callsign','日本語'),('shipname','TOO LONG A VESSEL NAME'),('draught',1.25),('to_port',64)]:
            assert client.post('/api/start',json={'ais5':{field:value}}).status_code==422


def test_ais_suite_covers_every_type_and_variant_with_valid_wire_frames():
    assert {s.message_type for s in SCENARIOS} == set(range(29))
    assert {'type-5', 'type-24-a', 'type-24-b', 'type-24-aux',
            'type-26-multipart'} <= {s.id for s in SCENARIOS}
    assert len([s for s in SCENARIOS if s.message_type == 25]) == 4
    assert len([s for s in SCENARIOS if s.message_type == 26]) == 5
    for scenario in SCENARIOS:
        decoder = Decoder()
        rows = [decoder.parse(frame, scenario.id) for frame in scenario.frames]
        assert [row['status'] for row in rows[:-1]] == ['pending'] * (len(rows) - 1), scenario.id
        assert rows[-1]['status'] == 'ok', (scenario.id, rows[-1])
        assert rows[-1]['ais_type'] == scenario.message_type


def test_all_type_ring_layout_and_unique_mmsi_keep_every_fixture_decodable():
    from server import ais_ring_layout
    from pyais.encode import encode_dict
    from collections import Counter
    center = Waypoint(lat=35.65, lon=139.75)
    markers = ais_ring_layout(center, 2, SCENARIOS)
    assert Counter(marker['ring'] for marker in markers) == {1: 7, 2: 14, 3: 21}
    assert len({marker['mmsi'] for marker in markers}) == 42
    for scenario, marker in zip(SCENARIOS, markers):
        distance, _ = navigation(center.lat, center.lon, Waypoint(lat=marker['lat'], lon=marker['lon']))
        assert abs(distance - marker['ring'] * 2) < 0.002
        decoder = Decoder()
        rows = [decoder.parse(frame, scenario.id) for frame in with_mmsi(scenario.frames, marker['mmsi'])]
        assert rows[-1]['status'] == 'ok', (scenario.id, rows[-1])
        assert rows[-1]['mmsi'] == str(marker['mmsi'])
        assert rows[-1]['ais_type'] == scenario.message_type
        position = encode_dict({'msg_type': 1, 'mmsi': marker['mmsi'], 'lat': marker['lat'],
                                'lon': marker['lon'], 'speed': 0, 'course': 0, 'heading': 0},
                               talker_id='AI', sentence_type='VDM')
        plotted = decoder.parse(position[0], scenario.id)
        assert plotted['status'] == 'ok' and plotted['mmsi'] == rows[-1]['mmsi']
        assert abs(plotted['latitude'] - marker['lat']) < 0.00001
        assert abs(plotted['longitude'] - marker['lon']) < 0.00001


def test_ais_suite_api_sends_selected_scenarios_over_tcp(monkeypatch):
    import socket
    import threading
    import server

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(5)
    monkeypatch.setattr(server, 'HOST', '127.0.0.1')
    monkeypatch.setattr(server, 'PORT', listener.getsockname()[1])
    received = []
    def accept():
        conn, _ = listener.accept()
        with conn:
            chunks = []
            while data := conn.recv(65536):
                chunks.append(data)
            received.append(b''.join(chunks))
    thread = threading.Thread(target=accept)
    thread.start()
    try:
        with TestClient(app) as client:
            catalog = client.get('/api/ais/scenarios').json()
            assert catalog['types'] == list(range(29))
            assert client.post('/api/ais/send', json={'scenario_ids':['missing']}).status_code == 422
            assert client.post('/api/ais/send', json={'scenario_ids':['type-5','type-5']}).status_code == 422
            result = client.post('/api/ais/send', json={'scenario_ids':['type-5','type-26-multipart']})
            assert result.status_code == 200, result.text
            assert result.json()['sentences'] == 5
        thread.join(timeout=5)
        assert not thread.is_alive()
        expected = [frame for id in ('type-5','type-26-multipart')
                    for frame in next(s.frames for s in SCENARIOS if s.id == id)]
        assert received == [('\r\n'.join(expected) + '\r\n').encode('ascii')]
    finally:
        listener.close()


def test_ring_motion_positions_keep_radius_spacing_and_valid_speed():
    import math
    from server import RingMotion, AisSuiteRequest
    for spacing in (.2, 2, 20):
        motion = RingMotion()
        motion.configure(AisSuiteRequest(scenario_ids=[s.id for s in SCENARIOS],
                         center=Waypoint(lat=35, lon=179.99), spacing_nm=spacing))
        assert motion.interval >= len(SCENARIOS) / 60
        assert motion.rate > 0
        markers, frames = motion.frames_at(45)
        decoder = Decoder()
        for marker, frame in zip(markers, frames):
            row = decoder.parse(frame, 'motion')
            assert row['status'] == 'ok'
            assert 0 < row['decoded']['speed'] <= 80
            assert 0 <= row['decoded']['course'] < 360
            distance, _ = navigation(35, 179.99, Waypoint.model_construct(lat=marker['lat'],lon=marker['lon']))
            assert abs(distance - marker['ring'] * spacing) < .002
        for ring in (1, 2, 3):
            angles = [m['angle'] for m in markers if m['ring'] == ring]
            gaps = [(angles[(i+1) % len(angles)] - angle) % 360 for i, angle in enumerate(angles)]
            assert max(gaps)-min(gaps) < 1e-9
        assert motion.frames_at(0)[0] == motion.frames_at(360)[0]


def test_ring_motion_transmits_updates_and_stop_closes_tcp(monkeypatch):
    import asyncio
    import server
    async def exercise():
        received = []
        closed = asyncio.Event()
        async def handle(reader, writer):
            try:
                while line := await reader.readline():
                    received.append(line.decode().strip())
            finally:
                writer.close()
                await writer.wait_closed()
                closed.set()
        listener = await asyncio.start_server(handle, '127.0.0.1', 0)
        monkeypatch.setattr(server, 'HOST', '127.0.0.1')
        monkeypatch.setattr(server, 'PORT', listener.sockets[0].getsockname()[1])
        motion = server.RingMotion()
        motion.configure(server.AisSuiteRequest(scenario_ids=['type-1'],center=Waypoint(lat=35,lon=139)))
        motion.active = True
        motion.task = asyncio.create_task(motion.run())
        try:
            deadline = asyncio.get_running_loop().time() + 5
            while len(received) < 2 and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(.05)
            await motion.stop()
            await asyncio.wait_for(closed.wait(), 2)
            assert not motion.active and not motion.connected and motion.task is None
            rows = [Decoder().parse(frame,'motion') for frame in received]
            assert len(rows) >= 2 and all(row['status']=='ok' for row in rows)
            assert rows[0]['latitude'] != rows[1]['latitude'] or rows[0]['longitude'] != rows[1]['longitude']
        finally:
            await motion.stop()
            listener.close()
            await listener.wait_closed()
    asyncio.run(exercise())
