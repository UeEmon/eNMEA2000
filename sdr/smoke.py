"""Docker integration: HTTP auth, engine file lifecycle, NMEA TCP/UDP fan-out."""
import json
import os
import sys
import socket
import subprocess
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN = next(l.split('=',1)[1] for l in (ROOT/'.env').read_text().splitlines() if l.startswith('SDR_TOKEN='))
PORT = os.environ.get('SDR_WEB_PORT') or next((l.split('=',1)[1] for l in (ROOT/'.env').read_text().splitlines() if l.startswith('SDR_WEB_PORT=')), '18082')
BASE = f'http://127.0.0.1:{PORT}'


def api(path, data=None):
    req=urllib.request.Request(BASE+'/api/'+path, data=None if data is None else json.dumps(data).encode(),headers={'X-SDR-Token':TOKEN,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)


def wait(fn):
    until=time.monotonic()+20
    while not fn():
        if time.monotonic()>until:raise AssertionError('Timed out')
        time.sleep(.1)


def main():
    try:
        urllib.request.urlopen(BASE+'/api/config')
        raise AssertionError('Unauthenticated API allowed')
    except urllib.error.HTTPError as e:assert e.code==401
    original=api('config')
    tcp=[];udp=[];sources=[];done=threading.Event()
    server=socket.socket();server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('0.0.0.0',10111));server.listen();server.settimeout(.2)
    us=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);us.bind(('0.0.0.0',10110));us.settimeout(.2)
    def read_tcp():
        while not done.is_set():
            try:conn,_=server.accept()
            except socket.timeout:continue
            conn.settimeout(.2);pending=b''
            with conn:
                while not done.is_set():
                    try:data=conn.recv(8192)
                    except socket.timeout:continue
                    if not data:break
                    pending+=data
                    while b'\r\n' in pending:
                        line,pending=pending.split(b'\r\n',1);tcp.append(line)
    def read_udp():
        while not done.is_set():
            try:data,addr=us.recvfrom(8192)
            except socket.timeout:continue
            udp.append(data.rstrip(b'\r\n'));sources.append(addr)
    threads=[threading.Thread(target=read_tcp),threading.Thread(target=read_udp)]
    for t in threads:t.start()
    try:
        config=json.loads(json.dumps(original));config['destinations']=[{'enabled':True,'protocol':p,'host':'host.docker.internal','port':port} for p,port in [('tcp',10111),('udp',10110)]]
        api('config',config);wait(lambda:all(d['connected'] for d in api('status')['destinations']))
        sys.path.insert(0,str(ROOT/'tests'))
        from fixtures import radio_frames
        lines=radio_frames()
        fixture=b'\r\n'.join(lines)+b'\r\n'
        # Internal ingest is intentionally not published to host/LAN.
        code='import socket,sys;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(sys.stdin.buffer.read(),("nmea-router",10112))'
        subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'exec','-T','ais-receiver','python','-c',code],input=fixture,check=True)
        wait(lambda:len(tcp)==len(lines) and len(udp)==len(lines))
        assert tcp==lines and udp==lines
        assert len(set(sources))==1
        assert api('status')['received']==len(lines)
        # A zero IQ fixture proves CLI/process compatibility, not RF decoding.
        (ROOT/'iq/silence.cu8').write_bytes(bytes([128])*3072000)
        config['input'].update(kind='file',file='silence.cu8',format='CU8',sample_rate=1536000)
        api('config',config);api('start',{})
        wait(lambda:api('status')['receiver']['state'] in ('finished','error'))
        status=api('status')['receiver'];assert status['state']=='finished',status
        api('stop',{});assert api('status')['receiver']['state']=='stopped'
        assert 'received.nmea' in api('logs')
        print(f'PASS: auth, TCP + UDP fan-out ({len(lines)} AIVDM frames), multipart socket identity, real AIS-catcher IQ-file lifecycle')
    finally:
        api('stop',{});api('config',original);done.set()
        for t in threads:t.join(2)
        server.close();us.close();(ROOT/'iq/silence.cu8').unlink(missing_ok=True)

if __name__=='__main__':main()
