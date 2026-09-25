#!/usr/bin/env python3
"""Reproduce poster summaries and run explicitly new, fixed-protocol baselines.

Inputs are read-only. WEKA's original six-decimal ARFF is used unchanged.
Outputs retain fold membership, probabilities, settings and runtime hashes.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

CLASSES = ['low', 'medium', 'high']
MODELS = {
    'ZeroR': ('weka.classifiers.rules.ZeroR', []),
    'Logistic': ('weka.classifiers.functions.Logistic', ['-R', '1.0', '-M', '-1']),
    'RandomForest': ('weka.classifiers.trees.RandomForest',
                     ['-P', '100', '-I', '100', '-num-slots', '1', '-K', '0', '-M', '1.0', '-V', '0.001', '-S', '1']),
    'MLP': ('weka.classifiers.functions.MultilayerPerceptron',
            ['-L', '0.3', '-M', '0.2', '-N', '500', '-V', '0', '-S', '0', '-E', '20', '-H', 'a']),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(predictions):
    matrix = np.zeros((3, 3), dtype=int)
    errors = []
    for row in predictions:
        a, b = CLASSES.index(row['actual']), CLASSES.index(row['predicted'])
        matrix[a, b] += 1
        target = np.eye(3)[a]
        errors.extend(target - np.array(row['probabilities']))
    n = int(matrix.sum())
    recall = np.divide(matrix.diagonal(), matrix.sum(axis=1), out=np.zeros(3), where=matrix.sum(axis=1) != 0)
    f1 = np.divide(2 * matrix.diagonal(), matrix.sum(axis=0) + matrix.sum(axis=1), out=np.zeros(3), where=(matrix.sum(axis=0) + matrix.sum(axis=1)) != 0)
    accuracy = float(np.trace(matrix) / n)
    chance = float(matrix.sum(axis=0) @ matrix.sum(axis=1) / n**2)
    return {'n': n, 'correct': int(np.trace(matrix)), 'matrix': matrix.tolist(),
            'accuracy': accuracy, 'kappa': (accuracy - chance) / (1 - chance),
            'macro_f1': float(f1.mean()), 'balanced_accuracy': float(recall.mean()),
            'mae': float(np.abs(errors).mean()), 'rmse': float(np.sqrt(np.square(errors).mean()))}


def name_components(names):
    unseen = set(names)
    components = []
    while unseen:
        first = min(unseen)
        unseen.remove(first)
        component, todo = {first}, [first]
        while todo:
            current = todo.pop()
            neighbors = {x for x in unseen if names[current] & names[x]}
            component.update(neighbors)
            unseen -= neighbors
            todo.extend(sorted(neighbors))
        components.append(sorted(component))
    return components


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--weka-home', type=Path, default=Path('C:/Program Files/Weka-3-8-6'))
    parser.add_argument('--java', type=Path)
    parser.add_argument('--historical-log', type=Path, default=Path.home() / 'wekafiles/weka.log')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('weka_evaluation.json'))
    args = parser.parse_args()
    root, home = args.data_root.resolve(), args.weka_home
    java = args.java or next(home.glob('jre/**/java.exe'))
    jar = home / 'weka.jar'
    prefix = [str(java), '--add-opens=java.base/java.lang=ALL-UNNAMED', '-cp', str(jar)]
    data_path = root / 'Feature Extraction/weka_outputs/meeting_dataset.arff'
    text = data_path.read_text(encoding='utf-8')
    header, body = text.split('@DATA')
    raw_rows = [x.strip() for x in body.splitlines() if x.strip() and not x.startswith('%')]
    data = pd.read_csv(root / 'Feature Extraction/weka_outputs/meeting_dataset.csv')
    ids = data.meeting_id.tolist()
    lookup = {}
    for record_id, row in zip(ids, raw_rows, strict=True):
        values = next(csv.reader([row]))
        key = tuple(float(v) for v in values[:-1])
        assert key not in lookup, 'Cannot map nonunique predictor vectors to record IDs'
        lookup[key] = record_id
    historical = {'status': 'not supplied'}
    if args.historical_log.is_file():
        log = args.historical_log.read_text(encoding='utf-8')
        commands = sorted(set(re.findall(r'INFO: Command: (weka\.classifiers\.(?:trees.RandomForest|functions.MultilayerPerceptron)[^\r\n]*)', log)))
        historical = {'source': '~/wekafiles/weka.log', 'sha256': sha(args.historical_log),
                      'recorded_16_instance_relation': 'Base relation is now meeting_effectiveness (16 instances)' in log,
                      'commands': commands,
                      'qualification': 'Application log records model settings, not ARFF hash, evaluation mode, fold seed, predictions, or scores. Seed 1 is an explicit reconstruction assumption, not a recovered historical fact.'}
        for key in ['RandomForest', 'MLP']:
            cls, options = MODELS[key]
            assert ' '.join([cls] + options) in commands, f'{key} differs from recovered command'
    names, sessions, contexts = {}, {}, {}
    for record_id in ids:
        directory = root / 'Feature Extraction/feature_extraction_outputs' / record_id
        participant = pd.read_csv(directory / 'participant_features.csv')
        names[record_id] = {str(x).strip().casefold() for x in participant.person_name.dropna() if str(x).strip()}
        record = pd.read_csv(directory / 'meeting_features.csv').iloc[0]
        context = 'SCI' if record_id.startswith('sci_') else 'HacKSU' if record_id.startswith('hacksu_') else 'CS1'
        contexts.setdefault(context, []).append(record_id)
        sessions.setdefault(context + ':' + record.meeting_date, []).append(record_id)
    scratch = Path(__file__).parent / '.tools/weka_evaluation'
    scratch.mkdir(parents=True, exist_ok=True)
    # Fixed protocols; no hyperparameter or seed search.
    jobs = [(model, 'stratified_10fold_seed1', None, None) for model in MODELS]
    for protocol, groups in [('leave_session_out', sessions), ('leave_context_out', contexts)]:
        for group_index, (_, test_ids) in enumerate(sorted(groups.items())):
            train_ids = [x for x in ids if x not in test_ids]
            train, test = (scratch / f'{protocol}_{group_index}_{part}.arff' for part in ['train', 'test'])
            for path, selected in [(train, train_ids), (test, test_ids)]:
                path.write_text(header + '@DATA\n' + '\n'.join(raw_rows[ids.index(x)] for x in selected) + '\n', encoding='utf-8')
            for model in MODELS:
                jobs.append((model, protocol, group_index, (train, test)))

    def run(job):
        model, protocol, fold, files = job
        cls, options = MODELS[model]
        evaluation = ['-t', str(data_path), '-x', '10', '-s', '1'] if files is None else ['-t', str(files[0]), '-T', str(files[1])]
        command = prefix + [cls] + evaluation + ['-v', '-o', '-classifications', 'weka.classifiers.evaluation.output.prediction.CSV -p first-last -distribution -decimals 12'] + options
        result = subprocess.run(command, text=True, capture_output=True, check=True, timeout=120)
        (scratch / f'{protocol}_{fold}_{model}.out').write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.stderr.strip():
            raise RuntimeError(result.stderr)
        predictions, cv_fold = [], -1
        for line in result.stdout.splitlines():
            if not re.match(r'^\d+,', line):
                continue
            cells = next(csv.reader([line]))
            assert len(cells) == 43, cells
            if files is None and cells[0] == '1':
                cv_fold += 1
            probabilities = [float(x.lstrip('*')) for x in cells[4:7]]
            assert abs(sum(probabilities) - 1) < 1e-9
            record_id = lookup[tuple(float(x) for x in cells[7:])]
            actual, predicted = (x.split(':')[1] for x in cells[1:3])
            assert actual == data.loc[data.meeting_id == record_id, 'effectiveness'].iloc[0]
            predictions.append({'record_id': record_id, 'fold': cv_fold if files is None else fold,
                                'actual': actual, 'predicted': predicted, 'probabilities': probabilities})
        assert predictions, result.stdout
        return model, protocol, predictions

    runs = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for model, protocol, predictions in pool.map(run, jobs):
            runs.setdefault(protocol, {}).setdefault(model, []).extend(predictions)
    result_runs = {}
    for protocol, model_predictions in runs.items():
        result_runs[protocol] = {}
        reference_folds = None
        for model, predictions in model_predictions.items():
            assert sorted(p['record_id'] for p in predictions) == sorted(ids)
            folds = {}
            for row in predictions:
                folds.setdefault(row['fold'], []).append(row['record_id'])
            folds = {k: sorted(v) for k, v in folds.items()}
            if reference_folds is not None:
                assert folds == reference_folds, 'Models must use paired test folds'
            reference_folds = folds
            fold_details = []
            for fold, test_ids in sorted(folds.items()):
                train_ids = [x for x in ids if x not in test_ids]
                train_names, test_names = (set().union(*(names[x] for x in selected)) for selected in [train_ids, test_ids])
                assert set(train_ids).isdisjoint(test_ids)
                if protocol == 'leave_session_out':
                    for session_ids in sessions.values():
                        assert not (set(session_ids) & set(train_ids) and set(session_ids) & set(test_ids))
                fold_details.append({'fold': fold, 'train': train_ids, 'test': test_ids,
                                     'shared_name_strings': len(train_names & test_names),
                                     'train_classes': data[data.meeting_id.isin(train_ids)].effectiveness.value_counts().to_dict()})
            result_runs[protocol][model] = {'metrics': metrics(predictions), 'folds': fold_details, 'predictions': predictions}
    targets = {'RandomForest': ([[4,1,0],[0,7,0],[0,0,4]], [0.9024, 0.2129, 0.2612]),
               'MLP': ([[3,2,0],[0,6,1],[0,0,4]], [0.7091, 0.1758, 0.3269])}
    for model, (matrix, rounded) in targets.items():
        measured = result_runs['stratified_10fold_seed1'][model]['metrics']
        assert measured['matrix'] == matrix
        assert [round(measured[k], 4) for k in ['kappa', 'mae', 'rmse']] == rounded
    components = name_components(names)
    group_limits = []
    for component in components:
        training = data[~data.meeting_id.isin(component)]
        group_limits.append({'held_out_records': component,
                             'training_class_counts': training.effectiveness.value_counts().to_dict(),
                             'missing_training_classes': sorted(set(CLASSES) - set(training.effectiveness))})
    output = {'purpose': 'Numerical reconstruction plus new exploratory baselines and session/context sensitivity; not independent effectiveness validation.',
              'runtime': {'weka_version': subprocess.check_output(prefix + ['weka.core.Version'], text=True).splitlines()[0].strip(),
                          'weka_jar_sha256': sha(jar), 'java_version': subprocess.run([str(java), '-version'], capture_output=True, text=True, check=True).stderr.strip()},
              'input_arff_sha256': sha(data_path), 'historical_log': historical,
              'class_order': CLASSES, 'model_options': MODELS,
              'protocol_notes': {'stratified_10fold_seed1': 'WEKA stratified CV, evaluation seed 1; paired across models. Fold IDs reconstructed from WEKA prediction output. RF/MLP options recovered from log; seed inferred by reconstruction.',
                                 'leave_session_out': '15 context/date groups; both April 3 SCI segments kept together. Training preserves original ARFF order. Repeated participants remain across folds.',
                                 'leave_context_out': 'Three filename-derived contexts. Training preserves original ARFF order. Contexts are not participant-disjoint.',
                                 'preprocessing': 'All 36 saved predictors retained. WEKA Logistic standardizes using each training fold with fixed ridge 1.0 and no tuning; other models use recorded/default internal processing. Existing label generation remains feature-informed.'},
              'participant_group_feasibility': {'components': components, 'fold_class_coverage': group_limits,
                                                'status': 'No complete two-way three-class participant-group evaluation: one training component lacks medium. Names are unverified identity proxies.'},
              'runs': result_runs}
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    for protocol, models in result_runs.items():
        print(protocol, {model: row['metrics']['correct'] for model, row in models.items()}, flush=True)


if __name__ == '__main__':
    main()
