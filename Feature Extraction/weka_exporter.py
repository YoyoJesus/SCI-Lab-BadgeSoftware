#!/usr/bin/env python3
"""
Weka Meeting Effectiveness Exporter
=====================================

Combines meeting / participant / window feature CSVs (output of
feature_extraction.py) into a single flat meeting-level dataset,
prompts you to label each meeting's effectiveness, and writes:

  weka_outputs/meeting_dataset.csv
  weka_outputs/meeting_dataset.arff   <- load directly into Weka

Effectiveness label: low / medium / high  (3-class classification)

Usage:
  python weka_exporter.py

Author: SCI-Lab Badge Software
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).parent / "weka_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EFFECTIVENESS_CLASSES = ["low", "medium", "high"]

# ---------------------------------------------------------------------------
# Feature selection
# ---------------------------------------------------------------------------

# Meeting-level columns to pull directly (already one row per meeting)
MEETING_COLS = [
    "speaking_ratio",
    "silence_ratio",
    "turns_per_minute",
    "mean_turn_duration_sec",
    "median_turn_duration_sec",
    "back_to_back_ratio",
    "mean_gap_sec",
    "n_active_participants",
    "gini_speaking_time",
    "participation_entropy",
    "dominant_speaker_fraction",
    "micro_turn_ratio",
]

# Participant-level columns to aggregate (mean + std across participants)
PARTICIPANT_AGG_COLS = [
    "speaking_fraction",
    "mean_turn_duration_sec",
    "interruption_ratio_suffered",
    "interruption_ratio_initiated",
    "response_latency_mean_sec",
    "self_succession_count",
    "micro_turn_ratio",
]

# Window-level columns to aggregate (std = consistency; slope = trend)
WINDOW_TREND_COLS = [
    "speaking_ratio",
    "gini_speaking_time",
    "turns_per_minute",
    "n_active_participants",
    "back_to_back_ratio",
]


# ---------------------------------------------------------------------------
# Flatten one meeting directory into a single feature dict
# ---------------------------------------------------------------------------

def flatten_meeting(meeting_dir: Path) -> dict:
    """Load the three feature CSVs and return one flat feature dict."""
    meeting_csv     = meeting_dir / "meeting_features.csv"
    participant_csv = meeting_dir / "participant_features.csv"
    window_csv      = meeting_dir / "window_features.csv"

    for p in [meeting_csv, participant_csv, window_csv]:
        if not p.exists():
            sys.exit(f"ERROR: Missing expected file: {p}")

    m_df = pd.read_csv(meeting_csv)
    p_df = pd.read_csv(participant_csv)
    w_df = pd.read_csv(window_csv)

    row = {}

    # -- Meeting-level features (direct) -------------------------------------
    m = m_df.iloc[0]
    for col in MEETING_COLS:
        row[col] = float(m[col]) if col in m.index and pd.notna(m[col]) else float("nan")

    # -- Participant-level aggregates ----------------------------------------
    for col in PARTICIPANT_AGG_COLS:
        if col in p_df.columns:
            vals = pd.to_numeric(p_df[col], errors="coerce").dropna()
            row[f"part_mean_{col}"] = vals.mean() if len(vals) > 0 else float("nan")
            row[f"part_std_{col}"]  = vals.std(ddof=0) if len(vals) > 1 else 0.0
        else:
            row[f"part_mean_{col}"] = float("nan")
            row[f"part_std_{col}"]  = float("nan")

    # -- Window-level dynamics -----------------------------------------------
    for col in WINDOW_TREND_COLS:
        if col in w_df.columns:
            vals = pd.to_numeric(w_df[col], errors="coerce").dropna()
            row[f"win_std_{col}"] = vals.std(ddof=0) if len(vals) > 1 else 0.0
            # Linear slope (trend): positive = metric rises over meeting duration
            if len(vals) >= 2:
                x = np.arange(len(vals), dtype=float)
                slope = float(np.polyfit(x, vals.values, 1)[0])
            else:
                slope = 0.0
            row[f"win_slope_{col}"] = slope
        else:
            row[f"win_std_{col}"]   = float("nan")
            row[f"win_slope_{col}"] = float("nan")

    return row


# ---------------------------------------------------------------------------
# Display a meeting summary for labeling context
# ---------------------------------------------------------------------------

def meeting_summary(meeting_dir: Path, features: dict) -> str:
    lines = [
        f"Meeting:  {meeting_dir.name}",
        "",
        f"  Duration            : {features.get('speaking_ratio', float('nan')):.0%} speaking",
        f"  Turns / min         : {features.get('turns_per_minute', float('nan')):.2f}",
        f"  Mean turn length    : {features.get('mean_turn_duration_sec', float('nan')):.1f}s",
        f"  Participation Gini  : {features.get('gini_speaking_time', float('nan')):.3f}  "
        f"(0=equal, 1=one person dominates)",
        f"  Participation entropy: {features.get('participation_entropy', float('nan')):.3f}  "
        f"(1=perfectly balanced)",
        f"  Back-to-back ratio  : {features.get('back_to_back_ratio', float('nan')):.0%}",
        f"  Dominant speaker    : {features.get('dominant_speaker_fraction', float('nan')):.0%} of speaking time",
        "",
        "Label this meeting:",
        "  1 = low      (unproductive, dominated, disorganized)",
        "  2 = medium   (average — some issues but functional)",
        "  3 = high     (balanced, structured, productive)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt for effectiveness label via GUI
# ---------------------------------------------------------------------------

def prompt_label(meeting_dir: Path, features: dict) -> str | None:
    summary = meeting_summary(meeting_dir, features)

    root = tk.Tk()
    root.withdraw()

    val = simpledialog.askinteger(
        "Label Meeting Effectiveness",
        summary + "\n\nEnter 1 (low), 2 (medium), or 3 (high):",
        minvalue=1,
        maxvalue=3,
    )
    root.destroy()

    if val is None:
        return None
    mapping = {1: "low", 2: "medium", 3: "high"}
    return mapping[val]


# ---------------------------------------------------------------------------
# Select a meeting directory via GUI
# ---------------------------------------------------------------------------

def select_meeting_dir() -> Path | None:
    base = Path(__file__).parent / "feature_extraction_outputs"
    if not base.exists():
        base = Path(__file__).parent

    root = tk.Tk()
    root.withdraw()
    chosen = filedialog.askdirectory(
        title="Select a meeting feature folder (contains meeting_features.csv)",
        initialdir=str(base),
    )
    root.destroy()
    return Path(chosen) if chosen else None


# ---------------------------------------------------------------------------
# Write ARFF
# ---------------------------------------------------------------------------

def write_arff(df: pd.DataFrame, path: Path):
    feature_cols = [c for c in df.columns if c != "effectiveness"]
    lines = [
        "@RELATION meeting_effectiveness",
        "",
    ]

    for col in feature_cols:
        lines.append(f"@ATTRIBUTE {col} NUMERIC")

    lines.append(f"@ATTRIBUTE effectiveness {{{','.join(EFFECTIVENESS_CLASSES)}}}")
    lines.append("")
    lines.append("@DATA")

    for _, row in df.iterrows():
        vals = []
        for col in feature_cols:
            v = row[col]
            vals.append("?" if pd.isna(v) else f"{v:.6f}")
        vals.append(str(row["effectiveness"]))
        lines.append(",".join(vals))

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print("  Weka Meeting Effectiveness Exporter")
    print("=" * 55)
    print("\nYou will select one meeting folder at a time.")
    print("Each folder must contain the three CSVs produced by")
    print("feature_extraction.py.\n")

    if len(sys.argv) > 1:
        print(f"WARNING: 10 meetings is a small dataset for classification.")
        print(f"         Use leave-one-out cross-validation in Weka (LOOCV).\n")

    dataset_rows = []

    while True:
        meeting_dir = select_meeting_dir()
        if meeting_dir is None:
            if not dataset_rows:
                print("No meetings selected. Exiting.")
                return
            break

        print(f"\nProcessing: {meeting_dir.name}")
        try:
            features = flatten_meeting(meeting_dir)
        except SystemExit as e:
            print(str(e))
            continue

        label = prompt_label(meeting_dir, features)
        if label is None:
            print(f"  Skipped (no label provided)")
            continue

        features["effectiveness"] = label
        features["meeting_id"]    = meeting_dir.name
        dataset_rows.append(features)
        print(f"  Added: {meeting_dir.name}  →  {label}")

        # Ask if they want to add another
        root = tk.Tk()
        root.withdraw()
        another = messagebox.askyesno(
            "Add Another Meeting?",
            f"Dataset so far: {len(dataset_rows)} meeting(s).\n\nAdd another meeting?"
        )
        root.destroy()
        if not another:
            break

    if not dataset_rows:
        print("No meetings were labeled. Exiting.")
        return

    # Build DataFrame — meeting_id first, effectiveness last
    df = pd.DataFrame(dataset_rows)
    id_col  = df.pop("meeting_id")
    eff_col = df.pop("effectiveness")
    df.insert(0, "meeting_id", id_col)
    df["effectiveness"] = eff_col

    # Warn if very few samples
    if len(df) < 10:
        print(f"\n⚠  Only {len(df)} meetings labeled.")
        print("   Use leave-one-out (LOOCV) in Weka for cross-validation.")
        print("   Consider binary labels (low vs high) for better results.")

    # Save CSV (includes meeting_id for reference)
    csv_path  = OUTPUT_DIR / "meeting_dataset.csv"
    arff_path = OUTPUT_DIR / "meeting_dataset.arff"

    df.to_csv(csv_path, index=False)

    # ARFF excludes meeting_id (string — not useful for ML)
    arff_df = df.drop(columns=["meeting_id"])
    write_arff(arff_df, arff_path)

    print(f"\n{'='*55}")
    print(f"  Export complete — {len(df)} meeting(s)")
    print(f"{'='*55}")
    print(f"  CSV  : {csv_path}")
    print(f"  ARFF : {arff_path}")
    print(f"\n  Label distribution:")
    for label, count in df["effectiveness"].value_counts().items():
        print(f"    {label:8s}: {count}")
    print(f"\n  Total features: {len(arff_df.columns) - 1}")
    print(f"\n  Weka tips:")
    print(f"    - Open meeting_dataset.arff in Weka Explorer")
    print(f"    - Set 'effectiveness' as the class attribute")
    print(f"    - Use Test option: Leave-one-out (LOOCV) given small dataset")
    print(f"    - Try: NaiveBayes, J48, RandomForest")


if __name__ == "__main__":
    main()
