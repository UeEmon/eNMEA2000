"""Deterministic AIS wire scenarios shared by the emulator and parser tests."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Scenario:
    id: str
    message_type: int
    label: str
    frames: tuple[str, ...]

    def public(self):
        return dict(id=self.id, message_type=self.message_type, label=self.label,
                    frames=list(self.frames), sentences=len(self.frames))


def _type(frame):
    payload = frame.split(',')[5]
    return ord(payload[0]) - 48 if payload[0] <= 'W' else ord(payload[0]) - 56


def _load():
    lines = (Path(__file__).parent / 'ais-all-types.log').read_text(encoding='ascii').splitlines()
    scenarios = []
    for index, line in enumerate(lines):
        if not line.startswith('!AI') or '*' not in line:
            raise ValueError(f'invalid AIS fixture line {index + 1}')
        message_type = _type(line)
        if index and line.split(',')[2] != '1':
            continue
        if message_type == 24 and len([s for s in scenarios if s.message_type == 24]) >= 2:
            continue  # Auxiliary vessel is named explicitly in the variant catalog.
        parts = int(line.split(',')[1])
        frames = tuple(lines[index:index + parts])
        if len(frames) != parts or [int(part.split(',')[2]) for part in frames] != list(range(1, parts + 1)):
            raise ValueError(f'incomplete AIS fixture at line {index + 1}')
        suffix = ''
        if message_type == 24:
            suffix = '-a' if len([s for s in scenarios if s.message_type == 24]) == 0 else '-b'
        scenarios.append(Scenario(f'type-{message_type}{suffix}', message_type,
                                  f'Type {message_type}' + (' Part A' if suffix == '-a' else ' Part B' if suffix else ''), frames))
    variants = {
        'type-24-aux': (24, 'Type 24 補助船舶', ('!AIVDO,1,1,,A,H>WikQl000000001EHijk0IgQV90,0*7E',)),
        'type-25-broadcast': (25, 'Type 25 放送・非構造化', ('!AIVDM,1,1,,A,I6Ki`kjbE@,4*79',)),
        'type-25-broadcast-structured': (25, 'Type 25 放送・構造化', ('!AIVDM,1,1,,A,I6Ki`klB=:aE,0*7D',)),
        'type-25-addressed': (25, 'Type 25 宛先指定・非構造化', ('!AIVDM,1,1,,A,I6Ki`kqVv6HTbUD,2*7A',)),
        'type-26-broadcast': (26, 'Type 26 放送・非構造化', ('!AIVDM,1,1,,A,J6Ki`kjbE@Rck@,4*60',)),
        'type-26-broadcast-structured': (26, 'Type 26 放送・構造化', ('!AIVDM,1,1,,A,J6Ki`klB=:aE2:g=,0*2C',)),
        'type-26-addressed': (26, 'Type 26 宛先指定・非構造化', ('!AIVDM,1,1,,A,J6Ki`kqVv6HTbUD8btl,2*3B',)),
        'type-26-multipart': (26, 'Type 26 3分割', (
            '!AIVDM,3,1,7,A,J6Ki`kuVv6HT4SBbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaE,0*6D',
            '!AIVDM,3,2,7,A,bUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFb,0*3B',
            '!AIVDM,3,3,7,A,EJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaEbUFbEJaE2:g=,0*50')),
        'type-17-negative': (17, 'Type 17 負の座標', ('!AIVDM,1,1,,A,A6Ki`kjp>CChh0,4*68',)),
        'type-17-unavailable': (17, 'Type 17 位置利用不可', ('!AIVDM,1,1,,A,A6Ki`kib3Qba00,4*16',)),
        'type-22-region': (22, 'Type 22 海域指定', ('!AIVDO,1,1,,A,F6Ki`kh00005hLQJ?;NS2gj00000,0*09',)),
        'type-23-region': (23, 'Type 23 海域指定', ('!AIVDO,1,1,,A,G6Ki`kjp>@e7UgAQGq000000000,2*6C',)),
    }
    scenarios.extend(Scenario(id, kind, label, frames) for id, (kind, label, frames) in variants.items())
    if set(range(29)) != {scenario.message_type for scenario in scenarios} or len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError('AIS type coverage is incomplete')
    return tuple(scenarios)


SCENARIOS = _load()
BY_ID = {scenario.id: scenario for scenario in SCENARIOS}
