from datetime import datetime, timezone
from tkinter import ttk

from viewer import PlotHistory, SpeakerViewer, candidate_state
from observer import ObserverPanel


def sample(seq, tick):
    return dict(seq=seq, device_ms=tick, seq_gap=0, late_samples=0, Sound_Level=20,
                Acceleration=.1, speech_score=1, model_score=-1, candidate=True,
                ready=True, model_id='paper-rule', Timestamp=datetime.now(timezone.utc).isoformat())


def test_missing_hybrid_prediction_is_not_shown_as_verified_silence():
    assert candidate_state(dict(sample(0, 0), model_id='synthetic-model', model_score=-1, candidate=False)) == 'unavailable'
    assert candidate_state(dict(sample(0, 0), ready=False)) == 'warming up'
    assert candidate_state(sample(0, 0)) == 'speaking'


def test_plot_history_is_bounded_and_uses_acquisition_time():
    history = PlotHistory(max_samples=100)
    history.add('badge_01', [sample(i, i * 5) for i in range(200)])
    assert len(history.rows['badge_01']) == 100
    assert history.rate('badge_01') == 200
    assert history.counts['badge_01'] == 200
    visible = history.visible('badge_01', seconds=.1, max_points=10)
    assert len(visible) <= 10
    assert visible[-1]['device_ms'] == 995
    assert min(row['device_ms'] for row in visible) >= 895


def test_embedded_observer_closes_without_destroying_viewer(tmp_path, tk_window):
    root = tk_window
    host = ttk.Frame(root)
    panel = ObserverPanel(root, tmp_path / 'reference.csv', 'demo', ['a'], container=host)
    try:
        panel.set_active(True)
        panel.start()
        panel.toggle('a')
        assert panel.recorder.states['a'] == 'active'
        panel.set_active(False)
        assert panel.recorder.states['a'] == 'unknown'
        assert panel.paused
        panel.close()
        assert root.winfo_exists()
    finally:
        if not panel.closed:
            panel.close()
        root.destroy()


def test_viewer_demo_keeps_predictions_out_of_observer_tab(tmp_path, tk_window):
    root = tk_window
    viewer = SpeakerViewer(root, demo=True, output_root=tmp_path)
    try:
        root.update_idletasks()
        assert set(viewer.history.rows) == {'badge_01', 'badge_02', 'badge_03'}
        viewer.tabs.select(viewer.reference_tab)
        viewer.tab_changed()
        assert viewer.observer.enabled
        viewer.observer.start()
        viewer.observer.toggle('badge_01')
        viewer.tabs.select(viewer.monitor_tab)
        viewer.tab_changed()
        assert viewer.observer.paused
        assert not viewer.observer.enabled
        assert set(viewer.observer.recorder.states.values()) == {'unknown'}
    finally:
        viewer.close()


def test_reference_save_failure_stops_panel_without_closing_live_viewer(tmp_path, monkeypatch, tk_window):
    import observer
    root = tk_window
    panel = ObserverPanel(root, tmp_path / 'reference.csv', 'demo', ['a'], container=ttk.Frame(root))
    def fail(*args):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(panel.recorder, 'change', fail)
    errors = []
    def show_error(*args, **kwargs):
        assert panel.closed
        errors.append(args)
    monkeypatch.setattr(observer.messagebox, 'showerror', show_error)
    try:
        panel.save()
        assert panel.closed and errors
        assert root.winfo_exists()
    finally:
        root.destroy()


def test_empty_connection_error_is_not_reported_as_success(tmp_path, monkeypatch, tk_window):
    import time
    import viewer as module
    async def fail(*args, **kwargs):
        raise TimeoutError()
    monkeypatch.setattr(module, 'receive', fail)
    root = tk_window
    app = SpeakerViewer(root, output_root=tmp_path)
    try:
        app.devices = ['synthetic-device']
        app.device_list.insert('end', 'Synthetic badge')
        app.device_list.selection_set(0)
        app.toggle_capture()
        deadline = time.monotonic() + 3
        while app.running and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert not app.running
        assert 'Capture failed: TimeoutError' in app.status.get()
    finally:
        app.close()


def test_plots_align_badges_by_acquisition_utc_not_individual_uptime(tmp_path, tk_window):
    root = tk_window
    app = SpeakerViewer(root, output_root=tmp_path)
    try:
        first = [dict(sample(0, 0), Timestamp='2026-01-01T00:00:00+00:00'),
                 dict(sample(1, 5), Timestamp='2026-01-01T00:00:01+00:00')]
        second = [dict(sample(0, 0), Timestamp='2026-01-01T00:00:02+00:00'),
                  dict(sample(1, 5), Timestamp='2026-01-01T00:00:03+00:00')]
        app.history.add('a', first)
        app.history.add('b', second)
        app.draw()
        lines = app.axes['Sound_Level'].lines
        assert list(lines[0].get_xdata()) == [-3, -2]
        assert list(lines[1].get_xdata()) == [-1, 0]
    finally:
        app.close()
