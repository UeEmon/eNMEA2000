"""Independent AIS-catcher verifies payload bits after real I/Q demodulation."""
import collections
import os
import shlex
import subprocess
import sys
from pathlib import Path
from modulator import Assembler,render
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'emulator'))
from ais_suite import SCENARIOS
# Minimum lengths from the pinned v0.70 Message::validate implementation.
MINIMUM=(149,149,149,168,418,88,72,56,168,70,168,72,40,40,88,92,80,168,312,70,271,145,154,160,72,60,96,168)

def decode(iq):
    prefix=shlex.split(os.environ.get('AIS_TEST_COMMAND','docker compose --env-file sdr/.env -f sdr/compose.yaml exec -T ais-receiver AIS-catcher'))
    r=subprocess.run(prefix+['-r','CU8','.','-s','288000','-n'],input=iq,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    if r.returncode:raise AssertionError(r.stderr.decode(errors='replace'))
    assembler=Assembler();packets=[]
    for line in r.stdout.splitlines():
        if line.startswith(b'!AIVDM'):
            packet=assembler.feed(line)
            if packet:packets.append(packet)
    return packets

def main():
    expected=[];excluded=[]
    for s in SCENARIOS:
        a=Assembler()
        for frame in s.frames:packet=a.feed(frame)
        bits,channel=packet;bits+='0'*((-len(bits))%8)
        if s.message_type==0 or len(bits)<MINIMUM[s.message_type-1] or s.id in ('type-15','type-26-multipart'):excluded.append(s.id)
        else:expected.append((bits,channel))
    iq,count=render('\n'.join(f for s in SCENARIOS for f in s.frames));decoded=decode(iq)
    missing=collections.Counter(expected)-collections.Counter(decoded);extra=collections.Counter(decoded)-collections.Counter(expected)
    assert not missing and not extra,{'expected':len(expected),'received':len(decoded),'missing':[int(p[0][:6],2) for p in missing],'extra':[int(p[0][:6],2) for p in extra]}
    sample='\n'.join(next(s for s in SCENARIOS if s.message_type==5).frames)
    bad,_=render(sample,{'corrupt':True});assert not decode(bad),'Bad FCS accepted'
    impaired,_=render(sample,{'noise':.01,'offset':500});assert len(decode(impaired))==1,'Impaired signal failed'
    # Verify a near-limit type-26 payload separately from the 1008-bit boundary case.
    a=Assembler()
    for f in next(s for s in SCENARIOS if s.id=='type-26-multipart').frames:packet=a.feed(f)
    from modulator import cu8,waveform
    bits,channel=packet;shorter=bits[:-52]+bits[-20:]
    assert decode(cu8(waveform(shorter,channel)))==[(shorter,channel)]
    print(f'PASS: {count} scenarios modulated, {len(decoded)} bit-exact payloads after AIS-catcher; bad FCS rejected; noise/CFO decoded; expected rejects={excluded}')
if __name__=='__main__':main()
