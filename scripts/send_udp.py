"""Stable source socket: supports multipart AIS and optional timed replay."""
import argparse
from pathlib import Path
import socket
import time
p=argparse.ArgumentParser()
p.add_argument('--host',default='127.0.0.1')
p.add_argument('--port',type=int,default=10110)
p.add_argument('--file',default=str(Path(__file__).resolve().parents[1]/'samples/demo.log'))
p.add_argument('--interval',type=float,default=.2)
p.add_argument('--repeat',action='store_true')
a=p.parse_args()
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
    while True:
        with open(a.file,'rb') as f:
            for line in f:
                if line.strip(): s.sendto(line.strip()+b'\r\n',(a.host,a.port)); time.sleep(a.interval)
        if not a.repeat: break
