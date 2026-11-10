"""Load a finished recording for browsing in the viewer."""
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ground_truth import evaluate_reference, merge_annotations

LABEL_VALUES = {'active': 1.0, 'not_active': 0.0}


def plot_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Hide prediction values the badge did not actually produce."""
    frame = frame.copy()
    ready = frame['ready'].astype(bool)
    missing_model = ~frame['model_id'].isin(['paper-rule', 'unknown']) & (frame['model_score'] < 0)
    frame['candidate'] = frame['candidate'].astype(float).where(ready & ~missing_model)
    frame['model_score'] = frame['model_score'].where(frame['model_score'] >= 0)
    if 'activity_label' in frame:
        frame['observer_label'] = frame['activity_label'].map(LABEL_VALUES)
    return frame


class Recording:
    def __init__(self, raw_path: Path) -> None:
        self.path = raw_path
        frame = pd.read_csv(raw_path)
        if frame.empty or not {'Timestamp', 'Badge_Name', 'Recording_ID'} <= set(frame):
            raise ValueError(f'{raw_path.name} has no badge samples')
        self.note = 'No observer labels found next to this recording.'
        self.labeled = False
        reference = raw_path.parent / 'reference.csv'
        if reference.exists():
            try:
                labels = pd.read_csv(reference)
                if labels.empty:
                    self.note = 'reference.csv has no labeled intervals.'
                else:
                    frame = merge_annotations(frame, labels)
                    self.labeled = bool(frame['activity_label'].isin(LABEL_VALUES).any())
                    self.note = ('Observer labels from reference.csv (no boundary margin).' if self.labeled
                                 else 'reference.csv marks this whole run as unknown.')
            except ValueError as error:
                self.note = f'Observer labels not shown: {error}'
        frame['Timestamp'] = pd.to_datetime(frame['Timestamp'], utc=True, format='ISO8601')
        start = frame['Timestamp'].min()
        frame['t'] = (frame['Timestamp'] - start).dt.total_seconds()
        self.recording_ids = sorted(frame['Recording_ID'].astype(str).unique())
        self.duration = float(frame['t'].max())
        self.rows = len(frame)
        self.badges = {str(badge): group.sort_values('t').reset_index(drop=True)
                       for badge, group in frame.groupby('Badge_Name')}

    def window(self, badge: str, end: float, seconds: float, max_points: int = 2000) -> pd.DataFrame:
        frame = self.badges[badge]
        times = frame['t'].to_numpy()
        lo, hi = np.searchsorted(times, [end - seconds, end], side='left')
        part = frame.iloc[lo:hi + 1]
        stride = max(1, -(-len(part) // max_points))
        return plot_columns(part.iloc[::stride])

    def summary(self) -> list[dict]:
        result = []
        for badge, frame in self.badges.items():
            ready = frame['ready'].astype(bool)
            row = dict(badge=badge, samples=len(frame), detected=None, labeled=None, agreement=None)
            if ready.any():
                row['detected'] = float(frame.loc[ready, 'candidate'].astype(bool).mean())
            if self.labeled:
                known = frame['activity_label'].isin(LABEL_VALUES)
                if known.any():
                    row['labeled'] = float(frame.loc[known, 'activity_label'].eq('active').mean())
                    scored = frame[ready]
                    if scored['activity_label'].isin(LABEL_VALUES).any():
                        row['agreement'] = evaluate_reference(scored, 'candidate')['accuracy']
            result.append(row)
        return result


def percent(value: Optional[float]) -> str:
    return '' if value is None else f'{value:.0%}'
