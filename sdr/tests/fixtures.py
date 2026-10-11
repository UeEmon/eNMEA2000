"""Test-only radio-style envelopes for all emulator scenarios; never used by services."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'emulator'))
from ais_suite import SCENARIOS


def radio_frames():
    frames = []
    for scenario in SCENARIOS:
        for frame in scenario.frames:
            body = 'AIVDM' + frame[6:frame.index('*')]
            check = 0
            for char in body: check ^= ord(char)
            frames.append(f'!{body}*{check:02X}'.encode())
    return frames
