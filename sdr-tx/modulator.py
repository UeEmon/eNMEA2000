"""AIS baseband test source: HDLC, CRC-16/X-25, NRZI and BT=0.4 GMSK."""
import math
import re
import time
import numpy as np
RATE=288000
RATES=(288000,384000,768000,1536000)

def crc16(data):
    crc=65535
    for byte in data:
        crc^=byte
        for _ in range(8):crc=(crc>>1)^(0x8408 if crc&1 else 0)
    return crc^65535

class Assembler:
    def __init__(self):self.parts={}
    def feed(self,raw):
        now=time.monotonic();self.parts={k:v for k,v in self.parts.items() if now-v[0]<10}
        if isinstance(raw,bytes):raw=raw.decode('ascii')
        raw=raw.strip()
        if len(raw)>1024 or not re.fullmatch(r'!AIVD[MO],[1-9],[1-9],[0-9]?,[AB12]?,[0-9:;<=>?@A-W`a-w]+,[0-5]\*[0-9A-Fa-f]{2}',raw):raise ValueError('AIS NMEA required')
        body,check=raw[1:].split('*');checksum=0
        for c in body:checksum^=ord(c)
        if checksum!=int(check,16):raise ValueError('NMEA checksum')
        talker,total,index,seq,channel,payload,fill=body.split(',');total,index,fill=int(total),int(index),int(fill)
        if index>total or (index<total and fill):raise ValueError('Invalid fragment')
        channel='B' if channel in ('B','2') else 'A';key=(talker,seq,channel)
        if total>1:
            if index==1:
                if len(self.parts)>=32:self.parts.pop(next(iter(self.parts)))
                self.parts[key]=(now,total,[payload]);return None
            old=self.parts.get(key)
            if not old or old[1]!=total or len(old[2])!=index-1:
                self.parts.pop(key,None);raise ValueError('Missing or out-of-order fragment')
            old[2].append(payload)
            if index<total:return None
            payload=''.join(old[2]);del self.parts[key]
        bits=''.join(f'{ord(c)-(48 if c<="W" else 56):06b}' for c in payload)
        if fill:bits=bits[:-fill]
        if not 38<=len(bits)<=1008:raise ValueError('Payload must be 38..1008 bits')
        return bits,channel

def hdlc_bits(payload,corrupt=False):
    padded=payload+'0'*((-len(payload))%8)
    data=bytes(int(padded[i:i+8],2) for i in range(0,len(padded),8))
    packet=data+(crc16(data)^int(corrupt)).to_bytes(2,'little')
    bits=[];ones=0
    for byte in packet:
        for shift in range(8):
            bit=(byte>>shift)&1;bits.append(bit);ones=ones+1 if bit else 0
            if ones==5:bits.append(0);ones=0
    flag=[0,1,1,1,1,1,1,0]
    return [0,1]*12+flag+bits+flag

def waveform(payload,channel='A',rate=RATE,amplitude=.65,offset=0,corrupt=False):
    if rate not in RATES:raise ValueError('Unsupported sample rate')
    sps=rate//9600;level=1;levels=[]
    for bit in hdlc_bits(payload,corrupt):
        if not bit:level=-level
        levels.append(level)
    t=np.arange(-2*sps,2*sps+1)/sps
    kernel=np.exp(-2*(math.pi*.4*t)**2/math.log(2));kernel/=kernel.sum()
    symbols=np.repeat([levels[0]]*4+levels+[levels[-1]]*4,sps)
    phase=np.cumsum(np.convolve(symbols,kernel,mode='same'))*(math.pi/2/sps)
    phase+=2*math.pi*((-25000 if channel=='A' else 25000)+offset)*np.arange(len(phase))/rate
    iq=amplitude*np.exp(1j*phase);ramp=np.linspace(0,1,2*sps)
    iq[:len(ramp)]*=ramp;iq[-len(ramp):]*=ramp[::-1]
    return np.concatenate((np.zeros(rate//100),iq,np.zeros(rate//100)))

def cu8(iq,noise=0,rng=None):
    if noise:
        rng=rng or np.random.default_rng();iq=iq+noise*(rng.normal(size=len(iq))+1j*rng.normal(size=len(iq)))
    out=np.empty(len(iq)*2);out[::2]=iq.real;out[1::2]=iq.imag
    return np.clip(np.rint(out*127+127.5),0,255).astype(np.uint8).tobytes()

def settings(value):
    result={}
    for k,d,lo,hi in [('amplitude',.65,.01,.9),('noise',0,0,.3),('offset',0,-3000,3000)]:
        n=value.get(k,d)
        if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not lo<=n<=hi:raise ValueError(f'{k}: {lo}..{hi}')
        result[k]=n
    result['corrupt']=value.get('corrupt',False)
    if not isinstance(result['corrupt'],bool):raise ValueError('corrupt must be boolean')
    return result

def render(text,config=None):
    if not isinstance(text,str):raise ValueError('NMEA text required')
    config=settings(config or {});assembler=Assembler();chunks=[];count=0;rng=np.random.default_rng(42)
    for line in text.splitlines():
        if not line.strip():continue
        packet=assembler.feed(line)
        if packet:
            count+=1
            if count>128:raise ValueError('Maximum 128 packets')
            chunks.append(cu8(waveform(*packet,amplitude=config['amplitude'],offset=config['offset'],corrupt=config['corrupt']),config['noise'],rng))
    if assembler.parts:raise ValueError('Incomplete multipart AIS')
    if not count:raise ValueError('No complete AIS packets')
    silence=cu8(np.zeros(RATE//10))
    return silence+b''.join(chunks)+silence,count
