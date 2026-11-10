import numpy as np
import pytest

from pipeline import Detector, vote_winner, decode_line, group_split, export_tree


def test_training_evaluates_same_holdout_and_skips_unknown(tmp_path, monkeypatch):
    import argparse
    import json
    import pandas as pd
    import pipeline
    monkeypatch.setattr(pipeline, 'ROOT', tmp_path)
    rng = np.random.default_rng(18)
    rows = []
    for session in range(4):
        for i in range(100):
            active = i % 2 == 0
            row = dict(zip(pipeline.FEATURES, rng.uniform(1, 5, len(pipeline.FEATURES))))
            row.update(norm_sound=10 if active else 0, norm_accel=0,
                       presence_margin=1 if active else -1, ready=True,
                       activity_label='active' if active else 'not_active', Recording_ID=f's{session}')
            rows.append(row)
    rows.append(dict(rows[0], activity_label='unknown'))
    source = tmp_path / 'synthetic.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    args = argparse.Namespace(csv=[str(source)], label='activity_label', allow_pseudo_labels=False,
                              output=str(tmp_path / 'evaluation'))
    pipeline.train(args)
    report = json.loads((tmp_path / 'evaluation/evaluation.json').read_text())
    assert report['unknown_rows_skipped'] == 1
    assert report['train_rows'] + report['test_rows'] == 400
    assert report['decision_threshold'] == .6
    assert report['classification_report']['accuracy'] == 1
    assert 'paper_rule_report' in report and 'paper_features_ml_report' in report
    assert (tmp_path / 'firmware/SpeakerBadge/model.h').exists()
    rows[0]['Proximity'] = -1
    pd.DataFrame(rows).to_csv(source, index=False)
    with pytest.raises(ValueError, match='Unavailable'):
        pipeline.train(args)


def test_label_frame_uses_peak_eligible_sample_and_centered_vote():
    import pandas as pd
    from pipeline import label_frame
    rows = []
    for i in range(5):
        for badge, score, candidate in [('a', 2, True), ('b', 100, False)]:
            rows.append(dict(Timestamp=f'2026-01-01T00:00:0{i}+00:00', Badge_Name=badge,
                             speech_score=score, candidate=candidate))
    result = label_frame(pd.DataFrame(rows))
    assert set(result['auto_speaker']) == {'a'}
    assert set(result[result.Badge_Name == 'b'].auto_activity_label) == {'not_active'}


def test_replay_preserves_hybrid_candidates_and_refuses_overwrite(tmp_path):
    import argparse
    import pandas as pd
    import pipeline
    rows = []
    for i in range(5):
        row = dict.fromkeys(pipeline.FIELDS, 0)
        row.update(Timestamp=f'2026-01-01T00:00:0{i}+00:00', Badge_Name='a',
                   Sound_Level=10, Acceleration=0, candidate=True, ready=True,
                   speech_score=0, model_score=.9)
        rows.append(row)
    source, output = tmp_path / 'input.csv', tmp_path / 'result.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    args = argparse.Namespace(csv=source, output=output)
    pipeline.replay(args)
    assert set(pd.read_csv(output).auto_speaker) == {'a'}
    with pytest.raises(FileExistsError):
        pipeline.replay(args)


def test_pseudo_labels_require_explicit_opt_in(tmp_path):
    import argparse
    import pipeline
    args = argparse.Namespace(csv=[str(tmp_path / 'missing.csv')], label='auto_activity_label',
                              allow_pseudo_labels=False, output=str(tmp_path))
    with pytest.raises(ValueError, match='agreement only'):
        pipeline.train(args)


def test_warmup_constant_baseline_and_paper_thresholds():
    detector = Detector()
    for _ in range(9):
        assert detector.update(10, 0) is None
    assert detector.update(10, 0)['candidate'] is False
    row = detector.update(100, 0)
    assert row['norm_sound'] == 90
    assert row['candidate'] is True
    row = detector.update(10, 10)
    assert row['score'] == pytest.approx(3)


def test_relative_bump_below_loudness_floor_is_not_speech():
    detector = Detector()
    for _ in range(20):
        detector.update(100, 0)
    row = detector.update(400, 0)
    assert row['score'] >= 3.5 and row['candidate'] is False
    assert detector.update(900, 0)['candidate'] is True


def test_label_frame_needs_half_of_each_bin_and_one_second_runs():
    import pandas as pd
    from pipeline import label_frame
    rows = []
    for tick in range(10):
        for sample in range(4):
            stamp = f'2026-01-01T00:00:{tick // 2:02d}.{5 * (tick % 2)}{sample}+00:00'
            # 'a' flags one sample in every bin; 'b' flags whole bins, but never two in a row.
            rows.append(dict(Timestamp=stamp, Badge_Name='a', speech_score=5, candidate=sample == 0))
            rows.append(dict(Timestamp=stamp, Badge_Name='b', speech_score=5, candidate=tick % 2 == 0))
    result = label_frame(pd.DataFrame(rows))
    assert set(result['auto_speaker']) == {'no_speaker'}


def test_invalid_readings_reset_history():
    detector = Detector()
    for _ in range(10):
        detector.update(10, 0)
    with pytest.raises(ValueError):
        detector.update(float('nan'), 0)
    assert detector.update(10, 0) is None


def test_vote_needs_three_wins_and_preserves_silence():
    assert vote_winner(['a', 'a', None, 'a', 'b']) == 'a'
    assert vote_winner(['a', 'a', None, 'b', 'b']) is None
    assert vote_winner([None] * 5) is None


def test_transport_rejects_bad_numbers_and_accepts_warmup():
    line = 'S,1,100,12,0.2,0,0,0,0,-1,0,0,0,0,20,22,45,100,0,0'
    assert decode_line(line)['ready'] is False
    for invalid in [line.replace('12,', 'nan,'), 'S,1', line.replace(',0.2,', ',-1,')]:
        with pytest.raises(ValueError):
            decode_line(invalid)


def test_group_split_keeps_recordings_together():
    y = np.tile([0, 1], 5)
    groups = np.repeat(np.arange(5), 2)
    train, test = group_split(y, groups)
    assert not set(groups[train]) & set(groups[test])
    with pytest.raises(ValueError):
        group_split(np.array([0, 1]), np.array(['one', 'one']))


def test_export_tree_contains_both_outcomes(tmp_path):
    from sklearn.tree import DecisionTreeClassifier
    tree = DecisionTreeClassifier(max_depth=2).fit([[0, 0, 0], [10, 0, 1]], [0, 1])
    path = tmp_path / 'model.h'
    export_tree(tree, path, 'test123')
    text = path.read_text()
    assert 'wearerModel' in text
    assert 'test123' in text
    assert 'return 1.000000000f' in text
    assert 'return 0.000000000f' in text
