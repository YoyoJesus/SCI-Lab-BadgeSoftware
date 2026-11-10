"""Speaker dashboard adapted from the existing native Nano realtime viewer."""
import argparse
import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import math
import os
from pathlib import Path
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ground_truth import merge_annotations
from observer import ObserverPanel
from pipeline import ROOT, SERVICE, receive

PLOTS = [
    ('Sound_Level', 'Microphone power', 'power', True),
    ('Acceleration', 'Motion over 100 ms', 'g', True),
    ('speech_score', 'Paper speech score', 'score', True),
    ('candidate', 'Local speaking candidate', 'off / on', True),
    ('model_score', 'Hybrid model score', 'score', False),
    ('Gyro_Magnitude', 'Gyroscope', 'degrees/s', False),
    ('Mag_Magnitude', 'Magnetometer', 'uT', False),
    ('Temperature', 'Temperature', 'C', False),
    ('Humidity', 'Humidity', '%', False),
    ('Pressure', 'Pressure', 'kPa', False),
    ('Proximity', 'Proximity', 'counts', False),
]
PREDICTIONS = {'speech_score', 'candidate', 'model_score'}
COLUMNS = ('badge', 'device', 'link', 'rate', 'received', 'gaps', 'drops', 'candidate', 'model')


def candidate_state(row: dict) -> str:
    if not row['ready']:
        return 'warming up'
    if row['model_id'] not in ['paper-rule', 'unknown'] and row['model_score'] < 0:
        return 'unavailable'
    return 'speaking' if row['candidate'] else 'not speaking'


class PlotHistory:
    def __init__(self, max_samples: int = 12000) -> None:
        self.rows: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_samples))
        self.counts: dict[str, int] = defaultdict(int)
        self.gaps: dict[str, int] = defaultdict(int)
        self.first_drops: dict[str, int] = {}

    def add(self, badge: str, rows: list[dict]) -> None:
        if rows:
            self.first_drops.setdefault(badge, rows[0]['late_samples'])
        self.rows[badge].extend(rows)
        self.counts[badge] += len(rows)
        self.gaps[badge] += sum(row['seq_gap'] for row in rows)

    def rate(self, badge: str) -> float:
        rows = self.rows[badge]
        if len(rows) < 2:
            return 0
        # Unsigned deltas keep the display valid across the device clock wrap.
        end = rows[-1]['device_ms']
        recent = []
        for row in reversed(rows):
            if ((end - row['device_ms']) & 0xFFFFFFFF) > 2000:
                break
            recent.append(row)
        span = (end - recent[-1]['device_ms']) & 0xFFFFFFFF
        return (len(recent) - 1) * 1000 / span if span else 0

    def visible(self, badge: str, seconds: float, max_points: int = 2000) -> list[dict]:
        if not self.rows[badge]:
            return []
        end = self.rows[badge][-1]['device_ms']
        rows = [row for row in self.rows[badge] if ((end - row['device_ms']) & 0xFFFFFFFF) <= seconds * 1000]
        stride = max(1, math.ceil(len(rows) / max(1, max_points - 1)))
        sampled = rows[::stride]
        if sampled and sampled[-1] is not rows[-1]:
            sampled.append(rows[-1])
        return sampled


class SpeakerViewer:
    def __init__(self, root: tk.Tk, demo: bool = False, output_root: Path = ROOT / 'outputs') -> None:
        self.root, self.demo, self.output_root = root, demo, output_root
        self.running = self.closing = self.destroyed = self.annotating = False
        self.preview_skips = 0
        self.history = PlotHistory()
        self.events: queue.Queue = queue.Queue()
        self.samples: queue.Queue = queue.Queue(maxsize=2000)
        self.stop_event = threading.Event()
        self.observer = None
        self.session_dir = self.raw_path = None
        self.devices: list[str] = []
        self.badge_devices: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.session = tk.StringVar(value='session_01')
        self.rate = tk.StringVar(value='200')
        self.send = tk.StringVar(value='5')
        self.window = tk.StringVar(value='30')
        self.refresh = tk.StringVar(value='5')
        self.status = tk.StringVar(value='Demo data only. No badge is connected.' if demo else 'Scan for badges, select devices, then start a recording.')
        self.saved = tk.StringVar(value='Every received sample is saved. Plotting uses a bounded, thinned history.')
        root.title('Speaker badge lab' + (' | DEMO DATA' if demo else ''))
        width = min(1400, int(root.winfo_screenwidth() * .9))
        height = min(860, int(root.winfo_screenheight() * .85))
        root.geometry(f'{width}x{height}')
        root.minsize(960, 600)
        style = ttk.Style(root)
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=(8, 5))
        style.configure('Treeview', rowheight=28, font=('Segoe UI', 10))
        self.build_ui()
        self.last_draw = 0.0
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_timer = self.root.after(50, self.poll)
        if demo:
            self.load_demo()

    def build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 8, 12, 2))
        header.pack(fill='x')
        ttk.Label(header, text='Speaker badge lab', font=('Segoe UI', 14, 'bold')).pack(side='left')
        ttk.Label(header, text='DEMO DATA | Synthetic signals' if self.demo else 'High-rate acquisition | Bulk BLE | Human reference').pack(side='right')
        controls = ttk.Frame(self.root, padding=(12, 2, 12, 6))
        controls.pack(fill='x')
        badge_header = ttk.Frame(controls)
        badge_header.grid(row=0, column=0, sticky='ew', padx=(0, 12))
        ttk.Label(badge_header, text='Badges (Ctrl/Shift for several)').pack(side='left')
        self.scan_button = ttk.Button(badge_header, text='Scan BLE', command=self.scan)
        self.scan_button.pack(side='right')
        self.device_list = tk.Listbox(controls, height=4, width=36, selectmode='extended', exportselection=False, font=('Segoe UI', 10))
        self.device_list.grid(row=1, column=0, rowspan=3, sticky='nsew', padx=(0, 12))
        self.inputs = []
        for column, (label, variable, values, width) in enumerate([
            ('Recording ID', self.session, None, 20), ('Sample rate (Hz)', self.rate, ['10', '50', '100', '200'], 8),
            ('Send every (s)', self.send, ['0', '1', '2', '5', '10', '30'], 8)], 1):
            ttk.Label(controls, text=label).grid(row=0, column=column, sticky='w', padx=6)
            widget = ttk.Entry(controls, textvariable=variable, width=width) if values is None else ttk.Combobox(
                controls, textvariable=variable, values=values, width=width, state='readonly')
            widget.grid(row=1, column=column, sticky='ew', padx=6)
            self.inputs.append(widget)
        self.capture_button = ttk.Button(controls, text='Start recording', command=self.toggle_capture)
        self.capture_button.grid(row=2, column=1, sticky='w', padx=6, pady=4)
        self.folder_button = ttk.Button(controls, text='Open session folder', command=self.open_folder, state='disabled')
        self.folder_button.grid(row=2, column=2, columnspan=2, sticky='w', padx=6)
        status = ttk.Label(controls, textvariable=self.status)
        status.grid(row=3, column=1, columnspan=3, sticky='ew', padx=6)
        status.bind('<Configure>', lambda event: status.configure(wraplength=max(200, event.width)))
        controls.columnconfigure(1, weight=1)
        self.panes = ttk.PanedWindow(self.root, orient='horizontal')
        self.panes.pack(fill='both', expand=True, padx=12)
        self.monitor_pane = ttk.Frame(self.panes, width=1, height=1)
        self.reference_pane = ttk.Frame(self.panes, width=400, height=1)
        self.panes.add(self.monitor_pane, weight=3)
        self.panes.add(self.reference_pane, weight=1)
        ttk.Label(self.reference_pane, text='Observer labels become available once the badges connect. '
                  'Prediction charts are hidden while the observer panel is open.', wraplength=360, padding=16).pack(anchor='w')
        self.table = ttk.Treeview(self.monitor_pane, columns=COLUMNS, show='headings', height=3)
        for name, label, width in zip(COLUMNS, ['Badge', 'Device', 'Link', 'Acquired Hz', 'Received', 'Seq gaps', 'New drops',
                                                'Candidate', 'Model'], [70, 120, 90, 80, 75, 65, 75, 90, 100]):
            self.table.heading(name, text=label)
            self.table.column(name, width=width, minwidth=50, stretch=True)
        self.table.pack(fill='x', pady=(4, 4))
        plot_controls = ttk.Frame(self.monitor_pane)
        plot_controls.pack(fill='x', pady=2)
        charts = ttk.Menubutton(plot_controls, text='Charts')
        charts.pack(side='left', padx=(0, 14))
        self.chart_menu = tk.Menu(charts, tearoff=False)
        charts['menu'] = self.chart_menu
        self.plot_vars = {}
        for field, title, _, default in PLOTS:
            self.plot_vars[field] = tk.BooleanVar(value=default)
            self.chart_menu.add_checkbutton(label=title, variable=self.plot_vars[field], command=self.rebuild_plots)
        ttk.Label(plot_controls, text='Visible seconds').pack(side='left')
        ttk.Combobox(plot_controls, textvariable=self.window, values=['10', '20', '30', '60'], width=4, state='readonly').pack(side='left', padx=(5, 14))
        ttk.Label(plot_controls, text='Refresh (Hz)').pack(side='left')
        ttk.Combobox(plot_controls, textvariable=self.refresh, values=['1', '2', '5', '10'], width=4, state='readonly').pack(side='left', padx=5)
        plot_area = ttk.Frame(self.monitor_pane, width=1, height=1)
        plot_area.pack(fill='both', expand=True, pady=4)
        plot_area.pack_propagate(False)
        self.figure = Figure(figsize=(10, 5), dpi=100, constrained_layout=True)
        self.canvas = FigureCanvasTkAgg(self.figure, plot_area)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.rebuild_plots()
        footer = ttk.Frame(self.root, padding=(12, 4))
        footer.pack(fill='x')
        ttk.Label(footer, textvariable=self.saved).pack(side='left')
        self.merge_button = ttk.Button(footer, text='Merge observer labels', command=self.merge_labels, state='disabled')
        self.merge_button.pack(side='right')
        if self.demo:
            self.scan_button.configure(state='disabled')
            self.capture_button.configure(state='disabled')

    def rebuild_plots(self) -> None:
        self.figure.clear()
        self.axes = {}
        selected = [plot for plot in PLOTS if self.plot_vars[plot[0]].get()
                    and not (self.annotating and plot[0] in PREDICTIONS)]
        columns = 1 if len(selected) <= 3 else 2
        for index, (field, title, unit, _) in enumerate(selected, 1):
            axis = self.figure.add_subplot(math.ceil(len(selected) / columns), columns, index)
            axis.set_title(title, loc='left', fontsize=10)
            axis.set_ylabel(unit, fontsize=9)
            if index > len(selected) - columns:
                axis.set_xlabel('Acquisition time (seconds from latest)', fontsize=9)
            axis.grid(True, alpha=.2)
            self.axes[field] = axis
        if not selected:
            self.figure.text(.5, .5, 'Choose charts from the Charts menu', ha='center')
        self.canvas.draw_idle()

    def emit(self, kind: str, payload: dict) -> None:
        if kind == 'samples':
            try:
                self.samples.put_nowait(payload)
            except queue.Full:
                self.preview_skips += 1  # The shared receiver saves CSV before preview delivery.
        else:
            self.events.put((kind, payload))

    def scan(self) -> None:
        self.scan_button.configure(state='disabled')
        self.status.set('Scanning for speaker badges...')
        def work() -> None:
            from bleak import BleakScanner
            try:
                devices = asyncio.run(BleakScanner.discover(timeout=5, service_uuids=[SERVICE]))
                self.emit('devices', {'devices': [(d.address, d.name or 'Speaker badge') for d in devices]})
            except Exception as error:
                self.emit('scan_error', {'error': f'{type(error).__name__}: {error}'})
        threading.Thread(target=work, daemon=True).start()

    def toggle_capture(self) -> None:
        if self.running:
            self.stop_event.set()
            self.capture_button.configure(state='disabled', text='Draining...')
            self.status.set('Stopping acquisition and draining buffered samples...')
            if self.observer:
                self.observer.close()
            return
        selected = [self.devices[i] for i in self.device_list.curselection()]
        if not selected:
            self.status.set('Scan and select at least one badge first.')
            return
        recording_id = self.session.get().strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', recording_id):
            self.status.set('Use an anonymous recording ID with letters, digits, underscores, or hyphens.')
            return
        if len(selected) > 9:
            self.status.set('Select at most nine badges for the observer panel.')
            return
        self.history = PlotHistory()
        self.preview_skips = 0
        self.table.delete(*self.table.get_children())
        self.links = {}
        if self.observer and not self.observer.closed:
            self.observer.close()
        self.session_dir = self.output_root / f'{recording_id}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")}'
        self.raw_path = None
        self.stop_event = threading.Event()
        self.running = True
        self.set_capture_controls(True)
        self.status.set('Connecting and synchronizing acquisition clocks...')
        args = argparse.Namespace(scan=False, address=selected, output=str(self.session_dir), recording_id=recording_id,
                                  rate=int(self.rate.get()), send_seconds=float(self.send.get()), seconds=86400, raw_only=True)
        def work() -> None:
            error = None
            try:
                asyncio.run(receive(args, on_event=self.emit, stop_event=self.stop_event))
            except Exception as exception:
                error = f'{type(exception).__name__}: {exception}'
            self.emit('done', {'error': error})
        threading.Thread(target=work, daemon=True).start()

    def set_capture_controls(self, running: bool) -> None:
        self.capture_button.configure(text='Stop and save' if running else 'Start recording', state='normal')
        self.scan_button.configure(state='disabled' if running else 'normal')
        for i, widget in enumerate(self.inputs):
            widget.configure(state='disabled' if running else ('normal' if i == 0 else 'readonly'))
        self.device_list.configure(state='disabled' if running else 'normal')
        self.merge_button.configure(state='disabled' if running else 'normal')

    def set_annotating(self, active: bool) -> None:
        # Keep observer labels independent of the predictions they will be used to evaluate.
        self.annotating = active
        self.table.configure(displaycolumns=[c for c in COLUMNS if c not in ['candidate', 'model']] if active else '#all')
        for index, (field, *_) in enumerate(PLOTS):
            if field in PREDICTIONS:
                self.chart_menu.entryconfigure(index, state='disabled' if active else 'normal')
        self.rebuild_plots()
        self.draw()

    def create_observer(self, badges: list[str]) -> None:
        for child in self.reference_pane.winfo_children():
            child.destroy()
        mapping = ', '.join(f'{badge}: {self.badge_devices.get(badge, badge)}' for badge in badges)
        scroll = ttk.Scrollbar(self.reference_pane, orient='vertical')
        scroll.pack(side='right', fill='y')
        canvas = tk.Canvas(self.reference_pane, highlightthickness=0, yscrollcommand=scroll.set)
        canvas.pack(fill='both', expand=True)
        scroll.configure(command=canvas.yview)
        content = ttk.Frame(canvas)
        window = canvas.create_window(0, 0, window=content, anchor='nw')
        content.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(content, text=mapping, wraplength=360, padding=(12, 8, 12, 0)).pack(anchor='w')
        self.observer = ObserverPanel(self.root, self.session_dir / 'reference.csv', self.session.get().strip(), badges,
                                      container=content, on_close=self.observer_closed)
        self.set_annotating(True)

    def observer_closed(self) -> None:
        if not self.destroyed:
            self.set_annotating(False)

    def poll(self) -> None:
        if self.destroyed:
            return
        while not self.events.empty():
            kind, data = self.events.get_nowait()
            if kind in ['devices', 'scan_error']:
                self.scan_button.configure(state='normal')
                self.device_list.delete(0, 'end')
                self.devices = [address for address, _ in data.get('devices', [])]
                for address, name in data.get('devices', []):
                    self.device_list.insert('end', f'{name} [{address}]')
                if self.devices:
                    self.device_list.selection_set(0, 'end')
                self.status.set(data.get('error') or f'Found {len(self.devices)} badge(s). Select devices and start recording.')
            elif kind == 'session':
                self.raw_path = Path(data['raw_path'])
                self.saved.set(f'CSV: {self.raw_path.name} | Plots refresh independently of acquisition.')
                self.folder_button.configure(state='normal')
            elif kind == 'connected':
                self.badge_devices = data.get('devices', {})
                self.links = {badge: 'connected' for badge in data['badges']}
                self.links.update({badge: 'not connected' for badge in data.get('failed', [])})
                self.table.configure(height=len(self.links))
                failed = ', '.join(f'{badge} ({self.badge_devices.get(badge, "")})' for badge in data.get('failed', []))
                self.status.set(f'Recording {len(data["badges"])} badge(s). Not connected: {failed}.' if failed
                                else f'Recording {len(data["badges"])} badge(s). Charts update as each bulk transfer arrives.')
                try:
                    self.create_observer(data['badges'])
                except (OSError, ValueError) as error:
                    self.status.set(f'Recording; observer labels unavailable: {error}')
            elif kind == 'link':
                self.links[data['badge']] = data['state']
            elif kind == 'finished':
                self.saved.set(f'Saved {data["samples"]:,} samples to {Path(data["raw_path"]).name}')
            elif kind == 'merge_result':
                self.status.set(data['message'])
                self.merge_button.configure(state='normal')
                if not self.demo:
                    self.capture_button.configure(state='normal')
            elif kind == 'done':
                self.running = False
                if self.observer and not self.observer.closed:
                    self.observer.close()
                self.set_capture_controls(False)
                self.status.set(f'Capture failed: {data["error"]}' if data['error'] else 'Stopped. Buffered data saved; observer labels are ready to merge.')
                if self.closing:
                    self.close()
                    return
        for _ in range(500):
            try:
                batch = self.samples.get_nowait()
            except queue.Empty:
                break
            self.history.add(batch['badge'], batch['rows'])
        self.update_table()
        if self.preview_skips and self.running:
            self.saved.set(f'Preview skipped {self.preview_skips} batches. CSV recording continues independently.')
        if time.monotonic() - self.last_draw >= 1 / int(self.refresh.get()):
            self.draw()
            self.last_draw = time.monotonic()
        self.poll_timer = self.root.after(50, self.poll)

    def update_table(self) -> None:
        for badge in sorted(set(self.links) | set(self.history.rows)):
            rows = self.history.rows.get(badge)
            device, link = self.badge_devices.get(badge, ''), self.links.get(badge, '')
            if rows:
                row = rows[-1]
                values = (badge, device, link, f'{self.history.rate(badge):.1f}',
                          f'{self.history.counts[badge]:,}', self.history.gaps[badge],
                          (row['late_samples'] - self.history.first_drops[badge]) & 0xFFFFFFFF,
                          candidate_state(row), row['model_id'])
            else:
                values = (badge, device, link) + ('',) * 6
            if self.table.exists(badge):
                self.table.item(badge, values=values)
            else:
                self.table.insert('', 'end', iid=badge, values=values)

    def draw(self) -> None:
        widget = self.canvas.get_tk_widget()
        if widget.winfo_width() > 1 and widget.winfo_height() > 1:
            # Tk's Windows DPI update can leave the backing figure larger than its viewport.
            self.figure.set_size_inches(widget.winfo_width() / self.figure.dpi,
                                        widget.winfo_height() / self.figure.dpi, forward=False)
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22']
        visible = {badge: self.history.visible(badge, float(self.window.get())) for badge in self.history.rows}
        latest = max((datetime.fromisoformat(rows[-1]['Timestamp']).timestamp() for rows in visible.values() if rows), default=0)
        series = {badge: ([datetime.fromisoformat(row['Timestamp']).timestamp() - latest for row in rows], rows)
                  for badge, rows in visible.items() if rows}
        for field, axis in self.axes.items():
            for line in list(axis.lines):
                line.remove()
            for text in list(axis.texts):
                text.remove()
            has_model_score = False
            for i, (badge, (x, rows)) in enumerate(series.items()):
                y = [row.get(field, math.nan) for row in rows]
                if field == 'model_score':
                    y = [value if value >= 0 else math.nan for value in y]
                    has_model_score = has_model_score or any(math.isfinite(value) for value in y)
                elif field == 'candidate':
                    y = [value if candidate_state(row) not in ['warming up', 'unavailable'] else math.nan
                         for row, value in zip(rows, y)]
                axis.plot(x, y, color=colors[i % len(colors)], label=badge, linewidth=1.2,
                          drawstyle='steps-post' if field == 'candidate' else 'default')
            axis.set_xlim(-float(self.window.get()), 0)
            axis.relim()
            axis.autoscale_view(scalex=False)
            if field in ['candidate', 'model_score']:
                axis.set_ylim(-.1, 1.1)
            if axis.lines and field == next(iter(self.axes)):
                axis.legend(loc='upper right', fontsize=8)
            if field == 'model_score' and not has_model_score:
                axis.text(.5, .5, 'No hybrid model prediction available', transform=axis.transAxes, ha='center', fontsize=9)
        self.canvas.draw_idle()

    def open_folder(self) -> None:
        if self.session_dir and self.session_dir.exists():
            os.startfile(self.session_dir)

    def merge_labels(self) -> None:
        if not self.raw_path or not self.observer or not self.observer.closed:
            self.status.set('Stop recording and finish annotations before merging.')
            return
        target = self.session_dir / 'training.csv'
        if target.exists():
            self.status.set('training.csv already exists. Use the CLI to merge into a new filename.')
            return
        self.merge_button.configure(state='disabled')
        self.capture_button.configure(state='disabled')
        raw_path, session_dir = self.raw_path, self.session_dir
        def work() -> None:
            import pandas as pd
            temporary = session_dir / f'.training-{time.time_ns()}.csv'
            try:
                frame = merge_annotations(pd.read_csv(raw_path), pd.read_csv(session_dir / 'reference.csv'), boundary_ms=200)
                frame.to_csv(temporary, mode='x', index=False)
                temporary.rename(target)
                self.emit('merge_result', {'message': f'Wrote training.csv: {frame.activity_label.value_counts().to_dict()}'})
            except Exception as error:
                self.emit('merge_result', {'message': f'Merge failed: {error}'})
            finally:
                temporary.unlink(missing_ok=True)
        threading.Thread(target=work, daemon=True).start()

    def load_demo(self) -> None:
        self.session.set('demo_session')
        self.session_dir = self.output_root / f'demo_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")}'
        self.session_dir.mkdir(parents=True, exist_ok=True)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for badge_index in range(3):
            badge = f'badge_{badge_index + 1:02d}'
            self.badge_devices[badge] = f'demo-device-{badge_index + 1:02d}'
            rows = []
            for i in range(6001):
                t = i / 200
                speaking = (int(t // 5) + badge_index) % 3 == 0
                rows.append(dict(seq=i, device_ms=i * 5, seq_gap=0, late_samples=0, ready=True,
                                 Sound_Level=50 + (150 if speaking else 15) * (1 + .15 * math.sin(t * 13)),
                                 Acceleration=.02 + (.08 if speaking else .01) * abs(math.sin(t * 4 + badge_index)),
                                 speech_score=(2.4 if speaking else .2) + .12 * math.sin(t * 6),
                                 candidate=speaking, model_score=-1, model_id='paper-rule',
                                 Gyro_Magnitude=4 + math.sin(t), Mag_Magnitude=30, Temperature=22,
                                 Humidity=45, Pressure=100, Proximity=20,
                                 Timestamp=(start + timedelta(seconds=t)).isoformat()))
            self.history.add(badge, rows)
            self.device_list.insert('end', f'Demo badge {badge_index + 1} [demo-device-{badge_index + 1:02d}]')
        self.create_observer(list(self.history.rows))
        self.saved.set('DEMO DATA | Synthetic signals only. No live recording or trained model.')
        self.update_table()
        self.draw()

    def close(self) -> None:
        if self.running:
            self.closing = True
            self.toggle_capture()
            return
        self.destroyed = True
        if self.observer and not self.observer.closed:
            self.observer.close()
        self.root.after_cancel(self.poll_timer)
        self.root.destroy()


def launch(demo: bool = False) -> None:
    root = tk.Tk()
    SpeakerViewer(root, demo=demo)
    root.mainloop()
