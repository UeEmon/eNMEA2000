"""Input-independent NMEA/AIS decoder. Each import owns its own assembler."""
import math
import re
import time
from datetime import datetime, timezone
from enum import Enum
import pynmea2
from pyais import decode as decode_ais

SENTENCE = re.compile(r'[!$][^\r\n!$]*')

# ITU-R M.1371-6 defines Types 1-28. Type 0 occurs in legacy feeds as
# an alias of a Class-A position report.
AIS_TYPE_NAMES = {
    0: 'Legacy Class-A position report',
    1: 'Class-A position report: scheduled',
    2: 'Class-A position report: assigned',
    3: 'Class-A position report: response to interrogation',
    4: 'Base station report',
    5: 'Static and voyage related data',
    6: 'Binary addressed message',
    7: 'Binary acknowledgement',
    8: 'Binary broadcast message',
    9: 'Standard SAR aircraft position report',
    10: 'UTC/date inquiry',
    11: 'UTC/date response',
    12: 'Addressed safety-related message',
    13: 'Safety-related acknowledgement',
    14: 'Safety-related broadcast message',
    15: 'Interrogation',
    16: 'Assignment mode command',
    17: 'DGNSS binary broadcast message',
    18: 'Standard Class-B equipment position report',
    19: 'Extended Class-B equipment position report',
    20: 'Data link management message',
    21: 'Aid-to-navigation report',
    22: 'Channel management',
    23: 'Group assignment command',
    24: 'Static data report',
    25: 'Single-slot binary message',
    26: 'Multiple-slot binary message with communications state',
    27: 'Long-range AIS broadcast message',
    28: 'Single-slot Aid-to-Navigation report',
}
AIS_SUPPORTED_TYPES = frozenset(AIS_TYPE_NAMES)

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def checksum(body):
    result = 0
    for c in body:
        result ^= ord(c)
    return f'{result:02X}'

def clean(value):
    if isinstance(value, Enum): return value.value
    if isinstance(value, bytes): return value.hex()
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, (str, int, float, bool)) or value is None: return value
    return str(value)

def ais_bits(parts):
    """Read the wire payload, excluding NMEA six-bit fill padding."""
    chunks = []
    for index, part in enumerate(parts):
        fields = part.split('*')[0].split(',')
        fill = int(fields[6])
        if not 0 <= fill <= 5 or (index < len(parts)-1 and fill):
            raise ValueError('AISフィルビット不正')
        chunk = []
        for char in fields[5]:
            code = ord(char)
            if not (48 <= code <= 87 or 96 <= code <= 119):
                raise ValueError('AISペイロード文字不正')
            value = code-48 if code <= 87 else code-56
            chunk.append(f'{value:06b}')
        bits = ''.join(chunk)
        chunks.append(bits[:-fill] if fill else bits)
    return ''.join(chunks)

def bit_int(bits, start, width, signed=False):
    if start+width > len(bits): raise ValueError('AISペイロード長不足')
    value = int(bits[start:start+width], 2)
    return value-(1 << width) if signed and value & (1 << (width-1)) else value

def binary_hex(bits):
    if not bits: return ''
    padding = (-len(bits)) % 8
    return (int(bits, 2) << padding).to_bytes((len(bits)+7)//8, 'big').hex()

def normalize_ais(data, parts):
    """Correct pyais 3.2.3 coordinate units and variable binary layouts.

    ITU-R M.1371-6 tables 66, 73-74, 79 and 81 define these fields.
    Keep binary bit lengths because hex's final byte can contain padding.
    """
    msg_type = data['msg_type']
    if msg_type == 17:
        bits = ais_bits(parts)
        if len(bits) < 80: raise ValueError('AIS Type 17ペイロード長不足')
        data['lon'] = round(bit_int(bits, 40, 18, True)/600, 6)
        data['lat'] = round(bit_int(bits, 58, 17, True)/600, 6)
        data['data'] = binary_hex(bits[80:])
        data['data_bit_length'] = len(bits)-80
    elif msg_type == 23 or (msg_type == 22 and not data.get('addressed')):
        bits = ais_bits(parts)
        start = 40 if msg_type == 23 else 69
        for name, width in [('ne_lon',18),('ne_lat',17),('sw_lon',18),('sw_lat',17)]:
            data[name] = round(bit_int(bits, start, width, True)/600, 6)
            start += width
    elif msg_type in (25, 26):
        bits = ais_bits(parts)
        addressed = bool(bit_int(bits, 38, 1))
        structured = bool(bit_int(bits, 39, 1))
        data.update(addressed=addressed, structured=structured)
        start = 40
        if addressed:
            data['dest_mmsi'] = bit_int(bits, start, 30)
            data['destination_spare'] = bit_int(bits, start+30, 2)
            start += 32
        if structured:
            app_id = bit_int(bits, start, 16)
            data.update(app_id=app_id, dac=app_id >> 6, fid=app_id & 63)
            start += 16
        else:
            data.pop('app_id', None)
        end = len(bits)-(24 if msg_type == 26 else 0)
        if end < start or len(bits) > (1064 if msg_type == 26 else 168):
            raise ValueError(f'AIS Type {msg_type}ペイロード長不正')
        data['data'] = binary_hex(bits[start:end])
        data['data_bit_length'] = end-start
        if msg_type == 26:
            radio = bit_int(bits, len(bits)-20, 20)
            data.update(radio=radio, radio_spare=bit_int(bits, end, 4),
                        communication_state_selector=radio >> 19,
                        communication_state=radio & 0x7ffff)
    return data

class Decoder:
    def __init__(self, ttl=30, max_groups=4096):
        self.groups = {}
        self.ttl, self.max_groups = ttl, max_groups
        self.expired = 0

    def expire(self):
        now = time.monotonic()
        for key in list(self.groups):
            if now - self.groups[key]['at'] > self.ttl:
                del self.groups[key]
                self.expired += 1

    def parse(self, text, source, received_at=None):
        self.expire()
        row = dict(received_at=received_at or utcnow(), source=source, raw=text[:8192],
                   sentence_type='UNKNOWN', status='error', checksum_valid=None, decoded={},
                   latitude=None, longitude=None, mmsi=None, event_time=None)
        try:
            match = SENTENCE.search(text)
            if not match: raise ValueError('NMEAセンテンスがありません')
            sentence = match.group(0).strip()
            row['sentence_type'] = sentence[3:6] if len(sentence) > 5 else 'UNKNOWN'
            # Prefix timestamps and CSV quote wrappers are allowed; checksum ends sentence.
            checked = re.match(r'^([!$][^*]+)\*([0-9A-Fa-f]{2})(?:[\s,";].*)?$', sentence)
            if not checked: raise ValueError('チェックサム欠落／形式不正')
            body, expected = checked.groups()
            row['checksum_valid'] = checksum(body[1:]) == expected.upper()
            if not row['checksum_valid']: raise ValueError('チェックサム不一致')
            sentence = body + '*' + expected
            if body[3:6] in ('VDM', 'VDO'):
                self._ais(sentence, source, row)
            else:
                try:
                    msg = pynmea2.parse(sentence, check=True)
                except pynmea2.SentenceTypeError:
                    row.update(status='unsupported', decoded={'fields': body.split(',')[1:]})
                    return row
                data = {field[1]: clean(getattr(msg, field[1], None)) for field in msg.fields}
                data['talker'] = getattr(msg, 'talker', '')
                row.update(status='ok', decoded=data)
                kind = row['sentence_type']
                valid = not ((kind == 'RMC' and data.get('status') != 'A') or
                             (kind == 'GGA' and data.get('gps_qual') in (None, 0, '0')) or
                             (kind == 'GLL' and data.get('status') != 'A'))
                if valid and data.get('lat') and data.get('lon'):
                    self._position(row, float(msg.latitude), float(msg.longitude))
                if kind == 'RMC' and getattr(msg, 'datestamp', None) and getattr(msg, 'timestamp', None):
                    row['event_time'] = datetime.combine(msg.datestamp, msg.timestamp).replace(tzinfo=timezone.utc).isoformat()
        except Exception as exc:
            row.update(status='error', error=str(exc)[:240])
        return row

    @staticmethod
    def _position(row, lat, lon):
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            row.update(latitude=lat, longitude=lon)

    def _ais(self, sentence, source, row):
        fields = sentence.split('*')[0].split(',')
        if len(fields) != 7: raise ValueError('AISフィールド数不正')
        total, number, sequence, channel = int(fields[1]), int(fields[2]), fields[3], fields[4]
        if not 1 <= number <= total <= 9: raise ValueError('AIS分割番号不正')
        parts = [sentence]
        if total > 1:
            key = (source, fields[0], sequence, channel, total)
            if number == 1:
                if key not in self.groups and len(self.groups) >= self.max_groups:
                    raise ValueError('AIS再構成バッファ上限')
                self.groups[key] = {'at': time.monotonic(), 'parts': {1: sentence}}
            group = self.groups.get(key)
            if not group: raise ValueError('AIS先頭断片未受信')
            if not sequence and number > 1 and number - 1 not in group['parts']:
                del self.groups[key]
                raise ValueError('識別子なしAISの断片順序不正')
            if number in group['parts'] and group['parts'][number] != sentence:
                del self.groups[key]
                raise ValueError('AIS断片の競合')
            group['parts'][number] = sentence
            if len(group['parts']) < total:
                row.update(status='pending', decoded={'fragment': number, 'total': total})
                return
            parts = [group['parts'][i] for i in range(1, total + 1)]
            del self.groups[key]
        data = clean(decode_ais(*parts).asdict())
        msg_type = data.get('msg_type')
        if msg_type not in AIS_SUPPORTED_TYPES:
            raise ValueError(f'未対応のAISメッセージType: {msg_type}')
        data = normalize_ais(data, parts)
        mmsi = data.get('mmsi')
        row.update(status='ok', decoded=data,
                  ais_type=msg_type, ais_type_name=AIS_TYPE_NAMES[msg_type],
                  mmsi=str(mmsi) if mmsi is not None else None)
        lat, lon = data.get('lat'), data.get('lon')
        if lat is not None and lon is not None: self._position(row, lat, lon)
