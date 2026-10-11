"""NMEA forwarding primitives; no application/database dependency."""
import collections
import json
import logging
import logging.handlers
import queue
import re
import socket
import threading
import time
from pathlib import Path


def host(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:\-]{1,253}', value) or value.startswith('-'):
        raise ValueError('Invalid host')
    return value


def integer(value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'Expected integer {low}..{high}')
    return value


def validate(config):
    c = json.loads(json.dumps(config))
    inp = c['input']
    if inp['kind'] not in ('rtltcp', 'spyserver', 'usb', 'file'):
        raise ValueError('Invalid input kind')
    inp['host'] = host(inp.get('host', 'host.docker.internal'))
    inp['port'] = integer(inp.get('port', 1234), 1, 65535)
    inp['sample_rate'] = integer(inp.get('sample_rate', 1536000), 96000, 10000000)
    inp['ppm'] = integer(inp.get('ppm', 0), -150, 150)
    gain = inp.get('gain', 'auto')
    if gain != 'auto':
        if isinstance(gain, bool) or not isinstance(gain, (float, int)) or not 0 <= gain <= 50:
            raise ValueError('Gain must be auto or 0..50')
    inp['gain'] = gain
    serial = inp.get('serial', '')
    if not isinstance(serial, str) or not re.fullmatch(r'[A-Za-z0-9_-]{0,64}', serial):
        raise ValueError('Invalid USB serial')
    inp['serial'] = serial
    if inp.get('format', 'CU8') not in ('CU8', 'CS8', 'CS16', 'CF32'):
        raise ValueError('Invalid IQ format')
    inp['format'] = inp.get('format', 'CU8')
    name = inp.get('file', '')
    if not isinstance(name, str) or (name and (Path(name).name != name or name in ('.', '..') or len(name) > 200)):
        raise ValueError('Select a file directly under /iq')
    inp['file'] = name
    if not isinstance(c['destinations'], list) or len(c['destinations']) > 16:
        raise ValueError('Maximum 16 destinations')
    seen = set()
    for d in c['destinations']:
        d['host'] = host(d['host'])
        d['port'] = integer(d['port'], 1, 65535)
        if d['protocol'] not in ('tcp', 'udp') or not isinstance(d['enabled'], bool):
            raise ValueError('Invalid destination')
        key = (d['protocol'], d['host'], d['port'])
        if key in seen:
            raise ValueError('Duplicate destination')
        seen.add(key)
    c['log_mb'] = integer(c.get('log_mb', 100), 1, 1000)
    return c


DEFAULT = {'input': {'kind': 'rtltcp', 'host': 'host.docker.internal', 'port': 1234},
           'destinations': [{'host': 'host.docker.internal', 'port': 10111, 'protocol': 'tcp', 'enabled': True}], 'log_mb': 100}


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    tmp.replace(path)


def sentence(raw):
    """Accept only checked AIVDM, never turn over-air traffic into own position."""
    raw = raw.strip()
    if len(raw) > 1024:
        return None
    if not re.fullmatch(rb'!AIVDM,[1-9],[1-9],[0-9]?,[AB12]?,[0-9:;<=>?@A-W`a-w]+,[0-5]\*[0-9A-Fa-f]{2}', raw):
        return None
    body, checksum = raw[1:].split(b'*')
    check = 0
    for b in body:
        check ^= b
    fields = body.split(b',')
    if check != int(checksum, 16) or int(fields[2]) > int(fields[1]):
        return None
    return raw + b'\r\n'


class Destination:
    """Independent bounded queue. Anything queued during a disconnect is discarded."""
    def __init__(self, config):
        self.config = config
        self.queue = queue.Queue(512)
        self.stop = threading.Event()
        self.connected = False
        self.sent = self.dropped = self.failures = 0
        self.error = ''
        self.sock = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def offer(self, data):
        if not self.connected:
            self.dropped += 1
            return
        try:
            self.queue.put_nowait((time.monotonic(), data))
        except queue.Full:
            self.dropped += 1

    def clear(self):
        while True:
            try:
                self.queue.get_nowait()
                self.dropped += 1
            except queue.Empty:
                break

    def run(self):
        while not self.stop.is_set():
            try:
                d = self.config
                if d['protocol'] == 'tcp':
                    self.sock = socket.create_connection((d['host'], d['port']), timeout=2)
                else:
                    info = socket.getaddrinfo(d['host'], d['port'], type=socket.SOCK_DGRAM)[0]
                    self.sock = socket.socket(info[0], info[1], info[2])
                    self.sock.settimeout(2)
                    self.sock.connect(info[4])
                self.clear()
                self.connected = True
                self.error = ''
                while not self.stop.is_set():
                    try:
                        stamp, data = self.queue.get(timeout=.2)
                    except queue.Empty:
                        if d['protocol'] == 'tcp':
                            import select
                            if select.select([self.sock], [], [], 0)[0] and not self.sock.recv(1):
                                raise ConnectionError('Peer closed connection')
                        continue
                    if time.monotonic() - stamp > 2:
                        self.dropped += 1
                        continue
                    try:
                        if d['protocol'] == 'tcp':
                            self.sock.sendall(data)
                        else:
                            self.sock.send(data)
                        self.sent += 1
                    except OSError:
                        self.dropped += 1
                        raise
            except OSError as exc:
                self.failures += 1
                self.error = str(exc)
            finally:
                self.connected = False
                self.clear()
                if self.sock:
                    self.sock.close()
                    self.sock = None
            self.stop.wait(1)

    def close(self):
        self.stop.set()
        self.thread.join(4)

    def status(self):
        return {**self.config, 'connected': self.connected, 'sent': self.sent,
                'dropped': self.dropped, 'failures': self.failures, 'error': self.error}


class Router:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / 'config.json'
        self.config = validate(json.loads(path.read_text()) if path.exists() else DEFAULT)
        self.lock = threading.RLock()
        self.outputs = []
        self.received = self.invalid = 0
        self.channels = collections.Counter()
        self.last_received = None
        self.handler = None
        self.configure(self.config)

    def configure(self, config):
        config = validate(config)
        with self.lock:
            atomic_json(self.directory / 'config.json', config)
            for output in self.outputs:
                output.close()
            self.outputs = [Destination(d) for d in config['destinations'] if d['enabled']]
            self.config = config
            if self.handler:
                self.handler.close()
            # Four files total; total storage bounded by configured MB (plus one sentence).
            self.handler = logging.handlers.RotatingFileHandler(self.directory / 'received.nmea',
                          maxBytes=config['log_mb'] * 1024 * 1024 // 4, backupCount=3)
            self.handler.setFormatter(logging.Formatter('%(message)s'))
            self.handler.terminator = '\r\n'
            # When lowering the cap, retain the most recent files that fit it.
            limit = config['log_mb'] * 1024 * 1024
            files = [self.directory / ('received.nmea' + suffix) for suffix in ('.3', '.2', '.1', '')]
            total = sum(p.stat().st_size for p in files if p.exists())
            for p in files:
                if total <= limit:
                    break
                if p.exists():
                    total -= p.stat().st_size
                    if p.name == 'received.nmea':
                        self.handler.close()
                        p.write_bytes(b'')
                        self.handler.stream = self.handler._open()
                    else:
                        p.unlink()

    def ingest(self, packet):
        with self.lock:
            for raw in packet.splitlines():
                line = sentence(raw)
                if not line:
                    self.invalid += 1
                    continue
                self.received += 1
                self.last_received = time.time()
                self.channels[line.split(b',')[4].decode() or '?'] += 1
                self.handler.emit(logging.LogRecord('nmea', logging.INFO, '', 0, line.decode().strip(), (), None))
                for output in self.outputs:
                    output.offer(line)

    def status(self):
        with self.lock:
            return {'received': self.received, 'invalid': self.invalid, 'channels': dict(self.channels),
                    'last_received': self.last_received, 'destinations': [o.status() for o in self.outputs]}

    def close(self):
        with self.lock:
            for output in self.outputs:
                output.close()
            self.handler.close()
