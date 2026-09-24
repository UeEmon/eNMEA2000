"""Input-independent NMEA/AIS decoder. Each import owns its own assembler."""
import math
import re
import time
from datetime import datetime, timezone
from enum import Enum
import pynmea2
from pyais import decode as decode_ais

SENTENCE = re.compile(r'[!$][^\r\n!$]*')

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
        row.update(status='ok', decoded=data, mmsi=str(data.get('mmsi', '')))
        lat, lon = data.get('lat'), data.get('lon')
        if lat is not None and lon is not None: self._position(row, lat, lon)
