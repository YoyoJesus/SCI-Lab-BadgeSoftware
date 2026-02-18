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
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, simpledialog


class AutoLabeler:
    def __init__(self):
        # ----------------------------
        # Parameters (tunable)
        # ----------------------------
        self.short_window_sec = 1        # fast response to speech onsets (was 3)
        self.long_window_sec = 60

        self.time_bin_ms = 500           # peak comparison resolution
        self.speech_threshold_quantile = 0.45  # lower = more sensitive
        self.min_speech_score = 0.3      # winner must be >= N IQR-widths above own quiet floor
        self.high_score_fallback = 2.0   # bypass speech_present if speech_score >= this
        self.vote_window_bins = 5        # sliding window size for majority vote (bins)
        self.min_vote_ratio = 0.35       # fraction of window bins winner must win

        # Acceleration contribution to the combined speech score.
        # The speaker's badge vibrates physically when they talk; other badges
        # only receive sound through air (much lower acceleration).
        # Set to 0.0 to disable and use sound only.
        self.accel_weight = 1.2          # relative weight vs norm_sound
        self.accel_clip = 2.5            # cap norm_accel to avoid walk/movement dominating

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

        # Check if Person_Name column exists, if not add it
        if "Person_Name" not in df.columns:
            print("\n⚠️ Person_Name column not found in data")
            df["Person_Name"] = ""
            self.data = df

    # --------------------------------------------------
    # Threshold speech presence — computed per badge
    # --------------------------------------------------
    def compute_speech_presence(self, df):
        short_w = f"{self.short_window_sec}s"
        long_w = f"{self.long_window_sec}s"

        results = []
        for _, badge_df in df.groupby("Badge_Name"):
            badge_df = badge_df.copy().set_index("Timestamp").sort_index()

            badge_df["sound_mean_short"] = (
                badge_df["Sound_Level"]
                .rolling(short_w, min_periods=1)
                .mean()
            )

            sound_threshold = (
                badge_df["Sound_Level"]
                .rolling(long_w, min_periods=10)
                .quantile(self.speech_threshold_quantile)
            )

            badge_df["speech_present"] = badge_df["sound_mean_short"] > sound_threshold
            results.append(badge_df.reset_index())

        return (
            pd.concat(results)
            .sort_values(["Timestamp", "Badge_Name"])
            .reset_index(drop=True)
        )

    # --------------------------------------------------
    # Collect person names if missing
    # --------------------------------------------------
    def collect_person_names_if_needed(self):
        """Check if person names are missing and collect them"""
        df = self.data

        # Check which badges are missing names
        badges_without_names = []
        for badge_name in df["Badge_Name"].unique():
            badge_data = df[df["Badge_Name"] == badge_name]
            # Check if all Person_Name values are empty/null
            if badge_data["Person_Name"].isna().all() or (badge_data["Person_Name"].str.strip() == "").all():
                badges_without_names.append(badge_name)

        if not badges_without_names:
            print("✓ All badges have person names assigned")
            return

        print("\n" + "="*50)
        print("👤 PERSON NAME ENTRY")
        print("="*50)
        print(f"The following badges don't have person names assigned:")
        for badge in badges_without_names:
            print(f"  - {badge}")
        print("\nWould you like to assign names now?")

        root = tk.Tk()
        root.withdraw()
        response = simpledialog.askstring(
            "Assign Names",
            "Enter 'yes' to assign names, or 'no' to skip:"
        )
        root.destroy()

        if response and response.lower() in ['yes', 'y']:
            badge_person_mapping = {}

            for badge_name in badges_without_names:
                root = tk.Tk()
                root.withdraw()
                person_name = simpledialog.askstring(
                    "Person Name",
                    f"Enter name for {badge_name}:"
                )
                root.destroy()

                if person_name and person_name.strip():
                    badge_person_mapping[badge_name] = person_name.strip()
                    print(f"✓ {badge_name} → {person_name.strip()}")
                else:
                    badge_person_mapping[badge_name] = ""
                    print(f"✓ {badge_name} → (no name)")

            # Apply the names to the dataframe
            for badge_name, person_name in badge_person_mapping.items():
                self.data.loc[self.data["Badge_Name"] == badge_name, "Person_Name"] = person_name

            print("="*50)
            print("Name assignment complete!")
            print("="*50 + "\n")
        else:
            print("Skipping name assignment\n")

    # --------------------------------------------------
    # Peak comparison logic
    # --------------------------------------------------
    def apply_peak_labeling(self, df):
        df = df.copy()
        df["time_bin"] = df["Timestamp"].dt.floor(f"{self.time_bin_ms}ms")
        df["auto_activity_label"] = "not_active"

        # Per-badge IQR normalization for sound and acceleration.
        #   floor  = rolling 25th percentile (quiet baseline, unaffected by speech)
        #   spread = rolling IQR (75th - 25th), robust scale estimate
        # Result: how many IQR-widths above the quiet floor is this sample?
        #
        # Acceleration is included because the speaker's badge physically
        # vibrates when they talk; bystander badges only receive sound through
        # air and show no matching acceleration spike.
        long_w = f"{self.long_window_sec}s"
        has_accel = "Acceleration" in df.columns
        norm_scores = []
        for _, badge_df in df.groupby("Badge_Name"):
            badge_df = badge_df.set_index("Timestamp").sort_index()

            def iqr_norm(series):
                roll = series.rolling(long_w, min_periods=10)
                floor  = roll.quantile(0.25).fillna(series.quantile(0.25))
                spread = (roll.quantile(0.75) - roll.quantile(0.25)).fillna(
                    series.quantile(0.75) - series.quantile(0.25)
                ).clip(lower=1)
                return (series - floor) / spread

            badge_df["norm_sound"] = iqr_norm(badge_df["Sound_Level"])

            if has_accel and self.accel_weight > 0:
                badge_df["norm_accel"] = iqr_norm(badge_df["Acceleration"])
                badge_df["speech_score"] = (
                    badge_df["norm_sound"]
                    + self.accel_weight * badge_df["norm_accel"].clip(lower=0, upper=self.accel_clip)
                )
            else:
                badge_df["speech_score"] = badge_df["norm_sound"]

            norm_scores.append(badge_df.reset_index())

        df = (
            pd.concat(norm_scores)
            .sort_values(["Timestamp", "Badge_Name"])
            .reset_index(drop=True)
        )
        df["time_bin"] = df["Timestamp"].dt.floor(f"{self.time_bin_ms}ms")

        # Pass 1 — per-bin raw winners
        # Only consider speech-present candidates that clear the speech score floor.
        bins_sorted = sorted(df["time_bin"].unique())
        raw_winners = {}
        for bin_t in bins_sorted:
            group = df[df["time_bin"] == bin_t]
            candidates = group[
                (group["speech_present"] | (group["speech_score"] >= self.high_score_fallback)) &
                (group["speech_score"] >= self.min_speech_score)
            ]
            if candidates.empty:
                continue
            raw_winners[bin_t] = candidates.loc[
                candidates["speech_score"].idxmax(), "Badge_Name"
            ]

        # Pass 2 — sliding window majority vote
        # A badge must win ≥ min_vote_ratio of the surrounding bins before its
        # rows in the centre bin are marked active.  This prevents a single
        # noise spike from winning a bin and over-labelling an entire bin.
        half = self.vote_window_bins // 2
        min_votes = max(1, round(self.vote_window_bins * self.min_vote_ratio))

        for i, bin_t in enumerate(bins_sorted):
            window = bins_sorted[max(0, i - half): i + half + 1]
            votes: dict[str, int] = {}
            for b in window:
                if b in raw_winners:
                    votes[raw_winners[b]] = votes.get(raw_winners[b], 0) + 1

            if not votes:
                continue
            top_badge, top_votes = max(votes.items(), key=lambda kv: kv[1])
            if top_votes >= min_votes:
                mask = (df["time_bin"] == bin_t) & (df["Badge_Name"] == top_badge)
                df.loc[mask, "auto_activity_label"] = "active"

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

        # Check and collect person names if needed
        self.collect_person_names_if_needed()

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