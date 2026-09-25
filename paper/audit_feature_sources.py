#!/usr/bin/env python3
"""Recompute saved features in memory; never overwrite local research outputs."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd


def compare(actual, saved):
    failures = []
    if actual.shape != saved.shape or list(actual.columns) != list(saved.columns):
        return [{'reason': 'schema_or_shape', 'computed_shape': list(actual.shape), 'saved_shape': list(saved.shape),
                 'computed_columns': list(actual.columns), 'saved_columns': list(saved.columns)}]
    for col in saved.columns:
        a, b = actual[col], saved[col]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            equal = np.isclose(a, b, atol=1e-10, rtol=1e-8, equal_nan=True)
        else:
            equal = (a.fillna('').astype(str).values == b.fillna('').astype(str).values)
        if not np.all(equal):
            # Do not emit person names or sensor-level values.
            failures.append({'column': col, 'mismatched_cells': int((~equal).sum())})
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('feature_source_audit.json'))
    args = parser.parse_args()
    root = args.data_root
    source = root / 'Feature Extraction/feature_extraction.py'
    spec = importlib.util.spec_from_file_location('extractor', source)
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    ids = pd.read_csv(root / 'Feature Extraction/weka_outputs/meeting_dataset.csv').meeting_id
    results, hashes = [], {}
    for record_id in ids:
        input_path = root / 'Data Cleanup and Normalization/processed_data/auto_label' / (record_id + '.csv')
        hashes[input_path.relative_to(root).as_posix()] = hashlib.sha256(input_path.read_bytes()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):
            df = extractor.load_and_validate(input_path)
            bins = extractor.aggregate_to_bins(df)
            turns = extractor.extract_turns(bins, min_bins=2)
            meeting = extractor.compute_meeting_features(df, bins, turns, record_id)
            participants = extractor.compute_participant_features(df, bins, turns, record_id, meeting)
            windows = extractor.compute_window_features(df, bins, turns, record_id, window_minutes=5.0)
        checks = {}
        for name, calculated in [('meeting_features', meeting), ('participant_features', participants), ('window_features', windows)]:
            saved_path = root / 'Feature Extraction/feature_extraction_outputs' / record_id / (name + '.csv')
            hashes[saved_path.relative_to(root).as_posix()] = hashlib.sha256(saved_path.read_bytes()).hexdigest()
            checks[name] = compare(calculated, pd.read_csv(saved_path))
        timeline = pd.DatetimeIndex(sorted(bins.time_bin.unique()))
        possible = int((timeline.max() - timeline.min()).total_seconds() / 0.5) + 1
        badge_rates = []
        for _, badge in df.groupby('Badge_Name'):
            timestamps = badge.Timestamp.drop_duplicates().sort_values()
            seconds = (timestamps.iloc[-1] - timestamps.iloc[0]).total_seconds()
            badge_rates.append((len(timestamps) - 1) / seconds)
        results.append({'record_id': record_id, 'input_rows': len(df),
                        'duplicate_badge_timestamp_keys': int(df.duplicated(['Badge_Name', 'Timestamp']).sum()),
                        'missing_global_half_second_bins': possible - len(timeline),
                        'unique_timestamp_rate_hz_min': min(badge_rates), 'unique_timestamp_rate_hz_max': max(badge_rates),
                        'table_mismatches': checks})
        print(record_id, 'mismatch columns:', sum(len(x) for x in checks.values()), flush=True)
    output = {'purpose': 'Recompute the existing extractor on saved auto-labeled inputs, using unchanged defaults. This does not validate automatic speaker labels or authenticate deployed firmware.',
              'parameters': {'min_turn_bins': 2, 'window_minutes': 5.0, 'absolute_tolerance': 1e-10, 'relative_tolerance': 1e-8},
              'extractor_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'records': results, 'source_sha256': hashes}
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
