"""Bulk scalar telemetry and acquisition-clock reconstruction."""
from datetime import datetime, timedelta, timezone
import struct
from typing import Optional

from pipeline import FIELDS, decode_line, validate_row

CONTROL = 'e8310003-65d2-4b11-91e0-87f64f931c82'
HEADER = struct.Struct('<BBH')
RECORD = struct.Struct('<III13fB')
FLOAT_FIELDS = [name for name in FIELDS if name not in
                ['seq', 'device_ms', 'late_samples', 'ready', 'paper_candidate', 'candidate']]


def decode_bulk(data: bytes) -> list[dict]:
    if len(data) < HEADER.size:
        raise ValueError('Truncated bulk header')
    kind, version, count = HEADER.unpack_from(data)
    if kind != 4 or version != 1 or not 1 <= count <= 3 or len(data) != HEADER.size + count * RECORD.size:
        raise ValueError('Unsupported or truncated bulk packet')
    rows = []
    for i in range(count):
        seq, device_ms, late, *values, flags = RECORD.unpack_from(data, HEADER.size + i * RECORD.size)
        if flags & ~7:
            raise ValueError('Unknown sample flags')
        row = dict(zip(FLOAT_FIELDS, values))
        row.update(seq=seq, device_ms=device_ms, late_samples=late,
                   ready=bool(flags & 1), paper_candidate=bool(flags & 2), candidate=bool(flags & 4))
        rows.append(validate_row(row))
    return rows


class DeviceClock:
    def __init__(self, device_ms: int, host_ms: int) -> None:
        if not 0 <= device_ms <= 0xFFFFFFFF or host_ms < 0:
            raise ValueError('Invalid clock anchor')
        self.device_ms = device_ms
        self.host = datetime.fromtimestamp(host_ms / 1000, timezone.utc)

    def timestamp(self, device_ms: int) -> datetime:
        delta = ((device_ms - self.device_ms + 0x80000000) & 0xFFFFFFFF) - 0x80000000
        return self.host + timedelta(milliseconds=delta)


class BulkSession:
    def __init__(self) -> None:
        self.clock: Optional[DeviceClock] = None
        self.model_id = 'unknown'
        self.text = ''
        self.pending: list[tuple[dict, datetime]] = []
        self.last_seq: Optional[int] = None
        self.complete = False

    def stamp(self, row: dict, arrival: datetime, legacy: bool = False) -> dict:
        previous = self.last_seq
        delta = (row['seq'] - previous) & 0xFFFFFFFF if previous is not None else 1
        if delta == 0 or delta >= 0x80000000:
            raise ValueError('Device sequence reversed or repeated; start a new recording after reboot')
        self.last_seq = row['seq']
        acquired = self.clock.timestamp(row['device_ms']) if not legacy and self.clock else arrival
        row.update(Timestamp=acquired.isoformat(), Arrival_Timestamp=arrival.isoformat(),
                   Clock_Source='arrival_legacy' if legacy else 'device_anchor',
                   model_id=self.model_id, seq_gap=delta - 1)
        return row

    def feed(self, data: bytes, arrival: datetime) -> list[dict]:
        if data and data[0] == 4:
            rows = decode_bulk(data)
            if self.clock is None:
                if len(self.pending) + len(rows) > 2048:
                    raise ValueError('Too many unsynchronized samples; clock handshake failed')
                self.pending.extend((row, arrival) for row in rows)
                return []
            return [self.stamp(row, arrival) for row in rows]
        self.text += data.decode('ascii', errors='strict')
        if len(self.text) > 4096:
            self.text = ''
            raise ValueError('Oversized text transport buffer')
        result = []
        while '\n' in self.text:
            line, self.text = self.text.split('\n', 1)
            if line.startswith('M,'):
                self.model_id = line[2:].strip()
            elif line.startswith('C,'):
                parts = line.strip().split(',')
                if len(parts) != 3:
                    raise ValueError('Malformed clock anchor')
                self.clock = DeviceClock(int(parts[1]), int(parts[2]))
                result.extend(self.stamp(row, arrived) for row, arrived in self.pending)
                self.pending.clear()
            elif line == 'D':
                self.complete = True
            elif line.startswith('ERROR,'):
                raise ValueError(f'Badge rejected configuration: {line}')
            elif line.startswith(('OK,', 'STATUS,')):
                continue
            else:
                result.append(self.stamp(decode_line(line), arrival, legacy=True))
        return result
