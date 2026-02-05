#!/usr/bin/env python3
"""
Auto Peak-Based Badge Activity Labeler
=====================================

Binary speech activity labeling using:
- Threshold-based speech presence detection
- Cross-badge peak sound comparison
- Short time-bin synchronization

Labels:
- active
- not_active

Output:
processed_data/auto_label/

Author: Auto Labeler
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, simpledialog


class AutoLabeler:
    def __init__(self):
        # ----------------------------
        # Parameters (tunable)
        # ----------------------------
        self.short_window_sec = 3
        self.long_window_sec = 60
        self.persistence_samples = 10

        self.time_bin_ms = 500           # peak comparison resolution
        self.peak_margin_ratio = 1.10    # must be 10% louder than others

        # ----------------------------
        # Output directory
        # ----------------------------
        self.output_dir = Path("processed_data") / "auto_label"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.data = None

    # --------------------------------------------------
    # File selection
    # --------------------------------------------------
    def select_file(self):
        base_dir = Path("Data Collection & Visualization") / "badge_data"
        if not base_dir.exists():
            base_dir = Path("badge_data")

        root = tk.Tk()
        root.withdraw()

        file_path = filedialog.askopenfilename(
            title="Select Badge Data CSV",
            initialdir=base_dir,
            filetypes=[("CSV files", "*.csv")]
        )

        root.destroy()
        return Path(file_path) if file_path else None

    # --------------------------------------------------
    # Load data
    # --------------------------------------------------
    def load_data(self, file_path):
        print(f"Loading data from: {file_path}")
        df = pd.read_csv(file_path)

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df.sort_values(["Timestamp", "Badge_Name"])

        self.data = df
        print(f"Loaded {len(df)} rows")
        print(f"Badges detected: {df['Badge_Name'].unique()}")

    # --------------------------------------------------
    # Threshold speech presence (reuse logic)
    # --------------------------------------------------
    def compute_speech_presence(self, df):
        df = df.copy()
        df = df.set_index("Timestamp")

        short_w = f"{self.short_window_sec}s"
        long_w = f"{self.long_window_sec}s"

        df["sound_mean_short"] = (
            df["Sound_Level"]
            .rolling(short_w, min_periods=1)
            .mean()
        )

        sound_threshold = (
            df
            .rolling(long_w, min_periods=10)
            ["Sound_Level"]
            .quantile(0.75)
        )

        df["speech_present"] = df["sound_mean_short"] > sound_threshold
        return df.reset_index()

    # --------------------------------------------------
    # Peak comparison logic
    # --------------------------------------------------
    def apply_peak_labeling(self, df):
        df = df.copy()

        # Create time bins
        df["time_bin"] = df["Timestamp"].dt.floor(f"{self.time_bin_ms}ms")

        df["auto_activity_label"] = "not_active"

        for _, group in df.groupby("time_bin"):
            active_candidates = group[group["speech_present"]]

            if active_candidates.empty:
                continue

            max_sound = active_candidates["Sound_Level"].max()

            # Require dominance margin
            dominant = active_candidates[
                active_candidates["Sound_Level"] >= max_sound / self.peak_margin_ratio
            ]

            if dominant.empty:
                continue

            # Pick the loudest badge
            winner_idx = dominant["Sound_Level"].idxmax()
            df.loc[winner_idx, "auto_activity_label"] = "active"

        return df

    # --------------------------------------------------
    # Main process
    # --------------------------------------------------
    def process(self):
        file_path = self.select_file()
        if not file_path:
            print("No file selected. Exiting.")
            return

        self.load_data(file_path)

        df = self.compute_speech_presence(self.data)
        df = self.apply_peak_labeling(df)

        # Prompt for output name
        root = tk.Tk()
        root.withdraw()
        filename = simpledialog.askstring(
            "Output File Name",
            "Enter output file name (without .csv):"
        )
        root.destroy()

        if not filename:
            filename = f"auto_labeled_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        output_path = self.output_dir / f"{filename}.csv"
        df.to_csv(output_path, index=False)

        print("\n=== Auto Labeling Complete ===")
        print(f"Output saved to: {output_path}")
        print("Label counts:")
        print(df["auto_activity_label"].value_counts())


# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    labeler = AutoLabeler()
    labeler.process()