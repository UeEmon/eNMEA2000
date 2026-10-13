import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'configure_sdr_chain', Path(__file__).parents[1] / 'scripts' / 'configure-sdr-chain.py')
chain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)


def test_default_uses_modulator():
    assert chain.rtl_tcp_source('') == dict(host='host.docker.internal', port=1235, sample_rate=288000)


def test_real_rtl_tcp():
    assert chain.rtl_tcp_source('192.168.1.20:1234') == dict(
        host='192.168.1.20', port=1234, sample_rate=1536000)


@pytest.mark.parametrize('value', ['host', ':1234', 'host:', 'host:0', 'host:70000', 'host:12a'])
def test_invalid(value):
    with pytest.raises(ValueError):
        chain.rtl_tcp_source(value)


def test_destinations_keep_saved_and_add_extra():
    ipad = {'enabled': True, 'protocol': 'udp', 'host': '192.168.1.30', 'port': 10110}
    result = chain.destinations([dict(chain.MAIN, enabled=False), ipad],
                                'tcp://192.168.1.31:10111, udp://192.168.1.30:10110')
    assert result == [chain.MAIN, ipad,
                      {'enabled': True, 'protocol': 'tcp', 'host': '192.168.1.31', 'port': 10111}]


@pytest.mark.parametrize('value', ['192.168.1.30:10110', 'http://h:1', 'udp://h', 'udp://:1', 'tcp://h:99999'])
def test_destinations_reject(value):
    with pytest.raises(ValueError):
        chain.destinations([], value)


def test_destinations_limit():
    extra = ','.join(f'udp://10.0.0.{i}:10110' for i in range(16))
    with pytest.raises(ValueError):
        chain.destinations([], extra)
