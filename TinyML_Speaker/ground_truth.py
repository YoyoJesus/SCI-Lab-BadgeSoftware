"""Independent observer intervals and badge-data alignment."""
import csv
from datetime import datetime
import math
from pathlib import Path
import re
from typing import Optional

import numpy as np
import pandas as pd

LABELS = {'active', 'not_active', 'unknown'}
INTERVAL_FIELDS = ['Recording_ID', 'Badge_Name', 'Start', 'End', 'activity_label']


class IntervalRecorder:
    def __init__(self, path: Path, recording_id: str, badges: list[str], started: datetime) -> None:
        if not badges or len(set(badges)) != len(badges):
            raise ValueError('Provide unique badge IDs')
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value) for value in [recording_id] + badges):
            raise ValueError('Use anonymous IDs containing letters, digits, underscores, or hyphens')
        if started.tzinfo is None:
            raise ValueError('Use timezone-aware timestamps')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open('x', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.handle, fieldnames=INTERVAL_FIELDS)
        self.writer.writeheader()
        self.handle.flush()
        self.recording_id = recording_id
        self.states = dict.fromkeys(badges, 'unknown')
        self.last = started
        self.closed = False

    def change(self, states: dict[str, str], now: datetime) -> None:
        if self.closed:
            raise ValueError('Recording is closed')
        if now.tzinfo is None or now < self.last:
            raise ValueError('Annotation timestamps must increase and include a timezone')
        if set(states) != set(self.states) or not set(states.values()) <= LABELS:
            raise ValueError('Provide a valid label for each configured badge')
        if now > self.last:
            for badge, label in self.states.items():
                self.writer.writerow(dict(Recording_ID=self.recording_id, Badge_Name=badge,
                                          Start=self.last.isoformat(), End=now.isoformat(), activity_label=label))
            self.handle.flush()
        self.last = now
        self.states = dict(states)

    def close(self, now: datetime) -> None:
        if not self.closed:
            try:
                self.change(self.states, now)
            finally:
                self.closed = True
                self.handle.close()


def merge_annotations(samples: pd.DataFrame, intervals: pd.DataFrame,
                      boundary_ms: float = 0, offset_ms: float = 0, onset_ms: float = 0) -> pd.DataFrame:
    """Label samples from observer intervals.

    onset_ms marks the time just before each active interval as unknown, since observers
    tend to press the speaking key after speech has already started.
    """
    required = {'Recording_ID', 'Badge_Name', 'Timestamp'}
    if not required <= set(samples) or not set(INTERVAL_FIELDS) <= set(intervals):
        raise ValueError('Missing badge sample or interval columns')
    if not all(math.isfinite(v) and v >= 0 for v in [boundary_ms, onset_ms]) or not math.isfinite(offset_ms):
        raise ValueError('Boundary and onset margins must be nonnegative; offsets must be finite')
    result = samples.copy().reset_index(drop=True)
    intervals = intervals.copy()
    for table in [result, intervals]:
        if table[['Recording_ID', 'Badge_Name']].isna().any().any():
            raise ValueError('Missing recording or badge IDs')
        for name in ['Recording_ID', 'Badge_Name']:
            table[name] = table[name].astype(str)
    if not set(intervals.activity_label) <= LABELS:
        raise ValueError('Unknown interval label; use active, not_active, or unknown')
    def parse_utc(values: pd.Series) -> pd.Series:
        if not values.astype(str).str.contains(r'(?:Z|[+-]\d{2}:\d{2})$', case=False).all():
            raise ValueError('Reference alignment requires ISO timestamps with an explicit timezone')
        return pd.to_datetime(values, utc=True, errors='raise', format='ISO8601')

    result['Timestamp'] = parse_utc(result.Timestamp)
    if result.Timestamp.isna().any():
        raise ValueError('Missing sample timestamp')
    result['activity_label'] = 'unknown'
    if intervals.empty:
        return result
    if not set(result.Recording_ID) & set(intervals.Recording_ID):
        raise ValueError('No matching recording IDs; use the same recording ID in both tools')
    pairs = set(zip(result.Recording_ID, result.Badge_Name))
    if not pairs & set(zip(intervals.Recording_ID, intervals.Badge_Name)):
        raise ValueError('No matching badge IDs; check the receiver badge assignments')
    shift = pd.Timedelta(milliseconds=offset_ms)
    for name in ['Start', 'End']:
        intervals[name] = parse_utc(intervals[name]) + shift
    if intervals[['Start', 'End']].isna().any().any() or (intervals.End <= intervals.Start).any():
        raise ValueError('Intervals must have finite timestamps and positive duration')
    guard = pd.Timedelta(milliseconds=boundary_ms)
    for (recording, badge), group in intervals.groupby(['Recording_ID', 'Badge_Name']):
        group = group.sort_values('Start')
        combined: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []
        for row in group.itertuples(index=False):
            if combined and row.Start < combined[-1][1]:
                raise ValueError('Annotation intervals overlap for one badge')
            if combined and row.Start == combined[-1][1] and row.activity_label == combined[-1][2]:
                combined[-1] = (combined[-1][0], row.End, row.activity_label)
            else:
                combined.append((row.Start, row.End, row.activity_label))
        positions = result.index[(result.Recording_ID == recording) & (result.Badge_Name == badge)]
        times = result.loc[positions, 'Timestamp']
        starts = np.array([(start + guard).value for start, _, _ in combined], dtype=np.int64)
        ends = np.array([(end - guard).value for _, end, _ in combined], dtype=np.int64)
        indexes = np.searchsorted(starts, times.astype('int64').to_numpy(), side='right') - 1
        labels = np.array([label for _, _, label in combined], dtype=object)
        valid = indexes >= 0
        safe = np.maximum(indexes, 0)
        valid &= times.astype('int64').to_numpy() < ends[safe]
        result.loc[positions[valid], 'activity_label'] = labels[safe[valid]]
        if onset_ms:
            onset = pd.Timedelta(milliseconds=onset_ms)
            for start, _, label in combined:
                if label == 'active':
                    late = (times >= start - onset) & (times < start)
                    result.loc[positions[late.to_numpy()], 'activity_label'] = 'unknown'
    return result


def evaluate_reference(frame: pd.DataFrame, prediction: str = 'candidate') -> dict:
    if 'activity_label' not in frame or prediction not in frame:
        raise ValueError('Need activity_label and the selected prediction column')
    if not set(frame.activity_label.dropna()) <= LABELS:
        raise ValueError('Invalid reference label')
    known = frame.activity_label.isin(['active', 'not_active'])
    values = frame.loc[known, prediction]
    if not values.isin([True, False, 0, 1]).all():
        raise ValueError('Predictions must be binary flags on annotated rows')
    active = frame.loc[known, 'activity_label'].eq('active')
    predicted = values.astype(bool)
    tp = int((active & predicted).sum())
    tn = int((~active & ~predicted).sum())
    fp = int((~active & predicted).sum())
    fn = int((active & ~predicted).sum())

    def ratio(numerator: int, denominator: int) -> Optional[float]:
        return numerator / denominator if denominator else None

    return {'prediction': prediction, 'total_rows': len(frame), 'annotated_rows': int(known.sum()),
            'unknown_rows': int((~known).sum()), 'confusion_matrix': [[tn, fp], [fn, tp]],
            'matrix_order': ['not_active', 'active'], 'precision': ratio(tp, tp + fp),
            'recall': ratio(tp, tp + fn), 'specificity': ratio(tn, tn + fp),
            'f1': ratio(2 * tp, 2 * tp + fp + fn), 'accuracy': ratio(tp + tn, int(known.sum())),
            'note': 'Sample-level observer-reference agreement. Temporally related rows are not independent trials.'}
