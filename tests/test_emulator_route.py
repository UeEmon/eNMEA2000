import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'emulator'))
from fastapi.testclient import TestClient
from server import Config, Route, Simulator, Waypoint, app, navigation
from app.parser import Decoder

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
