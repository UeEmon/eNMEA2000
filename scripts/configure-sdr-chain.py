"""Run through Compose exec stdin, using each service's own token and HTTP API."""
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request


def rtl_tcp_source(value):
    """AIS_RTL_TCP=host:port selects a real rtl_tcp receiver instead of the modulator."""
    if not value:
        return dict(host='host.docker.internal', port=1235, sample_rate=288000)
    host, sep, port = value.rpartition(':')
    if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError('AIS_RTL_TCP must be host:port')
    return dict(host=host, port=int(port), sample_rate=1536000)


def configure(stage):
    port = {'main': 80, 'emulator': 8090, 'receiver': 8002,
            'transmitter-config': 80, 'transmitter-start': 80}[stage]
    headers = {'Content-Type': 'application/json'}
    if stage == 'receiver':
        headers['X-SDR-Token'] = os.environ['SDR_TOKEN']
    elif stage.startswith('transmitter-'):
        headers['X-SDR-TX-Token'] = os.environ['SDR_TX_TOKEN']
    client = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def api(path, data=None):
        request = urllib.request.Request(
            f'http://127.0.0.1:{port}/api/{path}', headers=headers,
            data=None if data is None else json.dumps(data).encode())
        with client.open(request, timeout=20) as response:
            return json.load(response)

    if stage == 'main':
        api('login', {'token': os.environ['APP_TOKEN']})
        api('udp/start', {})
    elif stage == 'emulator':
        api('output', {'protocol': 'tcp', 'host': 'host.docker.internal', 'port': 10113})
    elif stage == 'transmitter-config':
        api('config', {'amplitude': 0.65, 'noise': 0, 'offset': 0, 'corrupt': False})
    elif stage == 'receiver':
        config = api('config')
        config['input'].update(kind='rtltcp', ppm=0, gain='auto', format='CU8',
                               **rtl_tcp_source(os.environ.get('AIS_RTL_TCP', '')))
        config['destinations'] = [{'enabled': True, 'protocol': 'tcp',
                                   'host': 'host.docker.internal', 'port': 10111}]
        api('config', config)
        api('start', {})
        deadline = time.monotonic() + 30
        while not api('status')['destinations'][0]['connected']:
            if time.monotonic() >= deadline:
                raise RuntimeError('SDR receiver could not connect to main TCP:10111')
            time.sleep(0.25)
    elif stage == 'transmitter-start':
        deadline = time.monotonic() + 30
        while api('status')['client'] is None:
            if time.monotonic() >= deadline:
                raise RuntimeError('SDR receiver could not connect to modulator RTL-TCP:1235')
            time.sleep(0.25)
        api('start', {})
    print(f'Configured: {stage}')


if __name__ == '__main__':
    try:
        configure(sys.argv[1])
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        # Do not print HTTP response bodies or environment tokens.
        print(f'SDR chain configuration failed ({sys.argv[1]}): {type(error).__name__}',
              file=sys.stderr)
        sys.exit(1)
