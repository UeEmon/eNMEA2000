"""Actual TCP/UDP receivers exercise all emulator output paths."""
import asyncio
import json
import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1] / 'emulator'))
import server


@pytest.fixture
def destination(monkeypatch, tmp_path):
    monkeypatch.setattr(server, 'OUTPUT_FILE', tmp_path / 'output.json')
    monkeypatch.setattr(server, 'output_override', None)
    return server.OUTPUT_FILE


def test_destination_validation_and_persistence(destination):
    with TestClient(server.app) as client:
        for body in [dict(host='http://host:123', port=123), dict(host='a/b', port=123),
                     dict(host='', port=123), dict(host='host', port=0),
                     dict(host='host', port=65536), dict(host='host', port=123, protocol='other')]:
            assert client.post('/api/output', json=body).status_code == 422
        config = dict(host='192.168.1.50', port=10110, protocol='udp')
        response = client.post('/api/output', json=config)
        assert response.status_code == 200
        assert response.json()['output'] == config
        assert not response.json()['active'] and not response.json()['motion']['active']
        assert json.loads(destination.read_text()) == config
        assert server.OutputConfig.model_validate_json(destination.read_text()).model_dump() == config
        assert client.get('/api/output').json() == config
        assert client.post('/api/output', json=dict(host='::1', port=10111)).status_code == 200
        assert client.get('/api/status').json()['target'] == 'TCP [::1]:10111'


def test_selected_suite_udp_datagrams_and_target_switch(destination):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(('127.0.0.1', 0)); receiver.settimeout(2)
        with TestClient(server.app) as client:
            assert client.post('/api/output', json=dict(host='127.0.0.1', port=receiver.getsockname()[1], protocol='udp')).status_code == 200
            response = client.post('/api/ais/send', json={'scenario_ids': ['type-5']})
            assert response.status_code == 200
            expected = server.BY_ID['type-5'].frames
            assert [receiver.recv(2048) for _ in expected] == [(line+'\r\n').encode() for line in expected]
            response = client.post('/api/ais/send', json={'scenario_ids': [s.id for s in server.SCENARIOS]})
            assert response.status_code == 200
            expected = [frame for scenario in server.SCENARIOS for frame in scenario.frames]
            assert [receiver.recv(2048) for _ in expected] == [(line+'\r\n').encode() for line in expected]
            # Saving a new destination stops both continuous producers, including live UDP output.
            client.post('/api/start', json={'interval': .2})
            receiver.recv(2048)
            request = dict(scenario_ids=['type-1'], center={'lat':35, 'lon':139})
            assert client.post('/api/ais/motion/start', json=request).status_code == 200
            response = client.post('/api/output', json=dict(host='127.0.0.1', port=9, protocol='tcp'))
            assert response.status_code == 200
            assert not response.json()['active'] and not response.json()['motion']['active']
            # Drain datagrams already sent, then ensure no further updates reach the old target.
            receiver.settimeout(.1)
            try:
                while True: receiver.recv(2048)
            except socket.timeout: pass
            with pytest.raises(socket.timeout): receiver.recv(2048)


def test_udp_continuous_and_ring_updates_stop(destination, monkeypatch):
    async def exercise():
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(('127.0.0.1', 0)); receiver.setblocking(False)
        monkeypatch.setattr(server, 'output_override', server.OutputConfig(host='127.0.0.1', port=receiver.getsockname()[1], protocol='udp'))
        loop = asyncio.get_running_loop()
        simulator = server.Simulator()
        simulator.config = server.Config(gps=True, ais=False, gga=False, interval=.2)
        simulator.task = asyncio.create_task(simulator.run())
        motion = server.RingMotion()
        try:
            first = await asyncio.wait_for(loop.sock_recv(receiver,2048),2)
            second = await asyncio.wait_for(loop.sock_recv(receiver,2048),2)
            assert first.startswith(b'$GNRMC') and second.startswith(b'$GNRMC')
            await simulator.stop()
            motion.configure(server.AisSuiteRequest(scenario_ids=['type-1'], center=server.Waypoint(lat=35,lon=139)))
            motion.active=True; motion.task=asyncio.create_task(motion.run())
            first = await asyncio.wait_for(loop.sock_recv(receiver,2048),3)
            second = await asyncio.wait_for(loop.sock_recv(receiver,2048),3)
            assert first.startswith(b'!AIVDM') and first != second
            await motion.stop()
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(loop.sock_recv(receiver,2048),.3)
        finally:
            await simulator.stop(); await motion.stop(); receiver.close()
    asyncio.run(exercise())
