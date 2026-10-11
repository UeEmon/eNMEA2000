"""Small internal HTTP services. Only the authenticated router is exposed via nginx."""
import hmac
import json
import os
import signal
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from core import Router, validate
from engine import Engine

ROLE = os.environ.get('SDR_ROLE', 'router')
TOKEN = os.environ.get('SDR_TOKEN', '')
router = None
engine = None
control_lock = threading.RLock()


def agent(path, data=None):
    request = urllib.request.Request('http://ais-receiver:8001' + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, value, content_type='application/json'):
        body = json.dumps(value, ensure_ascii=False).encode() if content_type == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, post):
        path = self.path.split('?')[0]
        if path == '/health' and not post:
            return self.reply(200, {'ok': True})
        if ROLE == 'router' and (not TOKEN or not hmac.compare_digest(self.headers.get('X-SDR-Token', ''), TOKEN)):
            return self.reply(401, {'error': '管理トークンが一致しません'})
        try:
            data = None
            if post:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 32768:
                    return self.reply(413, {'error': 'Request body size'})
                data = json.loads(self.rfile.read(length))
            if ROLE == 'receiver':
                if path == '/status' and not post:
                    return self.reply(200, engine.status())
                if path == '/files' and not post:
                    return self.reply(200, [p.name for p in Path('/iq').iterdir() if p.is_file() and not p.is_symlink()])
                if path == '/start' and post:
                    engine.start(validate(data))
                    return self.reply(200, engine.status())
                if path == '/stop' and post:
                    engine.stop()
                    return self.reply(200, engine.status())
            else:
                if path == '/api/status' and not post:
                    status = router.status()
                    try:
                        status['receiver'] = agent('/status')
                    except (OSError, ValueError):
                        status['receiver'] = {'state': 'unreachable'}
                    return self.reply(200, status)
                if path == '/api/config' and not post:
                    return self.reply(200, router.config)
                if path == '/api/files' and not post:
                    return self.reply(200, agent('/files'))
                if path == '/api/logs' and not post:
                    return self.reply(200, [p.name for p in sorted(router.directory.glob('received.nmea*'))])
                if path.startswith('/api/logs/') and not post:
                    name = path.removeprefix('/api/logs/')
                    if name not in ('received.nmea', 'received.nmea.1', 'received.nmea.2', 'received.nmea.3'):
                        return self.reply(404, {'error': 'Not found'})
                    with router.lock:
                        router.handler.flush()
                        content = (router.directory / name).read_bytes()
                    return self.reply(200, content, 'text/plain; charset=utf-8')
                with control_lock:
                    if path == '/api/config' and post:
                        config = validate(data)
                        agent('/stop', {})
                        router.configure(config)
                        return self.reply(200, config)
                    if path in ('/api/start', '/api/reconnect') and post:
                        return self.reply(200, agent('/start', router.config))
                    if path == '/api/stop' and post:
                        return self.reply(200, agent('/stop', {}))
            self.reply(404, {'error': 'Not found'})
        except urllib.error.HTTPError as exc:
            self.reply(502, {'error': exc.read(4096).decode(errors='replace')})
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})
        except FileNotFoundError:
            self.reply(404, {'error': 'File not found'})
        except (OSError, RuntimeError) as exc:
            self.reply(503, {'error': str(exc)})

    def setup(self):
        super().setup()
        self.connection.settimeout(20)


def main():
    global router, engine
    if ROLE == 'receiver':
        engine = Engine()
    else:
        if len(TOKEN) < 16:
            raise SystemExit('SDR_TOKEN requires at least 16 characters. Run setup.py.')
        router = Router(os.environ.get('SDR_DATA', '/data'))
        def receive():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind(('0.0.0.0', 10112))
                while True:
                    packet, _ = sock.recvfrom(65535)
                    router.ingest(packet)
        threading.Thread(target=receive, daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', 8001 if ROLE == 'receiver' else 8002), Handler)
    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        (engine or router).stop() if engine else router.close()


if __name__ == '__main__':
    main()
