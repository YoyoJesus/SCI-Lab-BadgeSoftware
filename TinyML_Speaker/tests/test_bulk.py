from datetime import datetime, timezone
import struct

import pytest

from transport import decode_bulk, DeviceClock, BulkSession
from pipeline import FIELDS


def packet(seq=10, device_ms=1000):
    values = [12, .2, 1, 0, .5, 1, .8, 2, 30, 22, 45, 100, 0]
    return struct.pack('<BBH', 4, 1, 2) + b''.join(
        struct.pack('<III13fB', seq + i, device_ms + i * 5, 0, *values, 7) for i in range(2))


def test_bulk_preserves_every_sample_and_validates_packet():
    rows = decode_bulk(packet())
    assert len(rows) == 2
    assert rows[1]['device_ms'] - rows[0]['device_ms'] == 5
    assert rows[0]['candidate'] and rows[0]['paper_candidate']
    assert set(rows[0]) == set(FIELDS)
    for invalid in [packet()[:-1], bytes([4, 2]) + packet()[2:], packet() + b'x']:
        with pytest.raises(ValueError):
            decode_bulk(invalid)
    bad = bytearray(packet())
    struct.pack_into('<f', bad, 16, float('nan'))
    with pytest.raises(ValueError):
        decode_bulk(bad)


def test_device_clock_preserves_acquisition_spacing_across_wrap():
    clock = DeviceClock(0xFFFFFFFE, 1767225600000)
    first = clock.timestamp(0xFFFFFFFE)
    second = clock.timestamp(3)
    assert (second - first).total_seconds() == .005
    assert first == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_session_buffers_pre_sync_data_and_does_not_use_bulk_arrival_time():
    session = BulkSession()
    assert session.feed(packet(), datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)) == []
    rows = session.feed(b'C,1000,1767225600000\n', datetime.now(timezone.utc))
    assert len(rows) == 2
    assert rows[0]['Timestamp'].startswith('2026-01-01T00:00:00')
    assert rows[0]['Arrival_Timestamp'].startswith('2026-01-01T00:00:10')
    assert rows[1]['seq_gap'] == 0
    rows = session.feed(packet(20, 1050), datetime.now(timezone.utc))
    assert rows[0]['seq_gap'] == 8


def test_session_legacy_ascii_is_marked_as_arrival_time():
    session = BulkSession()
    line = b'S,1,100,12,0.2,0,0,0,0,-1,0,0,0,0,20,22,45,100,0,0\n'
    assert session.feed(line[:20], datetime.now(timezone.utc)) == []
    row = session.feed(line[20:], datetime.now(timezone.utc))[0]
    assert row['Clock_Source'] == 'arrival_legacy'


def test_bulk_timestamps_can_be_labeled_with_mixed_iso_precision():
    import pandas as pd
    from pipeline import label_frame
    session = BulkSession()
    session.feed(b'C,1000,1767225600000\n', datetime.now(timezone.utc))
    rows = session.feed(packet(), datetime.now(timezone.utc))
    for row in rows:
        row['Badge_Name'] = 'a'
    labeled = label_frame(pd.DataFrame(rows))
    assert len(labeled) == 2
    assert (labeled.Timestamp.iloc[1] - labeled.Timestamp.iloc[0]).total_seconds() == .005


def test_session_rejects_bad_flags_and_sequence_reversal():
    bad = bytearray(packet())
    bad[4 + 64] = 128
    with pytest.raises(ValueError):
        decode_bulk(bad)
    session = BulkSession()
    session.feed(b'C,1000,1767225600000\n', datetime.now(timezone.utc))
    session.feed(packet(), datetime.now(timezone.utc))
    with pytest.raises(ValueError, match='sequence'):
        session.feed(packet(), datetime.now(timezone.utc))


@pytest.mark.parametrize('cancel', [False, True])
def test_receiver_configures_rate_and_drains_final_bulk(tmp_path, monkeypatch, cancel):
    import argparse
    import asyncio
    from types import SimpleNamespace
    import bleak
    import pandas as pd
    import pipeline
    from transport import CONTROL
    commands = []
    ready = None

    class Scanner:
        @staticmethod
        async def discover(**kwargs):
            return [SimpleNamespace(address='synthetic-device', name='test')]

    class Client:
        def __init__(self, device):
            self.is_connected = False
            self.services = SimpleNamespace(get_characteristic=lambda uuid: True)
        async def connect(self):
            self.is_connected = True
        async def disconnect(self):
            self.is_connected = False
        async def start_notify(self, characteristic, callback):
            self.callback = callback
        async def write_gatt_char(self, characteristic, data, response):
            assert characteristic == CONTROL and response
            commands.append(data.decode())
            if data == b'STOP\n':
                self.callback(None, packet(seq=12, device_ms=1010))
                self.callback(None, b'D\n')
            elif data.startswith(b'CLOCK '):
                self.callback(None, b'M,synthetic-model\nC,1000,1767225600000\n')
                self.callback(None, packet())
                ready.set()
            else:
                self.callback(None, b'OK,configured\n')

    monkeypatch.setattr(bleak, 'BleakScanner', Scanner)
    monkeypatch.setattr(bleak, 'BleakClient', Client)
    args = argparse.Namespace(scan=False, address=None, output=tmp_path, recording_id='test',
                              rate=200, send_seconds=2, seconds=100 if cancel else .001, raw_only=cancel)
    async def run():
        nonlocal ready
        ready = asyncio.Event()
        task = asyncio.create_task(pipeline.receive(args))
        if cancel:
            await asyncio.wait_for(ready.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    asyncio.run(run())
    frame = pd.read_csv(next(tmp_path.glob('*_raw.csv')))
    assert len(frame) == 4
    assert list(frame.seq) == [10, 11, 12, 13]
    assert frame.seq_gap.sum() == 0
    assert set(frame.Clock_Source) == {'device_anchor'}
    assert commands[0] == 'RATE 200\n'
    assert commands[1] == 'SEND 2000\n'
    assert commands[2].startswith('CLOCK ')
    assert commands[-1] == 'STOP\n'
    if not cancel:
        assert len(pd.read_csv(next(tmp_path.glob('*_labeled.csv')))) == 4
