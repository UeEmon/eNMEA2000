import copy
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import DEFAULT, Destination, Router, sentence, validate
from engine import command


def wait(predicate):
    limit = time.monotonic() + 6
    while not predicate():
        if time.monotonic() > limit: raise AssertionError('Timed out')
        time.sleep(.02)


def nmea(body):
    check = 0
    for b in body.encode(): check ^= b
    return f'!{body}*{check:02X}\r\n'.encode()

LINE = nmea('AIVDM,1,1,,A,13aG?P0000P00000000000000000,0')

class Tests(unittest.TestCase):
    def test_validation_and_own_position_isolation(self):
        self.assertEqual(sentence(LINE), LINE)
        self.assertIsNone(sentence(LINE.replace(b'*', b'*00')))
        self.assertIsNone(sentence(nmea('AIVDO,1,1,,A,13aG?P0000P00000000000000000,0')))
        self.assertIsNone(sentence(b'{"lat": 1}'))
        for mutate in [lambda c:c['input'].update(host=';id'),lambda c:c['input'].update(file='../secret'),lambda c:c['destinations'][0].update(port=0),lambda c:c.update(destinations=c['destinations']*2)]:
            c=copy.deepcopy(DEFAULT);mutate(c)
            with self.assertRaises(ValueError):validate(c)

    def test_command_inputs_and_path_isolation(self):
        c=validate(DEFAULT);self.assertIn('-t',command(c))
        for kind in ('rtltcp','usb','spyserver'):
            c['input']['kind']=kind;args=command(c);i=args.index('-X');self.assertEqual(args[i+1],'off')
        c=validate(DEFAULT)
        c['input']['kind']='usb';self.assertIn('-d:0',command(c))
        c['input']['kind']='spyserver';self.assertIn('-y',command(c))
        with tempfile.TemporaryDirectory() as td:
            c['input'].update(kind='file',file='test.iq')
            with self.assertRaises(ValueError):command(c,td)
            Path(td,'test.iq').write_bytes(b'\x80'*1024)
            self.assertEqual(command(c,td)[-2:],["CU8",str(Path(td,'test.iq'))])
            Path(td,'link.iq').symlink_to('/etc/passwd');c['input']['file']='link.iq'
            with self.assertRaises(ValueError):command(c,td)

    def test_udp_multipart_same_socket_and_persistence(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sink, tempfile.TemporaryDirectory() as td:
            sink.bind(('127.0.0.1',0));sink.settimeout(3);router=Router(td)
            try:
                c=validate(DEFAULT);c['destinations']=[{'protocol':'udp','host':'127.0.0.1','port':sink.getsockname()[1],'enabled':True}]
                router.configure(c);wait(lambda:router.outputs[0].connected)
                lines=[nmea('AIVDM,2,1,1,B,5'+'0'*59+',0'),nmea('AIVDM,2,2,1,B,'+'0'*11+',2')]
                router.ingest(b''.join(lines)+b'bad\n');received=[sink.recvfrom(4096) for _ in lines]
                self.assertEqual([r[0] for r in received],lines);self.assertEqual(received[0][1],received[1][1])
                self.assertEqual(router.status()['invalid'],1);self.assertEqual(Path(td,'received.nmea').read_bytes(),b''.join(lines))
            finally:router.close()
            restored=Router(td)
            try:self.assertEqual(restored.config,c)
            finally:restored.close()

    def test_tcp_disconnect_drops_offline_queue_and_recovers(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(5)
            dest=Destination({'protocol':'tcp','host':'127.0.0.1','port':listener.getsockname()[1],'enabled':True})
            try:
                conn,_=listener.accept();conn.settimeout(3);wait(lambda:dest.connected)
                dest.offer(LINE);self.assertEqual(conn.recv(4096),LINE);conn.close();wait(lambda:not dest.connected)
                dest.offer(LINE);self.assertGreaterEqual(dest.dropped,1)
                conn,_=listener.accept();conn.settimeout(3);wait(lambda:dest.connected)
                dest.offer(LINE);self.assertEqual(conn.recv(4096),LINE);conn.close()
            finally:dest.close()

    def test_log_rotation_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            router=Router(td)
            try:
                c=validate(DEFAULT);c['destinations']=[];c['log_mb']=1;router.configure(c);router.ingest(LINE*25000)
                self.assertLessEqual(sum(p.stat().st_size for p in Path(td).glob('received.nmea*')),1024*1024)
                self.assertEqual(len(list(Path(td).glob('received.nmea*'))),4)
            finally:router.close()


    def test_engine_retries_and_stop_kills_process(self):
        from engine import Engine
        from unittest.mock import patch
        import subprocess
        with patch('engine.command', return_value=[sys.executable,'-c','import sys;sys.stderr.write("input disconnected\\n");sys.exit(1)']):
            engine=Engine()
            try:
                engine.start(validate(DEFAULT))
                wait(lambda:engine.restarts>=1)
                self.assertEqual(engine.status()['state'],'retrying')
                self.assertIn('input disconnected',engine.status()['diagnostics'])
            finally:engine.stop()
            self.assertEqual(engine.state,'stopped')
        with patch('engine.command', return_value=[sys.executable,'-c','import time;time.sleep(60)']):
            engine=Engine()
            try:
                engine.start(validate(DEFAULT));wait(lambda:engine.state=='running')
                engine.stop();self.assertIsNotNone(engine.process.poll())
            finally:engine.stop()

    def test_all_types_and_variants_are_forwardable(self):
        from fixtures import radio_frames, SCENARIOS
        self.assertEqual({s.message_type for s in SCENARIOS},set(range(29)))
        frames=radio_frames()
        self.assertEqual(len(frames),45)
        for frame in frames:
            self.assertEqual(sentence(frame),frame+b'\r\n')

    def test_log_cap_reduction(self):
        with tempfile.TemporaryDirectory() as td:
            router=Router(td)
            try:
                c=validate(DEFAULT);c['destinations']=[];router.configure(c)
                router.ingest(LINE*25000)
                c['log_mb']=1;router.configure(c)
                self.assertLessEqual(sum(p.stat().st_size for p in Path(td).glob('received.nmea*')),1024*1024)
                router.ingest(LINE)
                self.assertTrue(Path(td,'received.nmea').read_bytes().endswith(LINE))
            finally:router.close()

if __name__=='__main__':unittest.main()
