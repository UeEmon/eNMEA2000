import pytest
from sqlalchemy import create_engine
from app.parser import Decoder, checksum
from app.store import Store


def padsb(body):
    return '$' + body + '*' + checksum(body)


JAL = padsb('PADSB,86D3A1,JAL123,35.549400,139.779800,12500,420.0,287.0,-1472,3')


def test_padsb_decoded_as_aircraft():
    r = Decoder().parse(JAL, 'tcp:a')
    assert r['status'] == 'ok' and r['sentence_type'] == 'ADSB' and r['icao'] == '86D3A1'
    assert r['mmsi'] is None and r['latitude'] == pytest.approx(35.5494)
    d = r['decoded']
    assert d['callsign'] == 'JAL123' and d['altitude_ft'] == 12500 and d['vertical_rate_fpm'] == -1472
    assert d['track_deg'] == 287.0 and d['category'] == 3


@pytest.mark.parametrize('body', ['PADSB,86D3A1,JAL123,95,139,1,1,1,1,3', 'PADSB,XYZ123,JAL123,35,139,1,1,1,1,3',
                                  'PADSB,86D3A1,JAL123,35,139', 'PADSB,86D3A1,jal,35,139,1,1,1,1,3'])
def test_padsb_rejects_invalid(body):
    r = Decoder().parse(padsb(body), 'a')
    assert r['status'] == 'error' and r['sentence_type'] == 'ADSB'


def test_padsb_unknown_position_kept():
    r = Decoder().parse(padsb('PADSB,86D3A1,JAL123,,,,,,,'), 'a')
    assert r['status'] == 'ok' and r['latitude'] is None and r['decoded']['altitude_ft'] is None


def test_existing_database_gets_icao_column(tmp_path):
    url = f'sqlite:///{tmp_path}/old.db'
    engine = create_engine(url)
    with engine.begin() as c:
        c.exec_driver_sql('CREATE TABLE events (id INTEGER PRIMARY KEY, received_at VARCHAR(40), source VARCHAR(180), '
                          'sentence_type VARCHAR(24), status VARCHAR(24), mmsi VARCHAR(16), latitude FLOAT, '
                          'longitude FLOAT, payload TEXT)')
        c.exec_driver_sql("INSERT INTO events (received_at, source, sentence_type, status, payload) "
                          "VALUES ('2026-10-13T00:00:00+00:00', 'a', 'GGA', 'ok', '{}')")
    engine.dispose()
    store = Store(url)
    try:
        store.add([Decoder().parse(JAL, 'tcp:a')])
        assert len(store.recent()) == 2
        assert [r['decoded']['callsign'] for r in store.recent(icao='86D3A1')] == ['JAL123']
    finally:
        store.engine.dispose()

