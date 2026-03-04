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
        self.min_speech_score = 0.75     # winner must be >= N IQR-widths above own quiet floor
        self.high_score_fallback = 3.5   # bypass speech_present if speech_score >= this
        self.vote_window_bins = 5        # sliding window size for majority vote (bins)
        self.min_vote_ratio = 0.55       # fraction of window bins winner must win

        # Acceleration contribution to the combined speech score.
        # The speaker's badge vibrates physically when they talk; other badges
        # only receive sound through air (much lower acceleration).
        # Set to 0.0 to disable and use sound only.
        self.accel_weight = 1.2          # relative weight vs norm_sound
        self.accel_clip = 2.5            # cap norm_accel to avoid walk/movement dominating
        
        # ----------------------------
        # Post-processing parameters
        # ----------------------------
        self.min_active_duration_sec = 2.0    # filter out active periods shorter than this
        self.min_inactive_duration_sec = 0.5  # filter out inactive gaps shorter than this
        self.merge_gap_sec = 1.5              # merge active periods separated by less than this
        self.enable_post_processing = True     # enable smoothing and filtering

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
    # Speaker-level label: who speaks in each time bin
    # --------------------------------------------------
    def add_speaker_column(self, df):
        """Add auto_speaker column: which badge is speaking per time bin, or 'no_speaker'."""
        df = df.copy()
        if "time_bin" not in df.columns:
            df["time_bin"] = df["Timestamp"].dt.floor(f"{self.time_bin_ms}ms")

        bin_speakers = {}
        for time_bin, group in df.groupby("time_bin"):
            active = group[group["auto_activity_label"] == "active"]["Badge_Name"].unique().tolist()
            if len(active) == 0:
                bin_speakers[time_bin] = "no_speaker"
            elif len(active) == 1:
                bin_speakers[time_bin] = active[0]
            else:
                # Multiple active in a bin — pick highest speech_score if available
                active_group = group[group["auto_activity_label"] == "active"]
                if "speech_score" in active_group.columns:
                    bin_speakers[time_bin] = active_group.loc[
                        active_group["speech_score"].idxmax(), "Badge_Name"
                    ]
                else:
                    bin_speakers[time_bin] = sorted(active)[0]

        df["auto_speaker"] = df["time_bin"].map(bin_speakers)
        return df

    # --------------------------------------------------
    # Post-processing: merge and filter labels
    # --------------------------------------------------
    def post_process_labels(self, df):
        """Apply smoothing and filtering to reduce fragmentation"""
        if not self.enable_post_processing:
            return df
        
        print("\nApplying post-processing...")
        results = []
        
        for badge_name, badge_df in df.groupby("Badge_Name"):
            badge_df = badge_df.sort_values("Timestamp").copy()
            
            # Step 1: Identify contiguous active/inactive runs
            badge_df['label_changed'] = (badge_df['auto_activity_label'] != 
                                         badge_df['auto_activity_label'].shift()).astype(int)
            badge_df['run_id'] = badge_df['label_changed'].cumsum()
            
            # Step 2: Calculate duration of each run
            runs = []
            for run_id, run_df in badge_df.groupby('run_id'):
                start_time = run_df['Timestamp'].iloc[0]
                end_time = run_df['Timestamp'].iloc[-1]
                duration = (end_time - start_time).total_seconds()
                label = run_df['auto_activity_label'].iloc[0]
                runs.append({
                    'run_id': run_id,
                    'start': start_time,
                    'end': end_time,
                    'duration': duration,
                    'label': label,
                    'indices': run_df.index.tolist()
                })
            
            # Step 3: Filter out short active periods
            for i, run in enumerate(runs):
                if run['label'] == 'active' and run['duration'] < self.min_active_duration_sec:
                    # Mark this run as not_active
                    badge_df.loc[run['indices'], 'auto_activity_label'] = 'not_active'
            
            # Step 4: Merge active periods separated by short gaps
            i = 0
            while i < len(runs) - 2:
                current = runs[i]
                gap = runs[i + 1]
                next_run = runs[i + 2]
                
                if (current['label'] == 'active' and 
                    gap['label'] == 'not_active' and 
                    next_run['label'] == 'active' and
                    gap['duration'] < self.merge_gap_sec):
                    # Fill the gap - mark it as active
                    badge_df.loc[gap['indices'], 'auto_activity_label'] = 'active'
                    i += 3  # Skip past the merged section
                else:
                    i += 1
            
            # Step 5: Fill short inactive gaps between active periods
            badge_df['label_changed'] = (badge_df['auto_activity_label'] != 
                                         badge_df['auto_activity_label'].shift()).astype(int)
            badge_df['run_id'] = badge_df['label_changed'].cumsum()
            
            for run_id, run_df in badge_df.groupby('run_id'):
                if run_df['auto_activity_label'].iloc[0] == 'not_active':
                    duration = (run_df['Timestamp'].iloc[-1] - run_df['Timestamp'].iloc[0]).total_seconds()
                    if duration < self.min_inactive_duration_sec:
                        # Check if surrounded by active periods
                        prev_idx = run_df.index[0] - 1
                        next_idx = run_df.index[-1] + 1
                        if (prev_idx in badge_df.index and next_idx in badge_df.index):
                            if (badge_df.loc[prev_idx, 'auto_activity_label'] == 'active' and
                                badge_df.loc[next_idx, 'auto_activity_label'] == 'active'):
                                badge_df.loc[run_df.index, 'auto_activity_label'] = 'active'
            
            # Clean up temporary columns
            badge_df = badge_df.drop(columns=['label_changed', 'run_id'], errors='ignore')
            results.append(badge_df)
        
        result_df = pd.concat(results).sort_values(['Timestamp', 'Badge_Name']).reset_index(drop=True)
        print("Post-processing complete")
        return result_df
    
    # --------------------------------------------------
    # Ask user for parameter tuning
    # --------------------------------------------------
    def get_user_parameters(self):
        """Prompt user to adjust key parameters"""
        root = tk.Tk()
        root.withdraw()
        
        # Ask if user wants to customize parameters
        customize = simpledialog.askstring(
            "Parameter Configuration",
            "Use default parameters? (yes/no)\n\nDefault settings:\n"
            f"  - Speech threshold quantile: {self.speech_threshold_quantile}\n"
            f"  - Min speech score: {self.min_speech_score}  (raised from 0.3)\n"
            f"  - High score fallback: {self.high_score_fallback}  (raised from 2.0)\n"
            f"  - Min vote ratio: {self.min_vote_ratio}  (raised from 0.35)\n"
            f"  - Acceleration weight: {self.accel_weight}\n"
            f"  - Min active duration: {self.min_active_duration_sec}s  (raised from 1.0s)\n"
            f"  - Merge gap: {self.merge_gap_sec}s"
        )
        
        if customize and customize.lower() in ['no', 'n']:
            # Speech threshold quantile
            val = simpledialog.askfloat(
                "Speech Threshold",
                f"Speech threshold quantile (0.0-1.0)\nLower = more sensitive\nCurrent: {self.speech_threshold_quantile}",
                initialvalue=self.speech_threshold_quantile,
                minvalue=0.0,
                maxvalue=1.0
            )
            if val is not None:
                self.speech_threshold_quantile = val
            
            # Min speech score
            val = simpledialog.askfloat(
                "Minimum Speech Score",
                f"Minimum speech score (IQR-widths above baseline)\nCurrent: {self.min_speech_score}",
                initialvalue=self.min_speech_score,
                minvalue=0.0,
                maxvalue=5.0
            )
            if val is not None:
                self.min_speech_score = val
            
            # Acceleration weight
            val = simpledialog.askfloat(
                "Acceleration Weight",
                f"Acceleration weight\nHigher = more emphasis on motion\nCurrent: {self.accel_weight}",
                initialvalue=self.accel_weight,
                minvalue=0.0,
                maxvalue=5.0
            )
            if val is not None:
                self.accel_weight = val
            
            # Min active duration
            val = simpledialog.askfloat(
                "Minimum Active Duration",
                f"Minimum active period duration (seconds)\nCurrent: {self.min_active_duration_sec}",
                initialvalue=self.min_active_duration_sec,
                minvalue=0.0,
                maxvalue=10.0
            )
            if val is not None:
                self.min_active_duration_sec = val
            
            # Merge gap
            val = simpledialog.askfloat(
                "Merge Gap",
                f"Maximum gap to merge active periods (seconds)\nCurrent: {self.merge_gap_sec}",
                initialvalue=self.merge_gap_sec,
                minvalue=0.0,
                maxvalue=5.0
            )
            if val is not None:
                self.merge_gap_sec = val
        
        root.destroy()
    
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
        
        # Get user parameters
        self.get_user_parameters()

        df = self.compute_speech_presence(self.data)
        df = self.apply_peak_labeling(df)
        
        # Apply post-processing to smooth and filter labels
        df = self.post_process_labels(df)

        # Add per-time-bin speaker column (badge name or 'no_speaker')
        df = self.add_speaker_column(df)

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
        print("\nOverall label counts:")
        print(df["auto_activity_label"].value_counts())
        
        print("\nPer-badge label counts:")
        for badge, badge_df in df.groupby('Badge_Name'):
            active_count = (badge_df['auto_activity_label'] == 'active').sum()
            total_count = len(badge_df)
            pct = (active_count / total_count * 100) if total_count > 0 else 0
            person = badge_df['Person_Name'].iloc[0] if 'Person_Name' in badge_df.columns else ''
            name_display = f" ({person})" if person else ""
            print(f"  {badge}{name_display}: {active_count:,}/{total_count:,} ({pct:.1f}% active)")
        
        print("\nParameters used:")
        print(f"  Speech threshold quantile: {self.speech_threshold_quantile}")
        print(f"  Min speech score: {self.min_speech_score}")
        print(f"  Acceleration weight: {self.accel_weight}")
        print(f"  Min active duration: {self.min_active_duration_sec}s")
        print(f"  Min inactive duration: {self.min_inactive_duration_sec}s")
        print(f"  Merge gap: {self.merge_gap_sec}s")


# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    labeler = AutoLabeler()
    labeler.process()