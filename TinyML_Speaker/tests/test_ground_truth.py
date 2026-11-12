from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from ground_truth import IntervalRecorder, merge_annotations, evaluate_reference


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_recorder_supports_overlap_and_saves_uncertainty(tmp_path):
    path = tmp_path / 'intervals.csv'
    recorder = IntervalRecorder(path, 'session', ['badge_01', 'badge_02'], START)
    recorder.change({'badge_01': 'active', 'badge_02': 'active'}, START + timedelta(seconds=1))
    recorder.change({'badge_01': 'unknown', 'badge_02': 'not_active'}, START + timedelta(seconds=2))
    recorder.close(START + timedelta(seconds=3))
    rows = pd.read_csv(path)
    assert len(rows) == 6
    assert set(rows[rows.Start == START.isoformat()].activity_label) == {'unknown'}
    assert (rows.activity_label == 'active').sum() == 2
    with pytest.raises(FileExistsError):
        IntervalRecorder(path, 'session', ['badge_01'], START)


def test_merge_respects_half_open_intervals_unknown_badges_and_session():
    samples = pd.DataFrame({'Timestamp': [START + timedelta(seconds=i) for i in range(4)],
                            'Badge_Name': ['a'] * 4, 'Recording_ID': ['s'] * 4})
    intervals = pd.DataFrame([dict(Recording_ID='s', Badge_Name='a', Start=START + timedelta(seconds=1),
                                   End=START + timedelta(seconds=2), activity_label='active')])
    merged = merge_annotations(samples, intervals)
    assert list(merged.activity_label) == ['unknown', 'active', 'unknown', 'unknown']
    other = samples.assign(Recording_ID='other')
    with pytest.raises(ValueError, match='recording'):
        merge_annotations(other, intervals)
    with pytest.raises(ValueError, match='overlap'):
        merge_annotations(samples, pd.concat([intervals, intervals]))


def test_boundary_guard_excludes_transition_uncertainty():
    samples = pd.DataFrame({'Timestamp': [START + timedelta(seconds=s) for s in [1, 1.1, 1.5, 1.9, 2]],
                            'Badge_Name': ['a'] * 5, 'Recording_ID': ['s'] * 5})
    intervals = pd.DataFrame([dict(Recording_ID='s', Badge_Name='a', Start=START + timedelta(seconds=1),
                                   End=START + timedelta(seconds=2), activity_label='active')])
    merged = merge_annotations(samples, intervals, boundary_ms=200)
    assert list(merged.activity_label) == ['unknown', 'unknown', 'active', 'unknown', 'unknown']


def test_onset_guard_excludes_late_speaking_presses_only():
    samples = pd.DataFrame({'Timestamp': [START + timedelta(seconds=s) for s in [0, 1.9, 2.5, 3, 4, 5, 5.5]],
                            'Badge_Name': ['a'] * 7, 'Recording_ID': ['s'] * 7})
    intervals = pd.DataFrame([dict(Recording_ID='s', Badge_Name='a', Start=START + timedelta(seconds=start),
                                   End=START + timedelta(seconds=end), activity_label=label)
                              for start, end, label in [(0, 3, 'not_active'), (3, 5, 'active'), (5, 6, 'not_active')]])
    merged = merge_annotations(samples, intervals, onset_ms=1000)
    assert list(merged.activity_label) == ['not_active', 'not_active', 'unknown', 'active', 'active',
                                           'not_active', 'not_active']
    with pytest.raises(ValueError, match='nonnegative'):
        merge_annotations(samples, intervals, onset_ms=-1)


def test_merge_rejects_naive_timestamps_and_handles_mixed_iso_precision():
    intervals = pd.DataFrame([dict(Recording_ID='s', Badge_Name='a', Start=START,
                                   End=START + timedelta(seconds=2), activity_label='active')])
    samples = pd.DataFrame(dict(Timestamp=['2026-01-01T00:00:00+00:00', '2026-01-01T00:00:01.123456+00:00'],
                                Badge_Name=['a', 'a'], Recording_ID=['s', 's']))
    assert set(merge_annotations(samples, intervals).activity_label) == {'active'}
    samples['Timestamp'] = ['2026-01-01 00:00:00', '2026-01-01 00:00:01']
    with pytest.raises(ValueError, match='timezone'):
        merge_annotations(samples, intervals)


def test_reference_evaluation_never_counts_unknown_as_negative():
    frame = pd.DataFrame({'activity_label': ['active', 'not_active', 'unknown'],
                          'candidate': [True, True, False]})
    report = evaluate_reference(frame)
    assert report['annotated_rows'] == 2
    assert report['unknown_rows'] == 1
    assert report['confusion_matrix'] == [[0, 1], [0, 1]]
    assert report['precision'] == .5
    assert report['recall'] == 1
    no_negative = evaluate_reference(frame.iloc[[0, 2]])
    assert no_negative['specificity'] is None


def test_recorder_rejects_time_reversal_and_unknown_badge(tmp_path):
    recorder = IntervalRecorder(tmp_path / 'labels.csv', 's', ['a'], START)
    with pytest.raises(ValueError):
        recorder.change({'a': 'active'}, START - timedelta(seconds=1))
    with pytest.raises(ValueError):
        recorder.change({'b': 'active'}, START)
    recorder.close(START + timedelta(seconds=1))


def test_checkpoints_do_not_create_false_label_boundaries(tmp_path):
    path = tmp_path / 'intervals.csv'
    recorder = IntervalRecorder(path, 's', ['a'], START)
    recorder.change({'a': 'active'}, START)
    recorder.change({'a': 'active'}, START + timedelta(seconds=1))
    recorder.close(START + timedelta(seconds=2))
    samples = pd.DataFrame(dict(Timestamp=[START + timedelta(seconds=1)], Badge_Name=['a'], Recording_ID=['s']))
    assert merge_annotations(samples, pd.read_csv(path), boundary_ms=200).activity_label.iloc[0] == 'active'


def test_observer_panel_starts_unknown_and_handles_overlap(tmp_path, tk_window):
    from observer import ObserverPanel
    root = tk_window
    try:
        panel = ObserverPanel(root, tmp_path / 'ui.csv', 's', ['a', 'b'])
        assert panel.paused and set(panel.recorder.states.values()) == {'unknown'}
        panel.start()
        panel.toggle('a')
        panel.toggle('b')
        assert set(panel.recorder.states.values()) == {'active'}
        panel.pause()
        assert set(panel.recorder.states.values()) == {'unknown'}
        panel.silence()
        assert set(panel.recorder.states.values()) == {'not_active'}
        panel.close()
    finally:
        if not panel.closed:
            panel.close()


def test_merge_and_evaluate_cli_end_to_end(tmp_path):
    import json
    from pathlib import Path
    import subprocess
    import sys
    script = Path(__file__).resolve().parents[1] / 'pipeline.py'
    raw = tmp_path / 'raw.csv'
    reference = tmp_path / 'reference.csv'
    merged = tmp_path / 'training.csv'
    report = tmp_path / 'report.json'
    pd.DataFrame(dict(Timestamp=[START + timedelta(seconds=1)] * 2, Recording_ID=['s', 's'],
                      Badge_Name=['a', 'b'], candidate=[True, False])).to_csv(raw, index=False)
    pd.DataFrame([dict(Recording_ID='s', Badge_Name=badge, Start=START,
                       End=START + timedelta(seconds=2), activity_label=label)
                  for badge, label in [('a', 'active'), ('b', 'not_active')]]).to_csv(reference, index=False)
    subprocess.run([sys.executable, str(script), 'merge', str(raw), str(reference), '--output', str(merged)], check=True)
    subprocess.run([sys.executable, str(script), 'evaluate', str(merged), '--output', str(report)], check=True)
    result = json.loads(report.read_text())
    assert result['annotated_rows'] == 2
    assert result['confusion_matrix'] == [[1, 0], [0, 1]]
