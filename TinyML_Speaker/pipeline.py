"""Paper-derived local detection, hybrid tree export, and PC collection."""
import argparse
import asyncio
import csv
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).resolve().parent
SERVICE = 'e8310001-65d2-4b11-91e0-87f64f931c82'
CHARACTERISTIC = 'e8310002-65d2-4b11-91e0-87f64f931c82'
FEATURES = ['norm_sound', 'norm_accel', 'presence_margin', 'Gyro_Magnitude',
            'Mag_Magnitude', 'Temperature', 'Humidity', 'Pressure', 'Proximity']
FIELDS = ['seq', 'device_ms', 'Sound_Level', 'Acceleration', 'norm_sound',
          'norm_accel', 'presence_margin', 'speech_score', 'model_score',
          'ready', 'paper_candidate', 'candidate', 'Gyro_Magnitude', 'Mag_Magnitude',
          'Temperature', 'Humidity', 'Pressure', 'Proximity', 'late_samples']


class Detector:
    """10 Hz causal reference of the firmware's paper-derived local rule."""
    def __init__(self) -> None:
        self.sound: deque[float] = deque(maxlen=600)
        self.accel: deque[float] = deque(maxlen=600)

    def update(self, sound: float, accel: float) -> Optional[dict[str, float]]:
        if not math.isfinite(sound) or not math.isfinite(accel) or min(sound, accel) < 0:
            self.sound.clear()
            self.accel.clear()
            raise ValueError('Sound and acceleration must be finite and nonnegative')
        self.sound.append(sound)
        self.accel.append(accel)
        if len(self.sound) < 10:
            return None
        s25, s45, s75 = np.quantile(self.sound, [.25, .45, .75])
        a25, a75 = np.quantile(self.accel, [.25, .75])
        spread = max(s75 - s25, 1)
        ns = (sound - s25) / spread
        na = (accel - a25) / max(a75 - a25, 1)
        margin = (np.mean(list(self.sound)[-10:]) - s45) / spread
        score = ns + 1.2 * np.clip(na, 0, 2.5)
        return {'norm_sound': float(ns), 'norm_accel': float(na),
                'presence_margin': float(margin), 'score': float(score),
                'candidate': bool(score >= .75 and (margin > 0 or score >= 3.5))}


def vote_winner(winners: list[Optional[str]]) -> Optional[str]:
    counts = Counter(w for w in winners if w is not None)
    if not counts:
        return None
    winner, count = counts.most_common(1)[0]
    return winner if count >= 3 else None


def decode_line(line: str) -> dict:
    parts = line.strip().split(',')
    if len(parts) != len(FIELDS) + 1 or parts[0] != 'S':
        raise ValueError('Invalid v1 sensor row')
    numbers = [float(p) for p in parts[1:]]
    return validate_row(dict(zip(FIELDS, numbers)))


def validate_row(row: dict) -> dict:
    if not all(math.isfinite(v) for v in row.values()):
        raise ValueError('Nonfinite sensor data')
    for field in ['seq', 'device_ms', 'late_samples']:
        if row[field] < 0 or int(row[field]) != row[field]:
            raise ValueError('Invalid counter')
        row[field] = int(row[field])
    if row['Sound_Level'] < 0 or row['Acceleration'] < 0:
        raise ValueError('Negative sensor reading')
    for field in ['ready', 'paper_candidate', 'candidate']:
        if row[field] not in (0, 1):
            raise ValueError('Invalid flag')
        row[field] = bool(row[field])
    if not (row['model_score'] == -1 or 0 <= row['model_score'] <= 1):
        raise ValueError('Invalid model score')
    if not row['ready'] and row['candidate']:
        raise ValueError('Candidate during warmup')
    return row


def group_split(y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    from sklearn.model_selection import GroupShuffleSplit
    if len(set(groups)) < 2 or set(y) != {0, 1}:
        raise ValueError('Need at least two recording groups and both labels')
    for train, test in GroupShuffleSplit(n_splits=100, test_size=.25, random_state=17).split(y, y, groups):
        if set(y[train]) == {0, 1} and set(y[test]) == {0, 1}:
            return train, test
    raise ValueError('Both labels must occur in training and held-out recordings')


def export_tree(model: DecisionTreeClassifier, path: Path, model_id: str) -> None:
    tree = model.tree_
    lines = ['#pragma once', f'#define SPEAKER_MODEL_ID "{model_id}"',
             'inline float wearerModel(const float *x) {']

    def emit(node: int, indent: str) -> None:
        if tree.children_left[node] == -1:
            values = tree.value[node][0]
            probability = float(values[1] / values.sum())
            lines.append(f'{indent}return {probability:.9f}f;')
            return
        lines.append(f'{indent}if (x[{tree.feature[node]}] <= {tree.threshold[node]:.9f}f) {{')
        emit(int(tree.children_left[node]), indent + '  ')
        lines.append(f'{indent}}} else {{')
        emit(int(tree.children_right[node]), indent + '  ')
        lines.append(f'{indent}}}')

    emit(0, '  ')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines + ['}', '']), encoding='utf-8')


def train(args: argparse.Namespace) -> None:
    import pandas as pd
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.tree import DecisionTreeClassifier
    if args.label == 'auto_activity_label' and not args.allow_pseudo_labels:
        raise ValueError('Auto labels require --allow-pseudo-labels; this measures agreement only')
    frames = []
    hashes = []
    for source in args.csv:
        frame = pd.read_csv(source)
        missing = set(FEATURES + [args.label, 'Recording_ID']) - set(frame.columns)
        if missing:
            raise ValueError(f'Missing columns: {sorted(missing)}. Use new firmware recordings and labels.')
        hashes.append(hashlib.sha256(Path(source).read_bytes()).hexdigest())
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    known = data[args.label].isin(['active', 'not_active'])
    skipped = int((~known).sum())
    data = data[known].copy()
    if data['Recording_ID'].isna().any() or data['Recording_ID'].astype(str).str.strip().eq('').any():
        raise ValueError('Recording_ID cannot be blank')
    if 'ready' in data:
        data = data[data['ready'].isin([1, True])]
    x = data[FEATURES].to_numpy(dtype=np.float32)
    if not np.isfinite(x).all():
        raise ValueError('Missing/nonfinite features; do not impute unavailable sensors silently')
    if (data[['Gyro_Magnitude', 'Mag_Magnitude', 'Humidity', 'Pressure', 'Proximity']] < 0).any().any():
        raise ValueError('Unavailable sensor features (-1); collect readings from functioning sensors')
    y = (data[args.label] == 'active').to_numpy(dtype=int)
    groups = data['Recording_ID'].astype(str).to_numpy()
    fit, test = group_split(y, groups)
    model = DecisionTreeClassifier(max_depth=4, min_samples_leaf=10, class_weight='balanced', random_state=17)
    model.fit(x[fit], y[fit])
    prediction = (model.predict_proba(x[test])[:, 1] >= .6).astype(int)
    sound_only_model = DecisionTreeClassifier(max_depth=4, min_samples_leaf=10, class_weight='balanced', random_state=17)
    sound_only_model.fit(x[fit, :3], y[fit])
    local_prediction = (sound_only_model.predict_proba(x[test, :3])[:, 1] >= .6).astype(int)
    paper_scores = x[test, 0] + 1.2 * np.clip(x[test, 1], 0, 2.5)
    paper_prediction = ((paper_scores >= .75) & ((x[test, 2] > 0) | (paper_scores >= 3.5))).astype(int)
    identity = hashlib.sha256((''.join(hashes) + args.label + json.dumps(FEATURES)
                               + model.tree_.threshold.tobytes().hex()
                               + model.tree_.value.tobytes().hex()).encode()).hexdigest()[:16]
    report = {'model_id': identity, 'features': FEATURES, 'source_sha256': hashes,
              'label': args.label, 'pseudo_labels': args.label == 'auto_activity_label',
              'unknown_rows_skipped': skipped, 'train_rows': len(fit), 'test_rows': len(test),
              'train_group_count': len(set(groups[fit])), 'test_group_count': len(set(groups[test])),
              'confusion_matrix': confusion_matrix(y[test], prediction).tolist(),
              'classification_report': classification_report(y[test], prediction, output_dict=True, zero_division=0),
              'decision_threshold': .6,
              'paper_rule_report': classification_report(y[test], paper_prediction, output_dict=True, zero_division=0),
              'paper_features_ml_report': classification_report(y[test], local_prediction, output_dict=True, zero_division=0),
              'note': 'Recording-held-out evaluation; participant independence is not established. Exported model uses training groups only.'}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    export_tree(model, ROOT / 'firmware/SpeakerBadge/model.h', identity)
    (output / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    print('Exported model.h. Rebuild and upload firmware to activate hybrid detection.')


def label_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the paper's winner and centered vote to a complete table."""
    import pandas as pd
    frame = frame.copy()
    frame['Timestamp'] = pd.to_datetime(frame['Timestamp'], utc=True, format='ISO8601')
    frame['time_bin'] = frame['Timestamp'].dt.floor('500ms')
    eligible = frame[frame['candidate'].isin([1, True])]
    winners = {}
    for tick, group in eligible.groupby('time_bin', sort=True):
        winners[tick] = group.loc[group['speech_score'].idxmax(), 'Badge_Name']
    bins = sorted(frame['time_bin'].unique())
    smoothed = {tick: vote_winner([winners.get(t) for t in bins[max(0, i - 2):i + 3]])
                for i, tick in enumerate(bins)}
    frame['auto_speaker'] = frame['time_bin'].map(smoothed).fillna('no_speaker')
    frame['auto_activity_label'] = np.where(frame['Badge_Name'] == frame['auto_speaker'], 'active', 'not_active')
    return frame


def replay(args: argparse.Namespace) -> None:
    import pandas as pd
    frame = pd.read_csv(args.csv)
    required = {'Timestamp', 'Badge_Name', 'Sound_Level', 'Acceleration'}
    if not required <= set(frame):
        raise ValueError(f'Required columns: {sorted(required)}')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if set(FIELDS) <= set(frame):
        label_frame(frame).to_csv(output, index=False, mode='x')
        print(f'Wrote {output} from stored badge candidates.')
        return
    frame['Timestamp'] = pd.to_datetime(frame['Timestamp'], utc=True, format='ISO8601')
    result = []
    for _, group in frame.groupby('Badge_Name'):
        detector = Detector()
        last = None
        for _, row in group.sort_values('Timestamp').iterrows():
            tick = row['Timestamp']
            if last is not None and (tick - last).total_seconds() < .1:
                continue
            if last is not None and (tick - last).total_seconds() > .25:
                detector = Detector()
            last = tick
            values = detector.update(float(row['Sound_Level']), float(row['Acceleration']))
            row = row.to_dict()
            row.update(values or {'norm_sound': 0, 'norm_accel': 0, 'presence_margin': 0, 'score': 0, 'candidate': False})
            row['speech_score'] = row.pop('score')
            row['ready'] = values is not None
            result.append(row)
    if not result:
        raise ValueError('No readings to replay')
    label_frame(pd.DataFrame(result)).to_csv(output, index=False, mode='x')
    print(f'Wrote {output}; causal adaptation, not an exact historical reproduction.')


async def receive(args: argparse.Namespace) -> None:
    from bleak import BleakClient, BleakScanner
    from transport import BulkSession, CONTROL
    import pandas as pd
    discovered = await BleakScanner.discover(timeout=8, service_uuids=[SERVICE])
    if args.scan:
        for device in discovered:
            print(device.address, device.name)
        return
    devices = [d for d in discovered if not args.address or d.address in args.address]
    if not devices:
        raise ValueError('No matching badges advertising the new service')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw_path = output / f'{stamp}_raw.csv'
    sessions: dict[str, BulkSession] = {}
    controlled: dict[str, BleakClient] = {}
    errors: list[str] = []
    clients = []
    sample_count = 0
    with raw_path.open('x', newline='', encoding='utf-8') as handle:
        columns = ['Timestamp', 'Arrival_Timestamp', 'Clock_Source', 'Badge_Name', 'Person_Name',
                   'Recording_ID', 'model_id', 'RSSI', 'seq_gap'] + FIELDS
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()

        def on_data(badge: str, data: bytearray) -> None:
            nonlocal sample_count
            if errors:
                return
            try:
                for row in sessions[badge].feed(bytes(data), datetime.now(timezone.utc)):
                    row.update(Badge_Name=badge, Person_Name='', Recording_ID=args.recording_id, RSSI='')
                    writer.writerow(row)
                    sample_count += 1
                handle.flush()
            except (ValueError, OSError) as error:
                errors.append(f'{badge}: {error}')

        try:
            for i, device in enumerate(devices):
                badge = f'badge_{i + 1:02d}'
                print(f'{badge}: connecting to {device.address}')
                client = BleakClient(device)
                await client.connect()
                clients.append(client)
                sessions[badge] = BulkSession()
                await client.start_notify(CHARACTERISTIC, lambda _, data, badge=badge: on_data(badge, data))
                if client.services.get_characteristic(CONTROL):
                    controlled[badge] = client
                    command = f'RATE {args.rate}\nSEND {round(args.send_seconds * 1000)}\nCLOCK {time.time_ns() // 1000000}\n'
                    await client.write_gatt_char(CONTROL, command.encode('ascii'), response=True)
                    deadline = time.monotonic() + 5
                    while sessions[badge].clock is None and time.monotonic() < deadline:
                        if errors:
                            raise ValueError(errors[0])
                        await asyncio.sleep(.02)
                    if sessions[badge].clock is None:
                        raise ConnectionError(f'{badge}: clock handshake timed out')
                else:
                    print(f'{badge}: legacy firmware; timestamps are BLE arrival times, rate settings unavailable')
            print(f'Recording scalar readings to {raw_path} for {args.seconds:g} seconds')
            started = time.monotonic()
            while time.monotonic() - started < args.seconds:
                if errors:
                    raise ValueError(errors[0])
                if any(not client.is_connected for client in clients):
                    raise ConnectionError('Badge disconnected; raw rows preserved, start a new recording')
                await asyncio.sleep(.2)
        finally:
            try:
                live = {badge: client for badge, client in controlled.items() if client.is_connected}
                if not errors:
                    for client in live.values():
                        await client.write_gatt_char(CONTROL, b'STOP\n', response=True)
                    deadline = time.monotonic() + 15
                    while any(not sessions[badge].complete for badge in live):
                        if errors:
                            raise ValueError(errors[0])
                        if time.monotonic() >= deadline or any(not client.is_connected for client in live.values()):
                            raise ConnectionError('Final bulk drain failed; received raw rows preserved')
                        await asyncio.sleep(.05)
            finally:
                await asyncio.gather(*(client.disconnect() for client in clients if client.is_connected), return_exceptions=True)
                if sample_count and not args.raw_only:
                    labeled = raw_path.with_name(f'{stamp}_labeled.csv')
                    label_frame(pd.read_csv(raw_path)).to_csv(labeled, index=False)
                    print(f'Labeled CSV: {labeled}')
                print(f'Saved {sample_count} samples')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    replay_parser = commands.add_parser('replay', help='Replay paper-derived causal rules on an existing CSV')
    replay_parser.add_argument('csv')
    replay_parser.add_argument('--output', default=str(ROOT / 'outputs/replay.csv'))
    train_parser = commands.add_parser('train', help='Train and export hybrid sensor tree')
    train_parser.add_argument('csv', nargs='+')
    train_parser.add_argument('--label', choices=['activity_label', 'auto_activity_label'], default='activity_label')
    train_parser.add_argument('--allow-pseudo-labels', action='store_true')
    train_parser.add_argument('--output', default=str(ROOT / 'outputs/model'))
    receiver = commands.add_parser('receive', help='Receive new badge firmware via BLE')
    receiver.add_argument('--scan', action='store_true')
    receiver.add_argument('--address', action='append')
    receiver.add_argument('--seconds', type=float, default=60)
    receiver.add_argument('--recording-id', default='session_01')
    receiver.add_argument('--output', default=str(ROOT / 'outputs'))
    receiver.add_argument('--rate', type=int, choices=[10, 50, 100, 200], default=200)
    receiver.add_argument('--send-seconds', type=float, default=5)
    receiver.add_argument('--raw-only', action='store_true', help='Skip final in-memory speaker labeling for long captures')
    observer = commands.add_parser('annotate', help='Open independent human observer panel')
    observer.add_argument('--badges', nargs='+', required=True)
    observer.add_argument('--recording-id', required=True)
    observer.add_argument('--output', default=None)
    merger = commands.add_parser('merge', help='Align observer intervals with badge CSV for training')
    merger.add_argument('csv')
    merger.add_argument('intervals')
    merger.add_argument('--output', required=True)
    merger.add_argument('--boundary-ms', type=float, default=200)
    merger.add_argument('--offset-ms', type=float, default=0)
    evaluation = commands.add_parser('evaluate', help='Compare predictions against human reference only')
    evaluation.add_argument('csv')
    evaluation.add_argument('--prediction', choices=['candidate', 'paper_candidate'], default='candidate')
    evaluation.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'receive' and (not math.isfinite(args.seconds) or args.seconds <= 0):
        parser.error('--seconds must be positive and finite')
    if args.command == 'receive' and (not math.isfinite(args.send_seconds) or not 0 <= args.send_seconds <= 600):
        parser.error('--send-seconds must be finite and between 0 and 600')
    try:
        if args.command == 'train':
            train(args)
        elif args.command == 'replay':
            replay(args)
        elif args.command == 'annotate':
            from observer import launch
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            launch(Path(args.output) if args.output else ROOT / f'outputs/{stamp}_reference.csv', args.recording_id, args.badges)
        elif args.command == 'merge':
            from ground_truth import merge_annotations
            merged = merge_annotations(pd.read_csv(args.csv), pd.read_csv(args.intervals), args.boundary_ms, args.offset_ms)
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            merged.to_csv(target, mode='x', index=False)
            print(f'Wrote {target}: {merged.activity_label.value_counts().to_dict()}')
        elif args.command == 'evaluate':
            from ground_truth import evaluate_reference
            report = evaluate_reference(pd.read_csv(args.csv), args.prediction)
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('x', encoding='utf-8') as handle:
                json.dump(report, handle, indent=2)
            print(f'Wrote reference evaluation to {target}')
        else:
            asyncio.run(receive(args))
    except (ValueError, OSError, ConnectionError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
