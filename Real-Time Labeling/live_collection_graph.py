#!/usr/bin/env python3
"""
Live Collection + Real-Time Speaker Detection
==============================================

All-in-one tool that:
  1. Scans for and connects to BLE badges
  2. Collects data in real time (saved to CSV)
  3. Runs the auto-labeler on the streaming data
  4. Shows a live graph with the ACTIVE SPEAKER displayed prominently

Usage:
    python live_collection_graph.py

Requires:
    pip install bleak matplotlib numpy
"""

import asyncio
import csv
import os
import sys
import threading
import datetime
from pathlib import Path
from collections import deque

import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import tkinter as tk
from tkinter import ttk, simpledialog

from realtime_labeler import RealtimeLabeler

# ============================================================
# BLE Configuration  (mirrors data_collection.py)
# ============================================================
SERVICE_UUID = "0000012f-0000-1000-8000-00805f9b34fb"
DATA_CHAR_UUID = "0000345f-0000-1000-8000-00805f9b34fb"

BADGE_ADDRESS = {
    "99:0F:9A:A1:83:96": "Badge01",
    "F9:5C:35:CF:D8:53": "Badge09",
    "E9:7D:DA:71:28:2C": "Badge05",
    "F9:54:91:BD:45:86": "Badge10",
    "AA:F4:C8:5D:45:ED": "Badge04",
    "71:F2:53:B7:47:FA": "Badge08",
    "01:1B:DE:95:4E:D9": "Badge03",
    "08:6B:88:33:3E:44": "Badge07",
    "D9:6D:90:A1:2B:3A": "Badge06",
    "3B:DE:58:7D:EF:BA": "HM Badge No.01",
}

# Consistent badge colors
BADGE_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]

# ============================================================
# Global state
# ============================================================
badge_person_mapping = {}      # badge_name -> person name
badge_color_map = {}           # badge_name -> hex color
data_lock = threading.Lock()
# Rolling buffers for the graph (last N points per badge)
GRAPH_POINTS = 200
graph_buffers = {}             # badge_name -> deque of {timestamp, sound, accel}
csv_filename = None
stop_collection = threading.Event()
labeler = RealtimeLabeler()

# ============================================================
# CSV helpers
# ============================================================

def init_csv():
    global csv_filename
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_dir = Path("badge_data")
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_filename = csv_dir / f"AllBadges_data_{ts}.csv"
    with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Badge_Name', 'Person_Name',
                         'Sound_Level', 'RSSI', 'Acceleration', 'GR',
                         'Raw_Data', 'RT_Label'])
    print(f"📝 CSV: {csv_filename}")


def save_row(timestamp, badge_name, sound, rssi, acceleration, gr, raw_data, label):
    if csv_filename is None:
        return
    person = badge_person_mapping.get(badge_name, "")
    try:
        with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, badge_name, person,
                             sound, rssi, acceleration,
                             gr if gr is not None else "",
                             raw_data, label])
    except Exception as e:
        print(f"❌ CSV write error: {e}")


def assign_color(badge_name):
    if badge_name not in badge_color_map:
        idx = len(badge_color_map) % len(BADGE_COLORS)
        badge_color_map[badge_name] = BADGE_COLORS[idx]
    return badge_color_map[badge_name]


# ============================================================
# BLE notification handler factory
# ============================================================

def make_handler(badge_name):
    """Create a BLE notification callback for *badge_name*."""
    sample_count = [0]   # mutable counter

    def handler(sender, data):
        if stop_collection.is_set():
            return
        try:
            decoded = data.decode('utf-8')
            ts_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            ts_dt = datetime.datetime.now()

            values = [v.strip() for v in decoded.split(',')]
            if len(values) >= 3:
                sound = float(values[0])
                rssi = float(values[1])
                accel = float(values[2])
                gr = values[3] if len(values) >= 4 else None
            else:
                return

            # Feed the real-time labeler
            labeler.add_sample(ts_dt, badge_name, sound, accel)
            label = labeler.get_all_labels().get(badge_name, "not_active")

            # Save to CSV (includes the real-time label)
            save_row(ts_str, badge_name, sound, rssi, accel, gr, decoded, label)

            # Update graph buffer
            with data_lock:
                if badge_name not in graph_buffers:
                    graph_buffers[badge_name] = deque(maxlen=GRAPH_POINTS)
                graph_buffers[badge_name].append({
                    'timestamp': ts_dt,
                    'sound': sound,
                    'accel': accel,
                })

            sample_count[0] += 1
            if sample_count[0] % 20 == 0:
                print(f"  [{ts_str}] {badge_name}: snd={sound:.0f}  acc={accel:.2f}  label={label}")

        except Exception as e:
            print(f"⚠️ {badge_name} handler error: {e}")

    return handler


# ============================================================
# BLE scanning + connection (async)
# ============================================================

async def ble_main():
    """Scan, connect, and collect — runs in its own thread."""
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("❌ bleak not installed. Run: pip install bleak")
        return

    print("\n🔍 Scanning for badges (5 s)…")
    devices = await BleakScanner.discover(timeout=5.0)
    detected = [d for d in devices if d.address in BADGE_ADDRESS]

    if not detected:
        print("⚠️  No badges found. The graph will run in demo / CSV-replay mode.")
        return

    badge_names = [BADGE_ADDRESS[d.address] for d in detected]
    print(f"✅ Found {len(detected)} badge(s): {badge_names}")

    # Collect person names (console prompts — runs in BLE thread)
    print("\n👤 PERSON NAME ENTRY")
    print("=" * 50)
    for bname in badge_names:
        person = input(f"  Name for {bname} (ENTER to skip): ").strip()
        badge_person_mapping[bname] = person
        if person:
            print(f"    ✓ {bname} → {person}")
    print("=" * 50, "\n")

    init_csv()

    # Connect all badges concurrently
    async def connect_badge(device):
        address = device.address
        bname = BADGE_ADDRESS[address]
        client = BleakClient(address)
        try:
            await client.connect(timeout=10)
            if not client.is_connected:
                print(f"❌ Could not connect to {bname}")
                return
            print(f"✅ Connected to {bname}")

            handler = make_handler(bname)

            # Find a notify-capable characteristic
            subscribed = False
            for svc in client.services:
                for char in svc.characteristics:
                    if "notify" in char.properties or "indicate" in char.properties:
                        try:
                            await client.start_notify(char.uuid, handler)
                            print(f"   📡 Subscribed to {char.uuid} on {bname}")
                            subscribed = True
                            break
                        except Exception:
                            pass
                if subscribed:
                    break

            if not subscribed:
                try:
                    await client.start_notify(DATA_CHAR_UUID, handler)
                    print(f"   📡 Subscribed to default char on {bname}")
                except Exception as e:
                    print(f"   ❌ No characteristic found for {bname}: {e}")
                    return

            # Hold connection open until stop
            while not stop_collection.is_set():
                await asyncio.sleep(0.5)
                if not client.is_connected:
                    print(f"⚠️  Lost connection to {bname}")
                    break

            await client.disconnect()
            print(f"🔌 Disconnected from {bname}")

        except Exception as e:
            print(f"❌ {bname} error: {e}")

    await asyncio.gather(*(connect_badge(d) for d in detected))


def run_ble_loop():
    """Entry point for the BLE thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ble_main())


# ============================================================
# Tkinter + Matplotlib GUI
# ============================================================

class LiveSpeakerApp:
    """Main GUI window: live graph + active speaker panel."""

    REFRESH_MS = 500          # graph update interval

    def __init__(self, root):
        self.root = root
        root.title("Real-Time Badge Collection + Auto-Labeling")
        root.state('zoomed')
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- Layout: left info panel | right graph ----
        main = tk.Frame(root)
        main.pack(fill='both', expand=True)

        # Left panel — active speaker + stats
        left = tk.Frame(main, width=320, bg='#1e1e2f', relief='ridge', bd=3)
        left.pack(side='left', fill='y', padx=(6, 0), pady=6)
        left.pack_propagate(False)

        tk.Label(left, text="ACTIVE SPEAKER",
                 font=('Segoe UI', 18, 'bold'), fg='white',
                 bg='#1e1e2f').pack(pady=(18, 4))

        self.speaker_label = tk.Label(left, text="—",
                                       font=('Segoe UI', 36, 'bold'),
                                       fg='#00ff88', bg='#1e1e2f')
        self.speaker_label.pack(pady=(0, 10))

        self.speaker_badge_label = tk.Label(left, text="",
                                             font=('Segoe UI', 14),
                                             fg='#aaaaaa', bg='#1e1e2f')
        self.speaker_badge_label.pack()

        ttk.Separator(left, orient='horizontal').pack(fill='x', padx=12, pady=14)

        tk.Label(left, text="ALL BADGES",
                 font=('Segoe UI', 14, 'bold'), fg='white',
                 bg='#1e1e2f').pack(pady=(0, 6))

        # Scrollable badge list
        self.badge_list_frame = tk.Frame(left, bg='#1e1e2f')
        self.badge_list_frame.pack(fill='both', expand=True, padx=8)

        self.badge_widgets = {}   # badge_name -> dict of tk widgets

        # Bottom stats
        ttk.Separator(left, orient='horizontal').pack(fill='x', padx=12, pady=8)
        self.stats_label = tk.Label(left, text="Samples: 0",
                                     font=('Consolas', 11), fg='#cccccc',
                                     bg='#1e1e2f', anchor='w')
        self.stats_label.pack(fill='x', padx=12, pady=(0, 4))

        self.csv_label = tk.Label(left, text="CSV: (waiting)",
                                   font=('Consolas', 9), fg='#888888',
                                   bg='#1e1e2f', anchor='w', wraplength=300)
        self.csv_label.pack(fill='x', padx=12, pady=(0, 10))

        # Right panel — matplotlib graph
        right = tk.Frame(main)
        right.pack(side='right', fill='both', expand=True, padx=6, pady=6)

        self.fig, self.axs = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        self.fig.patch.set_facecolor('#fafafa')
        self.fig.subplots_adjust(hspace=0.30, top=0.93, bottom=0.10)

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

        # Start the periodic refresh
        self._refresh()

    # ----------------------------------------------------------
    def _refresh(self):
        """Called every REFRESH_MS to repaint the graph + info."""
        self._update_graph()
        self._update_speaker_panel()
        self.root.after(self.REFRESH_MS, self._refresh)

    # ----------------------------------------------------------
    def _update_graph(self):
        ax_snd, ax_acc = self.axs

        ax_snd.clear()
        ax_acc.clear()

        with data_lock:
            snapshot = {b: list(q) for b, q in graph_buffers.items()}

        if not snapshot:
            ax_snd.set_title("Waiting for data…", fontsize=12)
            self.canvas.draw_idle()
            return

        labels_now = labeler.get_all_labels()
        active_speaker = labeler.get_active_speaker()

        for badge, samples in snapshot.items():
            color = assign_color(badge)
            sounds = [s['sound'] for s in samples]
            accels = [s['accel'] for s in samples]
            x = list(range(len(sounds)))

            lw = 2.5 if badge == active_speaker else 1.2
            alpha = 1.0 if badge == active_speaker else 0.5

            person = badge_person_mapping.get(badge, "")
            display = f"{badge} ({person})" if person else badge

            ax_snd.plot(x, sounds, color=color, label=display,
                        linewidth=lw, alpha=alpha)
            ax_acc.plot(x, accels, color=color, label=display,
                        linewidth=lw, alpha=alpha)

            # Shade background when this badge is the active speaker
            if badge == active_speaker and len(x) > 1:
                ax_snd.axvspan(x[-min(10, len(x))], x[-1],
                               color=color, alpha=0.10)
                ax_acc.axvspan(x[-min(10, len(x))], x[-1],
                               color=color, alpha=0.10)

        ax_snd.set_ylabel('Sound Level', fontweight='bold')
        ax_snd.set_title('Live Sound Level', fontweight='bold', fontsize=12)
        ax_snd.legend(loc='upper left', fontsize=8, ncol=2, framealpha=0.8)
        ax_snd.grid(True, alpha=0.25)
        ax_snd.set_facecolor('#f8f9fa')

        ax_acc.set_ylabel('Acceleration', fontweight='bold')
        ax_acc.set_title('Live Acceleration', fontweight='bold', fontsize=12)
        ax_acc.set_xlabel('Recent samples', fontweight='bold')
        ax_acc.legend(loc='upper left', fontsize=8, ncol=2, framealpha=0.8)
        ax_acc.grid(True, alpha=0.25)
        ax_acc.set_facecolor('#f8f9fa')

        self.canvas.draw_idle()

    # ----------------------------------------------------------
    def _update_speaker_panel(self):
        """Refresh the left-side active speaker + badge list."""
        active = labeler.get_active_speaker()
        scores = labeler.get_speaker_scores()
        all_labels = labeler.get_all_labels()

        # Active speaker display
        if active:
            person = badge_person_mapping.get(active, "")
            display_name = person if person else active
            self.speaker_label.config(text=display_name, fg='#00ff88')
            self.speaker_badge_label.config(text=active if person else "")
        else:
            self.speaker_label.config(text="—", fg='#555555')
            self.speaker_badge_label.config(text="")

        # Per-badge rows
        all_badges = sorted(labeler.get_known_badges())
        for badge in all_badges:
            if badge not in self.badge_widgets:
                self._create_badge_row(badge)

            w = self.badge_widgets[badge]
            is_active = (badge == active)
            score = scores.get(badge, 0)
            person = badge_person_mapping.get(badge, "")
            color = assign_color(badge)

            name_text = f"{badge}"
            if person:
                name_text += f"  ({person})"

            w['name'].config(text=name_text)
            w['score'].config(text=f"score: {score:.2f}")

            if is_active:
                w['frame'].config(bg=color, relief='raised')
                w['status'].config(text="● SPEAKING", fg='#00ff88',
                                    bg=color, font=('Segoe UI', 11, 'bold'))
                w['name'].config(bg=color, fg='white')
                w['score'].config(bg=color, fg='white')
            else:
                w['frame'].config(bg='#2a2a3d', relief='flat')
                w['status'].config(text="○ silent", fg='#666666',
                                    bg='#2a2a3d', font=('Segoe UI', 11))
                w['name'].config(bg='#2a2a3d', fg='#cccccc')
                w['score'].config(bg='#2a2a3d', fg='#888888')

        # Stats
        total_samples = sum(len(q) for q in graph_buffers.values())
        self.stats_label.config(text=f"Samples in view: {total_samples}")
        if csv_filename:
            self.csv_label.config(text=f"CSV: {csv_filename}")

    def _create_badge_row(self, badge_name):
        color = assign_color(badge_name)
        frame = tk.Frame(self.badge_list_frame, bg='#2a2a3d',
                         relief='flat', bd=2, padx=6, pady=4)
        frame.pack(fill='x', pady=3)

        name_lbl = tk.Label(frame, text=badge_name,
                            font=('Segoe UI', 12, 'bold'),
                            fg='#cccccc', bg='#2a2a3d', anchor='w')
        name_lbl.pack(fill='x')

        bottom = tk.Frame(frame, bg='#2a2a3d')
        bottom.pack(fill='x')

        status_lbl = tk.Label(bottom, text="○ silent",
                              font=('Segoe UI', 11), fg='#666666',
                              bg='#2a2a3d', anchor='w')
        status_lbl.pack(side='left')

        score_lbl = tk.Label(bottom, text="score: 0.00",
                             font=('Consolas', 10), fg='#888888',
                             bg='#2a2a3d', anchor='e')
        score_lbl.pack(side='right')

        self.badge_widgets[badge_name] = {
            'frame': frame,
            'name': name_lbl,
            'status': status_lbl,
            'score': score_lbl,
        }

    # ----------------------------------------------------------
    def _on_close(self):
        stop_collection.set()
        try:
            plt.close('all')
        except Exception:
            pass
        self.root.quit()
        self.root.destroy()


# ============================================================
# Entry point
# ============================================================

def main():
    print("=" * 55)
    print("  Real-Time Badge Collection + Speaker Detection")
    print("=" * 55)

    # Start BLE collection in a background thread
    ble_thread = threading.Thread(target=run_ble_loop, daemon=True)
    ble_thread.start()

    # Launch GUI on the main thread
    root = tk.Tk()
    app = LiveSpeakerApp(root)
    root.mainloop()

    stop_collection.set()
    print("\n✅ Done. Data saved to:", csv_filename)


if __name__ == '__main__':
    main()
