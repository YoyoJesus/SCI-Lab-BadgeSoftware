from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from typing import Optional

import pandas as pd
import pytest

from ground_truth import combine_references, observer_agreement, session_reference
from remote_observer import RemoteObserver

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def intervals(badge: str, spans: list[tuple[float, float, str]]) -> pd.DataFrame:
    return pd.DataFrame([dict(Recording_ID='s', Badge_Name=badge, Start=(START + timedelta(seconds=a)).isoformat(),
                              End=(START + timedelta(seconds=b)).isoformat(), activity_label=label)
                         for a, b, label in spans])


def test_consensus_keeps_agreement_and_marks_disagreement_unknown():
    first = intervals('a', [(0, 2, 'not_active'), (2, 5, 'active'), (5, 8, 'not_active')])
    second = intervals('a', [(0, 3, 'not_active'), (3, 5, 'active'), (5, 6, 'unknown'), (6, 8, 'not_active')])
    combined = combine_references(first, second)
    spans = [((pd.Timestamp(r.Start) - START).total_seconds(), (pd.Timestamp(r.End) - START).total_seconds(),
              r.activity_label) for r in combined.itertuples()]
    assert spans == [(0, 2, 'not_active'), (2, 3, 'unknown'), (3, 5, 'active'), (5, 6, 'unknown'), (6, 8, 'not_active')]


def test_consensus_treats_time_only_one_observer_covered_as_unknown():
    first = intervals('a', [(0, 4, 'active')])
    second = intervals('a', [(2, 4, 'active')]).assign(Badge_Name='a')
    combined = combine_references(first, pd.concat([second, intervals('b', [(0, 4, 'active')])]))
    assert list(zip(combined.Badge_Name, combined.activity_label)) == [('a', 'unknown'), ('a', 'active'), ('b', 'unknown')]


def test_agreement_reports_time_agreement_and_onset_gap():
    first = intervals('a', [(0, 2, 'not_active'), (2, 5, 'active'), (5, 10, 'not_active')])
    second = intervals('a', [(0, 3, 'not_active'), (3, 5, 'active'), (5, 10, 'not_active')])
    report = observer_agreement(first, second)
    assert report['both_labeled_seconds'] == pytest.approx(10)
    assert report['agreement'] == pytest.approx(.9)
    assert report['onsets_matched'] == 1
    assert report['median_onset_gap_ms'] == pytest.approx(1000)
    assert report['median_offset_gap_ms'] == pytest.approx(0)


def test_overlapping_intervals_are_rejected():
    first = intervals('a', [(0, 3, 'active'), (2, 4, 'not_active')])
    with pytest.raises(ValueError, match='overlap'):
        combine_references(first, intervals('a', [(0, 4, 'active')]))


def request(url: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST' if data else 'GET'), timeout=5) as reply:
        return json.loads(reply.read())


def test_remote_observer_records_taps_and_rejects_wrong_code(tmp_path: Path):
    output = tmp_path / 'reference_observer2.csv'
    remote = RemoteObserver(output, 's', ['a', 'b'], host='127.0.0.1', port=0)
    try:
        base = f'http://127.0.0.1:{remote.port}/{remote.code}'
        with pytest.raises(urllib.error.HTTPError):
            request(f'http://127.0.0.1:{remote.port}/wrong/state')
        assert request(f'{base}/state')['paused'] is True
        request(f'{base}/action', {'action': 'start'})
        state = request(f'{base}/action', {'action': 'toggle', 'badge': 'a'})
        assert state['labels'] == {'a': 'active', 'b': 'not_active'}
        with pytest.raises(urllib.error.HTTPError):
            request(f'{base}/action', {'action': 'toggle', 'badge': 'zzz'})
        time.sleep(.3)
    finally:
        remote.close()
    rows = pd.read_csv(output)
    assert set(rows.Badge_Name) == {'a', 'b'}
    assert 'active' in set(rows[rows.Badge_Name == 'a'].activity_label)


def test_remote_observer_pauses_when_the_page_goes_quiet(tmp_path: Path):
    remote = RemoteObserver(tmp_path / 'r.csv', 's', ['a'], host='127.0.0.1', port=0, heartbeat_seconds=.3)
    try:
        base = f'http://127.0.0.1:{remote.port}/{remote.code}'
        request(f'{base}/action', {'action': 'start'})
        request(f'{base}/action', {'action': 'toggle', 'badge': 'a'})
        time.sleep(.8)
        state = request(f'{base}/state')
        assert state['paused'] is True and state['labels'] == {'a': 'unknown'}
    finally:
        remote.close()


def test_second_observer_who_never_labeled_does_not_erase_the_first():
    first = intervals('a', [(0, 4, 'active')])
    idle = intervals('a', [(0, 4, 'unknown')])
    labels, agreement = session_reference(first, idle)
    assert agreement is None and labels.equals(first)
    assert session_reference(first, None)[1] is None
    labels, agreement = session_reference(first, intervals('a', [(0, 4, 'active')]))
    assert agreement['agreement'] == pytest.approx(1) and list(labels.activity_label) == ['active']


def test_combine_cli_writes_consensus_and_report(tmp_path: Path):
    import subprocess
    import sys
    script = Path(__file__).resolve().parents[1] / 'pipeline.py'
    first, second = tmp_path / 'one.csv', tmp_path / 'two.csv'
    intervals('a', [(0, 2, 'not_active'), (2, 4, 'active')]).to_csv(first, index=False)
    intervals('a', [(0, 3, 'not_active'), (3, 4, 'active')]).to_csv(second, index=False)
    subprocess.run([sys.executable, str(script), 'combine', str(first), str(second), '--output',
                    str(tmp_path / 'consensus.csv'), '--report', str(tmp_path / 'agreement.json')], check=True,
                   capture_output=True)
    assert list(pd.read_csv(tmp_path / 'consensus.csv').activity_label) == ['not_active', 'unknown', 'active']
    assert json.loads((tmp_path / 'agreement.json').read_text())['agreement'] == pytest.approx(.75)
