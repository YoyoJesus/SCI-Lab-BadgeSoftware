#!/usr/bin/env python3
"""
Meeting Productivity Feature Extractor
=======================================

Consumes an auto-labeled badge CSV (output of auto_label.py) and produces
three feature tables for meeting productivity analysis:

  meeting_features.csv     — one row per meeting, global summary
  participant_features.csv — one row per (meeting x participant)
  window_features.csv      — one row per (meeting x time window)

Usage:
  python feature_extraction.py path/to/hacksu_meeting_1.csv
  python feature_extraction.py path/to/hacksu_meeting_1.csv --window-minutes 3
  python feature_extraction.py path/to/hacksu_meeting_1.csv --min-turn-bins 1

Parameters:
  --window-minutes  FLOAT   Width of each analysis window (default: 5.0)
  --min-turn-bins   INT     Minimum 500ms bins to count as a full turn (default: 2 = 1 second)
                            Shorter turns are kept but flagged is_micro_turn=True

Author: SCI-Lab Badge Software
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {
    "Timestamp", "Badge_Name", "Person_Name",
    "Sound_Level", "Acceleration", "RSSI",
    "time_bin", "auto_activity_label", "auto_speaker",
    "norm_sound", "norm_accel", "speech_score",
}

NO_SPEAKER = "no_speaker"


# ---------------------------------------------------------------------------
# Step 1: Load & validate
# ---------------------------------------------------------------------------

def load_and_validate(path: Path) -> pd.DataFrame:
    print(f"Loading {path.name} ...")
    df = pd.read_csv(path, low_memory=False)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        sys.exit(f"ERROR: Input CSV is missing required columns: {missing}")

    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df["time_bin"]  = pd.to_datetime(df["time_bin"])

    # Ensure Person_Name always has a value (fall back to Badge_Name)
    df["Person_Name"] = (
        df["Person_Name"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
    )
    df["Person_Name"] = df["Person_Name"].fillna(df["Badge_Name"])

    df = df.sort_values(["time_bin", "Badge_Name"]).reset_index(drop=True)
    print(f"  Loaded {len(df):,} rows | {df['Badge_Name'].nunique()} badges | "
          f"time span: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
    return df


# ---------------------------------------------------------------------------
# Step 2: Aggregate raw samples to one row per (time_bin, Badge_Name)
# ---------------------------------------------------------------------------

def aggregate_to_bins(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse ~8 raw samples per (time_bin, badge) down to one representative row.
    Scalar signals are averaged; categoricals take the first value (already
    consistent within a bin by auto_label.py).
    """
    agg = (
        df.groupby(["time_bin", "Badge_Name"], sort=False)
        .agg(
            Person_Name       = ("Person_Name",         "first"),
            mean_sound        = ("Sound_Level",         "mean"),
            max_sound         = ("Sound_Level",         "max"),
            mean_accel        = ("Acceleration",        "mean"),
            max_accel         = ("Acceleration",        "max"),
            median_rssi       = ("RSSI",                "median"),
            mean_norm_sound   = ("norm_sound",          "mean"),
            mean_norm_accel   = ("norm_accel",          "mean"),
            mean_speech_score = ("speech_score",        "mean"),
            max_speech_score  = ("speech_score",        "max"),
            activity_label    = ("auto_activity_label", "first"),
            auto_speaker      = ("auto_speaker",        "first"),
            sample_count      = ("Timestamp",           "count"),
        )
        .reset_index()
        .sort_values(["time_bin", "Badge_Name"])
        .reset_index(drop=True)
    )
    return agg


# ---------------------------------------------------------------------------
# Step 3: Extract speech turns
# ---------------------------------------------------------------------------

def extract_turns(bin_df: pd.DataFrame, min_bins: int = 2) -> pd.DataFrame:
    """
    Identify speech turns from the 500ms-bin speaker sequence.

    A turn = maximal run of consecutive bins with the same non-'no_speaker'
    auto_speaker value.  Back-to-back turns (no silence gap) are supported.

    Returns one row per turn with turn metadata and gap/context columns.
    """
    # Collapse to one row per time_bin (speaker resolved by auto_label.py)
    speaker_seq = (
        bin_df[["time_bin", "auto_speaker"]]
        .drop_duplicates("time_bin")
        .sort_values("time_bin")
        .reset_index(drop=True)
    )

    # Build person-name lookup from badge name
    name_map = (
        bin_df[["Badge_Name", "Person_Name"]]
        .drop_duplicates()
        .set_index("Badge_Name")["Person_Name"]
        .to_dict()
    )

    # Assign run IDs (each change in auto_speaker starts a new run)
    speaker_seq["changed"] = (
        speaker_seq["auto_speaker"] != speaker_seq["auto_speaker"].shift(1)
    ).astype(int)
    speaker_seq["run_id"] = speaker_seq["changed"].cumsum()

    runs = (
        speaker_seq
        .groupby(["run_id", "auto_speaker"], sort=False)
        .agg(start_bin=("time_bin", "min"),
             end_bin  =("time_bin", "max"),
             n_bins   =("time_bin", "count"))
        .reset_index()
        .sort_values("run_id")
        .reset_index(drop=True)
    )
    runs["duration_sec"] = runs["n_bins"] * 0.5

    # Split into speech runs and silence runs; keep both for gap calculations
    speech_mask = runs["auto_speaker"] != NO_SPEAKER
    speech_runs = runs[speech_mask].copy().reset_index(drop=True)
    speech_runs["is_micro_turn"] = speech_runs["n_bins"] < min_bins
    speech_runs["turn_index_global"] = range(len(speech_runs))
    speech_runs["speaker_person"] = (
        speech_runs["auto_speaker"].map(name_map).fillna(speech_runs["auto_speaker"])
    )

    # Precompute prev/next run info using a dictionary for O(1) lookup
    run_by_id = runs.set_index("run_id")

    def _run_val(rid, col):
        if rid in run_by_id.index:
            return run_by_id.at[rid, col]
        return None

    # Build a run_id → speaker_badge lookup for speech runs only (for prev_real_speaker)
    speech_run_ids = set(speech_runs["run_id"].values)

    prev_speakers, next_speakers, gaps_before, gaps_after, prev_real_speakers = [], [], [], [], []
    for _, row in speech_runs.iterrows():
        rid = row["run_id"]

        prev_spk = _run_val(rid - 1, "auto_speaker")
        next_spk = _run_val(rid + 1, "auto_speaker")

        prev_speakers.append(prev_spk if prev_spk is not None else "START_OF_MEETING")
        next_speakers.append(next_spk if next_spk is not None else "END_OF_MEETING")

        # Gap = duration of the adjacent silence run (0 if adjacent run is speech)
        gap_before = (
            _run_val(rid - 1, "duration_sec")
            if prev_spk == NO_SPEAKER else 0.0
        )
        gap_after = (
            _run_val(rid + 1, "duration_sec")
            if next_spk == NO_SPEAKER else 0.0
        )
        gaps_before.append(gap_before if gap_before is not None else 0.0)
        gaps_after.append(gap_after  if gap_after  is not None else 0.0)

        # prev_real_speaker: look back past any silence to find the last actual speaker
        # (same as prev_speaker when back-to-back; differs when there's a gap)
        look_back = rid - 1
        prev_real = "START_OF_MEETING"
        while look_back in run_by_id.index:
            spk = run_by_id.at[look_back, "auto_speaker"]
            if spk != NO_SPEAKER:
                prev_real = spk
                break
            look_back -= 1
        prev_real_speakers.append(prev_real)

    speech_runs["prev_speaker"]      = prev_speakers
    speech_runs["next_speaker"]      = next_speakers
    speech_runs["gap_before_sec"]    = gaps_before
    speech_runs["prev_real_speaker"] = prev_real_speakers
    speech_runs["gap_after_sec"]  = gaps_after

    return speech_runs.rename(columns={"auto_speaker": "speaker_badge"})


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _gini(values):
    """Gini coefficient of an array of non-negative values. 0=equal, 1=dominated."""
    arr = np.array(sorted(values), dtype=float)
    total = arr.sum()
    if total == 0 or len(arr) == 0:
        return 0.0
    n = len(arr)
    numerator = 2 * np.dot(np.arange(1, n + 1), arr) - (n + 1) * total
    return numerator / (n * total)


def _norm_entropy(fractions):
    """Normalized Shannon entropy (0=one speaker, 1=perfectly equal)."""
    n = len(fractions)
    if n <= 1:
        return 0.0
    h = -sum(p * math.log(p) for p in fractions if p > 0)
    return h / math.log(n)


def _per_person_speaking_sec(turns: pd.DataFrame):
    """Return {badge: speaking_seconds} dict for all turns in the slice."""
    return turns.groupby("speaker_badge")["duration_sec"].sum().to_dict()


def _slice_features(bin_slice: pd.DataFrame, turn_slice: pd.DataFrame,
                    all_badges: list) -> dict:
    """
    Compute meeting/window-level features from a bin slice and turn slice.
    Used by both compute_meeting_features and the window loop.
    """
    f = {}

    total_bins    = bin_slice["time_bin"].nunique()
    speaking_bins = (
        bin_slice[bin_slice["auto_speaker"] != NO_SPEAKER]["time_bin"].nunique()
    )
    silence_bins  = total_bins - speaking_bins

    f["total_bins"]          = total_bins
    f["speaking_bins"]       = speaking_bins
    f["silence_bins"]        = silence_bins
    f["speaking_ratio"]      = speaking_bins / total_bins if total_bins > 0 else 0.0
    f["silence_ratio"]       = silence_bins  / total_bins if total_bins > 0 else 0.0

    duration_sec = total_bins * 0.5
    f["duration_sec"] = duration_sec

    # Turn-level features
    n_turns = len(turn_slice)
    f["n_turns"]          = n_turns
    f["turns_per_minute"] = (n_turns / (duration_sec / 60)) if duration_sec > 0 else 0.0

    if n_turns > 0:
        f["mean_turn_duration_sec"]   = turn_slice["duration_sec"].mean()
        f["median_turn_duration_sec"] = turn_slice["duration_sec"].median()
        f["std_turn_duration_sec"]    = turn_slice["duration_sec"].std(ddof=0)
        f["back_to_back_ratio"]       = (turn_slice["gap_before_sec"] == 0).sum() / n_turns
        valid_gaps = turn_slice[turn_slice["gap_before_sec"] > 0]["gap_before_sec"]
        f["mean_gap_sec"] = valid_gaps.mean() if len(valid_gaps) > 0 else 0.0
        f["std_gap_sec"]  = valid_gaps.std(ddof=0) if len(valid_gaps) > 0 else 0.0
        f["micro_turn_ratio"] = turn_slice["is_micro_turn"].sum() / n_turns
    else:
        f["mean_turn_duration_sec"]   = np.nan
        f["median_turn_duration_sec"] = np.nan
        f["std_turn_duration_sec"]    = np.nan
        f["back_to_back_ratio"]       = np.nan
        f["mean_gap_sec"]             = np.nan
        f["std_gap_sec"]              = np.nan
        f["micro_turn_ratio"]         = np.nan

    # Participation features
    per_person = _per_person_speaking_sec(turn_slice)
    total_speaking_sec = sum(per_person.values())

    n_active = len(per_person)
    f["n_active_participants"] = n_active

    if n_active > 0 and total_speaking_sec > 0:
        speaking_secs = list(per_person.values())
        fractions = [s / total_speaking_sec for s in speaking_secs]
        f["gini_speaking_time"]        = _gini(speaking_secs)
        f["participation_entropy"]     = _norm_entropy(fractions)
        f["dominant_speaker_fraction"] = max(fractions)
    else:
        f["gini_speaking_time"]        = np.nan
        f["participation_entropy"]     = np.nan
        f["dominant_speaker_fraction"] = np.nan

    # Audio/motion quality signals
    active_bins = bin_slice[bin_slice["activity_label"] == "active"]
    f["mean_accel_active"] = active_bins["mean_accel"].mean() if len(active_bins) > 0 else np.nan
    f["mean_accel_all"]    = bin_slice["mean_accel"].mean()

    speaker_bins = bin_slice[bin_slice["auto_speaker"] != NO_SPEAKER]
    f["mean_speech_score"] = speaker_bins["mean_speech_score"].mean() if len(speaker_bins) > 0 else np.nan

    # Per-person speaking seconds (one feature per badge; NaN if not present)
    for badge in all_badges:
        f[f"speaking_sec_{badge}"]  = per_person.get(badge, 0.0)
        badge_turns = turn_slice[turn_slice["speaker_badge"] == badge]
        f[f"turn_count_{badge}"]    = len(badge_turns)

    return f


# ---------------------------------------------------------------------------
# Step 4: Meeting-level features
# ---------------------------------------------------------------------------

def compute_meeting_features(df: pd.DataFrame, bin_df: pd.DataFrame,
                              turns: pd.DataFrame, meeting_id: str) -> pd.DataFrame:
    all_badges = sorted(df["Badge_Name"].unique())
    participants = sorted(df["Person_Name"].unique())

    base = {
        "meeting_id":    meeting_id,
        "meeting_date":  str(df["Timestamp"].dt.date.iloc[0]),
        "start_time":    str(df["Timestamp"].min()),
        "end_time":      str(df["Timestamp"].max()),
        "n_participants": df["Badge_Name"].nunique(),
        "participants":  ", ".join(participants),
        "n_unique_turn_holders": turns["speaker_badge"].nunique(),
    }

    total_sec = (df["Timestamp"].max() - df["Timestamp"].min()).total_seconds()
    base["total_duration_sec"] = total_sec

    slice_feats = _slice_features(bin_df, turns, all_badges)
    base.update(slice_feats)

    # Participation features that need full meeting context
    per_person = _per_person_speaking_sec(turns)
    total_speaking_sec = sum(per_person.values())
    if total_speaking_sec > 0:
        base["dominant_speaker_ratio"] = max(per_person.values()) / total_speaking_sec
    else:
        base["dominant_speaker_ratio"] = np.nan

    return pd.DataFrame([base])


# ---------------------------------------------------------------------------
# Step 5: Participant-level features
# ---------------------------------------------------------------------------

def compute_participant_features(df: pd.DataFrame, bin_df: pd.DataFrame,
                                 turns: pd.DataFrame, meeting_id: str,
                                 meeting_feats: pd.DataFrame) -> pd.DataFrame:
    all_badges = sorted(df["Badge_Name"].unique())
    total_speaking_sec = meeting_feats["speaking_sec_" + all_badges[0]].iloc[0] if len(all_badges) > 0 else 0
    # Recalculate total speaking sec directly
    total_speaking_sec = turns["duration_sec"].sum()
    meeting_duration   = meeting_feats["total_duration_sec"].iloc[0]
    meeting_start      = df["Timestamp"].min()

    rows = []
    for badge in all_badges:
        p_turns  = turns[turns["speaker_badge"] == badge]
        name_map = (
            df[df["Badge_Name"] == badge]["Person_Name"]
            .iloc[0] if len(df[df["Badge_Name"] == badge]) > 0 else badge
        )

        r = {
            "meeting_id":   meeting_id,
            "badge_name":   badge,
            "person_name":  name_map,
        }

        speaking_sec = p_turns["duration_sec"].sum()
        n_turns      = len(p_turns)

        r["speaking_sec"]       = speaking_sec
        r["speaking_fraction"]  = speaking_sec / total_speaking_sec if total_speaking_sec > 0 else 0.0
        r["n_turns"]            = n_turns
        r["turn_rate_per_min"]  = (n_turns / (meeting_duration / 60)) if meeting_duration > 0 else 0.0

        if n_turns > 0:
            r["mean_turn_duration_sec"]   = p_turns["duration_sec"].mean()
            r["median_turn_duration_sec"] = p_turns["duration_sec"].median()
            r["std_turn_duration_sec"]    = p_turns["duration_sec"].std(ddof=0)
            r["max_turn_duration_sec"]    = p_turns["duration_sec"].max()
            r["micro_turn_count"]         = int(p_turns["is_micro_turn"].sum())
            r["micro_turn_ratio"]         = r["micro_turn_count"] / n_turns

            # Interruptions
            badge_set = set(turns["speaker_badge"].unique())
            # Interrupted: this person was speaking, next speaker is someone else with no gap
            r["n_turns_interrupted"] = int(
                ((p_turns["gap_after_sec"] == 0) &
                 (p_turns["next_speaker"].isin(badge_set)) &
                 (p_turns["next_speaker"] != badge)).sum()
            )
            # Interrupting: this person started with no gap after another speaker
            r["n_turns_interrupting"] = int(
                ((p_turns["gap_before_sec"] == 0) &
                 (p_turns["prev_speaker"].isin(badge_set)) &
                 (p_turns["prev_speaker"] != badge)).sum()
            )
            r["interruption_ratio_suffered"]  = r["n_turns_interrupted"]  / n_turns
            r["interruption_ratio_initiated"] = r["n_turns_interrupting"] / n_turns

            # Response latency: silence gap after a different speaker ended and before
            # this person started (uses prev_real_speaker to look through silence runs)
            resp_mask = (
                (p_turns["prev_real_speaker"].isin(badge_set)) &
                (p_turns["prev_real_speaker"] != badge) &
                (p_turns["gap_before_sec"] > 0)
            )
            resp_gaps = p_turns[resp_mask]["gap_before_sec"]
            r["response_latency_mean_sec"] = resp_gaps.mean() if len(resp_gaps) > 0 else np.nan

            # Self-succession: takes floor again after a silence (same badge was last speaker)
            r["self_succession_count"] = int(
                ((p_turns["prev_speaker"] == badge) & (p_turns["gap_before_sec"] > 0)).sum()
            )

            # Timeline
            r["first_turn_time_sec"] = (
                p_turns["start_bin"].min() - meeting_start
            ).total_seconds()
            r["last_turn_time_sec"] = (
                p_turns["end_bin"].max() - meeting_start
            ).total_seconds()
            r["active_participation_span_sec"] = (
                r["last_turn_time_sec"] - r["first_turn_time_sec"]
            )
        else:
            for col in [
                "mean_turn_duration_sec", "median_turn_duration_sec",
                "std_turn_duration_sec", "max_turn_duration_sec",
                "micro_turn_count", "micro_turn_ratio",
                "n_turns_interrupted", "n_turns_interrupting",
                "interruption_ratio_suffered", "interruption_ratio_initiated",
                "response_latency_mean_sec", "self_succession_count",
                "first_turn_time_sec", "last_turn_time_sec",
                "active_participation_span_sec",
            ]:
                r[col] = np.nan if col not in {"micro_turn_count", "n_turns_interrupted",
                                                "n_turns_interrupting", "self_succession_count"} else 0

        # Per-badge bin-level signals
        badge_bins     = bin_df[bin_df["Badge_Name"] == badge]
        speaking_bins  = badge_bins[badge_bins["auto_speaker"] == badge]
        listening_bins = badge_bins[badge_bins["auto_speaker"] != badge]

        r["speaking_activity_ratio"] = (
            len(speaking_bins) / len(badge_bins) if len(badge_bins) > 0 else 0.0
        )
        r["mean_speech_score_during_turns"] = (
            speaking_bins["mean_speech_score"].mean() if len(speaking_bins) > 0 else np.nan
        )
        r["mean_accel_during_turns"]  = (
            speaking_bins["mean_accel"].mean() if len(speaking_bins) > 0 else np.nan
        )
        r["mean_accel_not_speaking"]  = (
            listening_bins["mean_accel"].mean() if len(listening_bins) > 0 else np.nan
        )
        r["rssi_mean"] = badge_bins["median_rssi"].mean() if len(badge_bins) > 0 else np.nan
        r["rssi_std"]  = badge_bins["median_rssi"].std(ddof=0) if len(badge_bins) > 0 else np.nan

        rows.append(r)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 6: Window-level features
# ---------------------------------------------------------------------------

def compute_window_features(df: pd.DataFrame, bin_df: pd.DataFrame,
                             turns: pd.DataFrame, meeting_id: str,
                             window_minutes: float = 5.0) -> pd.DataFrame:
    all_badges    = sorted(df["Badge_Name"].unique())
    window_sec    = window_minutes * 60
    meeting_start = bin_df["time_bin"].min()
    meeting_end   = bin_df["time_bin"].max()
    total_duration = (meeting_end - meeting_start).total_seconds()

    # Build non-overlapping window boundaries
    boundaries = []
    t = meeting_start
    while t < meeting_end:
        w_end = t + pd.Timedelta(seconds=window_sec)
        boundaries.append((t, w_end))
        t = w_end

    rows = []
    total_windows = len(boundaries)
    for idx, (w_start, w_end) in enumerate(boundaries):
        bin_slice  = bin_df[(bin_df["time_bin"] >= w_start) & (bin_df["time_bin"] < w_end)]
        # Include turns that START within the window
        turn_slice = turns[(turns["start_bin"] >= w_start) & (turns["start_bin"] < w_end)]

        if len(bin_slice) == 0:
            # Empty window — emit zeros so the time series is complete
            r = {
                "meeting_id":              meeting_id,
                "window_index":            idx,
                "window_start":            str(w_start),
                "window_end":              str(w_end),
                "window_position_fraction": idx / max(total_windows - 1, 1),
            }
            rows.append(r)
            continue

        feats = _slice_features(bin_slice, turn_slice, all_badges)
        r = {
            "meeting_id":              meeting_id,
            "window_index":            idx,
            "window_start":            str(w_start),
            "window_end":              str(w_end),
            "window_position_fraction": idx / max(total_windows - 1, 1),
        }
        r.update(feats)
        rows.append(r)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract meeting productivity features from an auto-labeled badge CSV."
    )
    parser.add_argument(
        "input_csv", type=Path,
        help="Path to auto-labeled CSV (output of auto_label.py)."
    )
    parser.add_argument(
        "--window-minutes", type=float, default=5.0,
        help="Width of each analysis window in minutes (default: 5.0)."
    )
    parser.add_argument(
        "--min-turn-bins", type=int, default=2,
        help="Min 500ms bins to count as a full turn (default: 2 = 1 second)."
    )
    args = parser.parse_args()

    if not args.input_csv.exists():
        sys.exit(f"ERROR: File not found: {args.input_csv}")

    meeting_id = args.input_csv.stem

    # Load
    df     = load_and_validate(args.input_csv)
    bin_df = aggregate_to_bins(df)
    turns  = extract_turns(bin_df, min_bins=args.min_turn_bins)

    print(f"  Turns extracted: {len(turns)} | "
          f"micro-turns: {turns['is_micro_turn'].sum()} | "
          f"back-to-back: {(turns['gap_before_sec'] == 0).sum()}")

    # Compute features
    meeting_feats     = compute_meeting_features(df, bin_df, turns, meeting_id)
    participant_feats = compute_participant_features(df, bin_df, turns, meeting_id, meeting_feats)
    window_feats      = compute_window_features(
        df, bin_df, turns, meeting_id, window_minutes=args.window_minutes
    )

    # Save outputs
    out_dir = Path(__file__).parent / "feature_extraction_outputs" / meeting_id
    out_dir.mkdir(parents=True, exist_ok=True)

    meeting_feats.to_csv(out_dir / "meeting_features.csv", index=False)
    participant_feats.to_csv(out_dir / "participant_features.csv", index=False)
    window_feats.to_csv(out_dir / "window_features.csv", index=False)

    print(f"\n=== Feature Extraction Complete ===")
    print(f"Input:    {args.input_csv.name}")
    print(f"Meeting:  {meeting_feats['total_duration_sec'].iloc[0]/60:.1f} min, "
          f"{meeting_feats['n_participants'].iloc[0]} participants")
    print(f"Output:   {out_dir}/")
    print(f"  - meeting_features.csv     ({len(meeting_feats)} row, "
          f"{len(meeting_feats.columns)} features)")
    print(f"  - participant_features.csv ({len(participant_feats)} rows, "
          f"{len(participant_feats.columns)} features)")
    print(f"  - window_features.csv      ({len(window_feats)} rows, "
          f"{len(window_feats.columns)} features)")


if __name__ == "__main__":
    main()
