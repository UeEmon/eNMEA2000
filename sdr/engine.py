"""Own the AIS-catcher subprocess without Docker socket access or shell execution."""
import collections
import subprocess
import threading
import time
from pathlib import Path
from core import validate


def command(config, iq_root='/iq'):
    inp = validate(config)['input']
    args = ['AIS-catcher', '-q', '-c', 'AB', '-s', str(inp['sample_rate']), '-p', str(inp['ppm']),
            '-u', 'nmea-router', '10112']
    kind = inp['kind']
    if kind == 'rtltcp':
        args += ['-t', inp['host'], str(inp['port']), '-gt', 'TUNER', str(inp['gain']), 'TIMEOUT', '10']
    elif kind == 'spyserver':
        args += ['-y', inp['host'], str(inp['port'])]
        if inp['gain'] != 'auto':
            args += ['-gy', 'GAIN', str(int(inp['gain']))]
    elif kind == 'usb':
        args += ['-d', inp['serial']] if inp['serial'] else ['-d:0']
        args += ['-gr', 'TUNER', str(inp['gain'])]
    else:
        root = Path(iq_root).resolve()
        path = (root / inp['file']).resolve()
        if path.parent != root or not path.is_file() or not inp['file']:
            raise ValueError('IQ file not found under /iq')
        args += ['-r', inp['format'], str(path)]
    return args


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.worker = None
        self.stop_event = threading.Event()
        self.state = 'stopped'
        self.exit_code = None
        self.restarts = 0
        self.messages = collections.deque(maxlen=100)

    def start(self, config):
        args = command(config)
        with self.lock:
            self.stop()
            self.stop_event.clear()
            self.state = 'starting'
            self.worker = threading.Thread(target=self.run, args=(args, config['input']['kind'] == 'file'), daemon=True)
            self.worker.start()

    def run(self, args, replay):
        while not self.stop_event.is_set():
            try:
                self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                self.state = 'running'
                # Bound each line as well as the number of retained diagnostic lines.
                while True:
                    line = self.process.stderr.readline(4096)
                    if not line:
                        break
                    self.messages.append(line.decode(errors='replace').rstrip())
                self.exit_code = self.process.wait()
                self.process.stderr.close()
                if replay:
                    self.state = 'finished' if self.exit_code == 0 else 'error'
                    break
            except OSError as exc:
                self.messages.append(str(exc))
            if self.stop_event.is_set():
                break
            self.state = 'retrying'
            self.restarts += 1
            if self.stop_event.wait(3):
                break

    def stop(self):
        with self.lock:
            self.stop_event.set()
            # A process may be in Popen when stop is requested.
            for _ in range(60):
                proc = self.process
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                if not self.worker or not self.worker.is_alive():
                    break
                self.worker.join(.1)
            if self.worker and self.worker.is_alive():
                raise RuntimeError('Receiver did not stop')
            self.state = 'stopped'

    def status(self):
        return {'state': self.state, 'exit_code': self.exit_code, 'restarts': self.restarts,
                'diagnostics': list(self.messages), 'signal_strength': None,
                'note': 'running is process status, not proof of RF reception'}
