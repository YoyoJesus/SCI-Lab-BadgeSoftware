#!/usr/bin/env python3
"""
Demo / Test Mode
================

Replays an existing CSV file through the real-time labeler + graph
so you can test and tune without live badges connected.

Usage:
    python demo_replay.py
    
    (then select a CSV file)
"""

import csv
import datetime
import threading
import time
from pathlib import Path
from collections import deque

import tkinter as tk
from tkinter import filedialog

# Reuse the same GUI + labeler
import sys
sys.path.insert(0, str(Path(__file__).parent))

from realtime_labeler import RealtimeLabeler
from live_collection_graph import (
    LiveSpeakerApp, labeler, graph_buffers, data_lock,
    badge_person_mapping, stop_collection, GRAPH_POINTS,
    assign_color, csv_filename
)


def select_csv():
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Select Badge Data CSV to Replay",
        filetypes=[("CSV files", "*.csv")],
        initialdir=str(Path(__file__).parent.parent / "badge_data")
    )
    root.destroy()
    return Path(path) if path else None


def replay_csv(file_path, speed=1.0):
    """Read a CSV and feed rows into the labeler at (accelerated) real time."""
    print(f"📂 Replaying: {file_path}")
    print(f"   Speed: {speed}x")

    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                try:
                    ts = datetime.datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    continue

            badge = row.get('Badge_Name', 'Unknown')
            person = row.get('Person_Name', '')
            sound = float(row.get('Sound_Level', 0))
            accel = float(row.get('Acceleration', 0))

            if person and badge not in badge_person_mapping:
                badge_person_mapping[badge] = person

            rows.append((ts, badge, sound, accel))

    if not rows:
        print("❌ No valid rows found")
        return

    rows.sort(key=lambda r: r[0])
    t0 = rows[0][0]
    print(f"   Rows: {len(rows)}, Badges: {set(r[1] for r in rows)}")
    print(f"   Duration: {rows[-1][0] - rows[0][0]}")

    for i, (ts, badge, sound, accel) in enumerate(rows):
        if stop_collection.is_set():
            break

        # Feed into labeler
        labeler.add_sample(ts, badge, sound, accel)

        # Update graph buffer
        with data_lock:
            if badge not in graph_buffers:
                graph_buffers[badge] = deque(maxlen=GRAPH_POINTS)
            graph_buffers[badge].append({
                'timestamp': ts,
                'sound': sound,
                'accel': accel,
            })

        # Simulate real-time pacing
        if i < len(rows) - 1:
            dt = (rows[i + 1][0] - ts).total_seconds() / speed
            if dt > 0:
                time.sleep(min(dt, 0.1))  # cap to avoid long pauses

    print("✅ Replay complete")


def main():
    file_path = select_csv()
    if not file_path:
        print("No file selected.")
        return

    # Ask replay speed
    root_ask = tk.Tk()
    root_ask.withdraw()
    from tkinter import simpledialog
    speed = simpledialog.askfloat(
        "Replay Speed",
        "Replay speed multiplier:\n  1.0 = real time\n  5.0 = 5x faster\n  20.0 = 20x faster",
        initialvalue=10.0, minvalue=0.1, maxvalue=100.0
    )
    root_ask.destroy()
    if speed is None:
        speed = 10.0

    # Start replay in background thread
    replay_thread = threading.Thread(
        target=replay_csv, args=(file_path, speed), daemon=True
    )
    replay_thread.start()

    # Launch the same GUI
    root = tk.Tk()
    app = LiveSpeakerApp(root)
    root.mainloop()
    stop_collection.set()


if __name__ == '__main__':
    main()
