#!/usr/bin/env python3
"""Validate unique-key alignment without converting unannotated time to silence."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

KEYS = ['Timestamp', 'Badge_Name']


def unique_labels(frame, column):
    """Collapse concordant labels; exclude conflicting keys rather than guess."""
    frame = frame[KEYS + [column]].copy()
    frame['Timestamp'] = pd.to_datetime(frame.Timestamp)
    frame[column] = frame[column].fillna('unknown').astype(str).str.strip().str.lower()
    counts = frame.groupby(KEYS)[column].nunique(dropna=False)
    bad_keys = counts[counts > 1].index
    keep = ~pd.MultiIndex.from_frame(frame[KEYS]).isin(bad_keys)
    result = frame.loc[keep].drop_duplicates(KEYS)
    return result, {'input_rows': len(frame), 'unique_keys': len(counts),
                    'duplicate_rows_beyond_first': len(frame) - len(counts),
                    'conflicting_keys_excluded': len(bad_keys)}


def assess(manual, auto):
    manual, manual_audit = unique_labels(manual, 'activity_label')
    auto, auto_audit = unique_labels(auto, 'auto_activity_label')
    joined = manual.merge(auto, on=KEYS, how='outer', validate='one_to_one', indicator=True)
    matched = joined[joined['_merge'] == 'both'].copy()
    explicit = matched[matched.activity_label.isin(['active', 'not_active'])]
    positive = explicit[explicit.activity_label == 'active']
    negative = explicit[explicit.activity_label == 'not_active']
    valid_auto = positive[positive.auto_activity_label.isin(['active', 'not_active'])]
    detected = int((valid_auto.auto_activity_label == 'active').sum())
    # Never derive negative-class statistics when no verified negatives exist.
    return {'manual': manual_audit, 'auto': auto_audit,
            'alignment': {str(k): int(v) for k, v in joined['_merge'].value_counts().items()},
            'matched_unique_keys': len(matched), 'explicitly_annotated_keys': len(explicit),
            'unannotated_keys': int((~matched.activity_label.isin(['active', 'not_active'])).sum()),
            'annotation_coverage_fraction': len(explicit) / len(matched) if len(matched) else None,
            'annotated_active_keys': len(positive), 'annotated_inactive_keys': len(negative),
            'active_keys_with_valid_auto_label': len(valid_auto), 'active_keys_detected': detected,
            'recall_on_annotated_active_keys': detected / len(valid_auto) if len(valid_auto) else None,
            'specificity': None, 'precision': None, 'overall_binary_accuracy': None,
            'qualification': 'Unknown means never annotated (author confirmation). Only conditional recall on annotated active keys is estimable here; annotations may not cover all active periods. Precision, specificity, and overall accuracy are unavailable without verified negatives and adequate coverage. This is a new unique-key analysis, not a replacement of historical duplicate-weighted counts.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('annotation_validation.json'))
    args = parser.parse_args()
    paths = ['currentdata/session_20260225_103434/processed_badge_data_20260225_103434.csv', 'currentdata/auto_label/hacksu_d3_2.3.csv']
    manual = pd.read_csv(args.data_root / paths[0], usecols=KEYS + ['activity_label'])
    auto = pd.read_csv(args.data_root / paths[1], usecols=KEYS + ['auto_activity_label'])
    result = assess(manual, auto)
    result['source_sha256'] = {p: hashlib.sha256((args.data_root / p).read_bytes()).hexdigest() for p in paths}
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['source_sha256', 'qualification']}, indent=2))
