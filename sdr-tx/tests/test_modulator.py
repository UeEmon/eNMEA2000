import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from modulator import Assembler,crc16,waveform,cu8,hdlc_bits,render,RATE
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'emulator'))
from ais_suite import SCENARIOS
class Tests(unittest.TestCase):
    def test_crc(self):self.assertEqual(crc16(b'123456789'),0x906e)
    def test_scenarios_and_source_isolation(self):
        for s in SCENARIOS:
            a=Assembler()
            for f in s.frames:packet=a.feed(f)
            self.assertEqual(int(packet[0][:6],2),s.message_type)
        s=next(s for s in SCENARIOS if len(s.frames)>1);a,b=Assembler(),Assembler()
        self.assertIsNone(a.feed(s.frames[0]))
        with self.assertRaises(ValueError):b.feed(s.frames[-1])
        for f in s.frames[1:]:result=a.feed(f)
        self.assertIsNotNone(result)
    def test_invalid_and_partial(self):
        with self.assertRaises(ValueError):Assembler().feed(SCENARIOS[0].frames[0][:-2]+'00')
        with self.assertRaises(ValueError):render(next(s.frames[0] for s in SCENARIOS if len(s.frames)>1))
    def test_hdlc(self):
        bits=[];ones=0
        for bit in hdlc_bits('01111111'*21)[32:-8]:
            if ones==5:self.assertEqual(bit,0);ones=0;continue
            bits.append(bit);ones=ones+1 if bit else 0
        data=bytes(sum(bits[i+j]<<j for j in range(8)) for i in range(0,len(bits),8))
        self.assertEqual(data[:-2],bytes([127])*21);self.assertEqual(int.from_bytes(data[-2:],'little'),crc16(data[:-2]))
    def test_spectrum_and_format(self):
        bits=Assembler().feed(next(s for s in SCENARIOS if s.message_type==1).frames[0])[0]
        for channel,center in [('A',-25000),('B',25000)]:
            iq=waveform(bits,channel);p=np.abs(np.fft.fft(iq))**2;f=np.fft.fftfreq(len(iq),1/RATE)
            self.assertLess(abs(np.sum(f*p)/p.sum()-center),3000);self.assertEqual(len(cu8(iq)),2*len(iq))
    def test_determinism(self):
        text='\n'.join(next(s for s in SCENARIOS if s.message_type==5).frames)
        a,n=render(text,{'noise':.01});b,_=render(text,{'noise':.01});self.assertEqual(a,b);self.assertEqual(n,1)
    def test_stop_clears_queue_and_incomplete_fragments(self):
        import importlib.util,tempfile
        spec=importlib.util.spec_from_file_location('sdr_tx_service',Path(__file__).resolve().parents[1]/'server.py')
        service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
        with tempfile.TemporaryDirectory() as td:
            service.DATA=Path(td);state=service.State();state.client='test';state.enabled=True
            a=Assembler();frames=next(s for s in SCENARIOS if s.message_type==5).frames
            state.ingest(frames[0],a);state.stop();state.enabled=True
            state.ingest(frames[1],a)
            self.assertEqual(state.queue.qsize(),0);self.assertEqual(state.counts['invalid'],1)
            for frame in frames:state.ingest(frame,a)
            self.assertEqual(state.queue.qsize(),1);state.stop();self.assertEqual(state.queue.qsize(),0)

if __name__=='__main__':unittest.main()
