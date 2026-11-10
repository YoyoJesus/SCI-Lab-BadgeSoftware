from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from review import Recording

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def write_run(folder, labels=True):
    rows = []
    for badge in ['badge_01', 'badge_02']:
        for i in range(40):
            rows.append(dict(Timestamp=(START + timedelta(seconds=i * .25)).isoformat(), Badge_Name=badge,
                             Recording_ID='synthetic', model_id='paper-rule', model_score=-1.0, ready=i >= 4,
                             candidate=badge == 'badge_01' and i >= 20, Sound_Level=10.0 + i, Acceleration=.01))
    folder.mkdir()
    raw = folder / '20260101T000000000000Z_raw.csv'
    pd.DataFrame(rows).to_csv(raw, index=False)
    if labels:
        pd.DataFrame([dict(Recording_ID='synthetic', Badge_Name='badge_01', Start=START.isoformat(),
                           End=(START + timedelta(seconds=5)).isoformat(), activity_label='not_active'),
                      dict(Recording_ID='synthetic', Badge_Name='badge_01', Start=(START + timedelta(seconds=5)).isoformat(),
                           End=(START + timedelta(seconds=10)).isoformat(), activity_label='active')]).to_csv(
            folder / 'reference.csv', index=False)
    return raw


def test_past_run_summarizes_detection_against_observer_labels(tmp_path):
    run = Recording(write_run(tmp_path / 'session'))
    assert run.labeled and run.duration == pytest.approx(9.75)
    summary = {row['badge']: row for row in run.summary()}
    assert summary['badge_01']['detected'] == pytest.approx(20 / 36)
    assert summary['badge_01']['labeled'] == pytest.approx(.5)
    assert summary['badge_01']['agreement'] == 1
    assert summary['badge_02']['labeled'] is None and summary['badge_02']['agreement'] is None
    part = run.window('badge_01', end=9.75, seconds=2)
    assert part['observer_label'].eq(1).all()
    assert part['t'].between(7.75, 9.75).all()
    assert run.window('badge_01', end=.5, seconds=2)['candidate'].isna().all()


def test_past_run_without_labels_still_opens(tmp_path):
    run = Recording(write_run(tmp_path / 'session', labels=False))
    assert not run.labeled and 'No observer labels' in run.note
    assert all(row['labeled'] is None for row in run.summary())


def test_viewer_reviews_past_run_and_returns_to_live(tmp_path, tk_window):
    from viewer import SpeakerViewer
    root = tk_window
    app = SpeakerViewer(root, output_root=tmp_path)
    try:
        app.show_review(Recording(write_run(tmp_path / 'session')))
        root.update_idletasks()
        assert {'observer_label', 'candidate', 'Sound_Level'} <= set(app.axes)
        assert app.axes['Sound_Level'].get_xlim() == (0 - 30 + 9.75, 9.75)
        assert len(app.axes['observer_label'].lines) == 2
        app.exit_review()
        assert 'observer_label' not in app.axes
        assert app.review is None
    finally:
        app.close()


def test_detection_tiles_stay_hidden_while_labeling_unless_enabled(tmp_path, tk_window):
    from viewer import SpeakerViewer
    root = tk_window
    app = SpeakerViewer(root, demo=True, output_root=tmp_path)
    try:
        root.update()
        assert not app.tiles.winfo_manager()
        app.show_detections.set(True)
        app.refresh_predictions()
        root.update()
        assert app.tiles.winfo_manager() == 'pack'
        assert 'candidate' in app.axes
        texts = {badge: label.cget('text') for badge, label in app.tile_labels.items()}
        assert set(texts) == {'badge_01', 'badge_02', 'badge_03'}
        assert all('Speaking' in text or 'Quiet' in text for text in texts.values())
        app.show_detections.set(False)
        app.refresh_predictions()
        root.update()
        assert not app.tiles.winfo_manager()
        app.observer.close()
        root.update()
        assert app.tiles.winfo_manager() == 'pack'
    finally:
        app.close()


def test_all_unknown_labels_count_as_unlabeled(tmp_path):
    raw = write_run(tmp_path / 'session', labels=False)
    pd.DataFrame([dict(Recording_ID='synthetic', Badge_Name='badge_01', Start=START.isoformat(),
                       End=(START + timedelta(seconds=10)).isoformat(), activity_label='unknown')]).to_csv(
        raw.parent / 'reference.csv', index=False)
    run = Recording(raw)
    assert not run.labeled and 'unknown' in run.note
