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
