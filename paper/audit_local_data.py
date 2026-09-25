#!/usr/bin/env python3
"""Audit saved research outputs without modifying inputs or training classifiers.

Requires numpy and pandas. Outputs aggregates and source hashes, never names.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


def audit(root):
    sources = {}

    def read(relative):
        path = root / relative
        sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return pd.read_csv(path)

    base = 'Feature Extraction/'
    data = read(base + 'weka_outputs/meeting_dataset.csv')
    predictors = data.columns.drop(['meeting_id', 'effectiveness']).tolist()
    arff_path = root / base / 'weka_outputs/meeting_dataset.arff'
    sources[str(arff_path.relative_to(root)).replace('\\', '/')] = hashlib.sha256(arff_path.read_bytes()).hexdigest()
    arff = arff_path.read_text(encoding='utf-8')
    attributes = [line.split()[1] for line in arff.splitlines() if line.upper().startswith('@ATTRIBUTE')]
    import io
    ad = pd.read_csv(io.StringIO(arff.split('@DATA')[1]), header=None, names=attributes)
    assert attributes == predictors + ['effectiveness']
    assert data.effectiveness.tolist() == ad.effectiveness.tolist()
    assert np.allclose(data[predictors], ad[predictors], atol=0.50001e-6, rtol=0)
    spec = importlib.util.spec_from_file_location('exporter', root / base / 'weka_exporter.py')
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    records, name_sets, mismatches = [], [], []
    for _, row in data.iterrows():
        directory = base + 'feature_extraction_outputs/' + row.meeting_id
        meeting = read(directory + '/meeting_features.csv').iloc[0]
        participants = read(directory + '/participant_features.csv')
        read(directory + '/window_features.csv')
        reconstructed = exporter.flatten_meeting(root / directory)
        for col in predictors:
            if not np.isclose(row[col], reconstructed[col], atol=1e-12, rtol=1e-10, equal_nan=True):
                mismatches.append({'meeting_id': row.meeting_id, 'feature': col,
                                   'saved': float(row[col]), 'reconstructed': float(reconstructed[col])})
        names = {str(x).strip().casefold() for x in participants.person_name.dropna() if str(x).strip()}
        name_sets.append(names)
        records.append({'meeting_id': row.meeting_id, 'class': row.effectiveness,
                        'date': meeting.meeting_date, 'start': meeting.start_time, 'end': meeting.end_time,
                        'recorded_participants': int(meeting.n_participants),
                        'participant_rows': len(participants), 'duration_minutes': float(meeting.total_duration_sec / 60),
                        'context_from_id': 'SCI' if row.meeting_id.startswith('sci_') else 'HacKSU' if row.meeting_id.startswith('hacksu_') else 'CS1'})
    durations = [r['duration_minutes'] for r in records]
    contexts = {}
    for context in ['SCI', 'HacKSU', 'CS1']:
        selected = [r for r in records if r['context_from_id'] == context]
        contexts[context] = {'records': len(selected), 'classes': {c: sum(r['class'] == c for r in selected) for c in ['low', 'medium', 'high']}}
    comparison_dir = 'currentdata/label_comparison/comparison_20260304_103134/'
    compared = read(comparison_dir + 'label_comparison_20260304_103134.csv')
    manual = read('currentdata/session_20260225_103434/processed_badge_data_20260225_103434.csv')
    auto = read('currentdata/auto_label/hacksu_d3_2.3.csv')
    keys = ['Timestamp', 'Badge_Name']
    for frame in [manual, auto, compared]:
        frame['Timestamp'] = pd.to_datetime(frame.Timestamp)
    manual['manual_label'] = np.where(manual.activity_label.astype(str).str.strip().str.lower() == 'active', 'active', 'not_active')
    auto['auto_label'] = np.where(auto.auto_activity_label.astype(str).str.strip().str.lower() == 'active', 'active', 'not_active')
    joined = manual[keys + ['manual_label']].merge(auto[keys + ['auto_label']], on=keys)
    pd.testing.assert_series_equal(joined.value_counts().sort_index(), compared[joined.columns].value_counts().sort_index())
    compared['bin'] = compared.Timestamp.dt.floor('500ms')
    bins = pd.Index(sorted(compared.bin.unique()))
    states = {}
    for col in ['manual_label', 'auto_label']:
        counts = compared[compared[col] == 'active'].groupby(['bin', 'Badge_Name']).size().unstack(fill_value=0)
        states[col] = counts.idxmax(axis=1).reindex(bins, fill_value='no_speaker')
        if col == 'manual_label':
            overlap = int(((counts > 0).sum(axis=1) > 1).sum())
    classes = sorted(compared.Badge_Name.unique()) + ['no_speaker']
    matrix = pd.crosstab(states['manual_label'], states['auto_label']).reindex(index=classes, columns=classes, fill_value=0)
    original = json.loads((root / 'paper/supplementary_evaluations.json').read_text())['speaker_states']
    assert matrix.values.tolist() == original['matrix'], 'Saved speaker matrix does not match presentation'
    binary = compared.groupby(['manual_label', 'auto_label']).size()
    tp, fn, fp, tn = (int(binary[k]) for k in [('active', 'active'), ('active', 'not_active'), ('not_active', 'active'), ('not_active', 'not_active')])
    unique_manual, unique_auto = manual[keys].drop_duplicates(), auto[keys].drop_duplicates()
    key_overlap = unique_manual.merge(unique_auto, on=keys, how='outer', indicator=True)['_merge'].value_counts()
    return {
        'provenance': 'Audit of saved local outputs; no classifier training or sensor relabeling. Contexts inferred from record IDs; names used only for overlap counts, not verified identities.',
        'dataset': {'rows': len(data), 'predictors': len(predictors), 'classes': data.effectiveness.value_counts().to_dict(),
                    'missing_predictor_values': int(data[predictors].isna().sum().sum()),
                    'constant_predictors': [c for c in predictors if data[c].nunique(dropna=False) == 1],
                    'arff_matches_csv_at_six_decimal_precision': True, 'feature_reconstruction_mismatches': mismatches,
                    'contexts': contexts, 'duration_minutes': {'min': min(durations), 'median': float(np.median(durations)), 'max': max(durations), 'total': sum(durations)},
                    'distinct_recorded_name_strings': len(set().union(*name_sets)),
                    'record_pairs_sharing_a_name': sum(bool(a & b) for i, a in enumerate(name_sets) for b in name_sets[i+1:]),
                    'records': records},
        'speaker_comparison': {'saved_rows_reproduced': True, 'manual_rows': len(manual), 'auto_rows': len(auto), 'joined_rows': len(compared),
                    'duplicate_keys_beyond_first': {'manual': int(manual.duplicated(keys).sum()), 'auto': int(auto.duplicated(keys).sum()), 'joined': int(compared.duplicated(keys).sum())},
                    'unique_key_alignment': {str(k): int(v) for k, v in key_overlap.items()},
                    'manual_raw_labels': {str(k): int(v) for k,v in manual.activity_label.value_counts(dropna=False).items()},
                    'recorded_start': str(compared.Timestamp.min()), 'recorded_end': str(compared.Timestamp.max()),
                    'binary': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn, 'accuracy': (tp+tn)/len(compared), 'precision': tp/(tp+fp), 'recall': tp/(tp+fn), 'specificity': tn/(tn+fp)},
                    'classes': classes, 'matrix': matrix.values.tolist(), 'bins': len(bins), 'correct': int(np.trace(matrix)), 'manual_overlap_bins': overlap,
                    'matches_presentation_matrix': True},
        'source_sha256': sources,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('local_data_audit.json'))
    args = parser.parse_args()
    result = audit(args.data_root)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(f'Wrote {args.output}; {len(result["dataset"]["feature_reconstruction_mismatches"])} feature mismatches')
