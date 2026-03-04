#!/usr/bin/env python3
"""
Label Comparison Tool
=====================

Compares manual vs auto activity labels on a per-sample basis.

- Manual labels are treated as ground truth
- 'unknown' is normalized to 'not_active'
- Comparison is aligned by Badge_Name + Timestamp
- Auto label column is auto-detected for backward compatibility

Output:
processed_data/label_comparison/comparison_<timestamp>/

Author: Label Comparison Tool
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# --------------------------------------------------
# File selection
# --------------------------------------------------
def select_csv(title):
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title=title,
        filetypes=[("CSV files", "*.csv")]
    )

    root.destroy()
    return Path(file_path) if file_path else None


# --------------------------------------------------
# Label normalization
# --------------------------------------------------
def normalize_label(val):
    if pd.isna(val):
        return "not_active"
    val = str(val).strip().lower()
    if val == "active":
        return "active"
    return "not_active"


# --------------------------------------------------
# Speaker-state helpers
# --------------------------------------------------
def compute_speaker_states(merged_df, time_bin_ms=500):
    """
    Convert per-badge labels to a per-time-bin speaker state.

    For each time bin:
      - manual_speaker : badge with the most active samples in the bin
                         (ties broken alphabetically); 'no_speaker' if none active
      - auto_speaker   : same logic for auto labels

    Overlap bins (multiple manually-active badges) are resolved by sample count
    rather than skipped, so no data is lost.
    """
    df = merged_df.copy()
    df["time_bin"] = pd.to_datetime(df["Timestamp"]).dt.floor(f"{time_bin_ms}ms")

    rows = []
    overlap_count = 0
    for time_bin, group in df.groupby("time_bin"):
        manual_active = group[group["manual_label"] == "active"]["Badge_Name"].unique().tolist()
        auto_active   = group[group["auto_label"]   == "active"]["Badge_Name"].unique().tolist()

        if len(manual_active) == 0:
            manual_speaker = "no_speaker"
        elif len(manual_active) == 1:
            manual_speaker = manual_active[0]
        else:
            # Overlap: pick badge with the most active samples in this bin
            overlap_count += 1
            counts = group[group["manual_label"] == "active"].groupby("Badge_Name").size()
            manual_speaker = counts.idxmax()

        if len(auto_active) == 0:
            auto_speaker = "no_speaker"
        elif len(auto_active) == 1:
            auto_speaker = auto_active[0]
        else:
            counts = group[group["auto_label"] == "active"].groupby("Badge_Name").size()
            auto_speaker = counts.idxmax()

        rows.append({"time_bin": time_bin, "manual_speaker": manual_speaker,
                     "auto_speaker": auto_speaker, "overlap": overlap_count > 0})

    result = pd.DataFrame(rows)
    result.attrs["overlap_bins"] = overlap_count
    return result


def build_speaker_cm(speaker_df, classes):
    """Build an (N x N) confusion matrix from speaker_df."""
    n = len(classes)
    idx = {c: i for i, c in enumerate(classes)}
    cm = np.zeros((n, n), dtype=int)
    for _, row in speaker_df.iterrows():
        m, a = row["manual_speaker"], row["auto_speaker"]
        if m in idx and a in idx:
            cm[idx[m], idx[a]] += 1
    return cm


def compute_multiclass_metrics(cm, classes):
    """
    Compute per-class TP/FP/FN/TN and precision/recall/F1 from an (N x N) cm.
    Also returns overall (speaker-state) accuracy.
    """
    total = int(cm.sum())
    overall_accuracy = cm.diagonal().sum() / total if total > 0 else 0.0

    per_class = {}
    for i, cls in enumerate(classes):
        tp = int(cm[i, i])
        fp = int(cm[:, i].sum()) - tp   # predicted as C but isn't C
        fn = int(cm[i, :].sum()) - tp   # actually C but predicted as something else
        tn = total - tp - fp - fn
        precision  = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall     = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1         = (2 * precision * recall / (precision + recall)
                      if (precision + recall) > 0 else 0.0)
        per_class[cls] = dict(TP=tp, FP=fp, FN=fn, TN=tn,
                              precision=precision, recall=recall, f1=f1)

    return overall_accuracy, per_class


def plot_comparison_grid(cm, labels, output_path, title="Badge Label Comparison"):
    """
    Plot an (N+1) x (N+1) confusion matrix (raw counts + row-normalised).

    cm     : numpy int array of shape (N, N) from build_speaker_cm
    labels : display labels in the same order as the cm rows/columns
    """
    n = len(labels)
    row_sums = cm.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    cm_pct = cm / row_sums

    fig, axes = plt.subplots(1, 2, figsize=(max(14, n * 2), max(6, n * 1.4)))
    fig.suptitle(title, fontsize=13, fontweight="bold")

    for ax, data, fmt_fn, subtitle in [
        (axes[0], cm,     lambda v: str(v),      "Raw counts"),
        (axes[1], cm_pct, lambda v: f"{v:.0%}",  "Normalised (% of ground truth)"),
    ]:
        im = ax.imshow(data, cmap="Blues", aspect="auto",
                       vmin=0, vmax=(None if data is cm else 1))
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel("Auto-Labeled Speaker", fontsize=11)
        ax.set_ylabel("Manual Speaker (Ground Truth)", fontsize=11)
        ax.set_title(subtitle, fontsize=10)

        threshold = data.max() * 0.55
        for i in range(n):
            for j in range(n):
                color = "white" if data[i, j] > threshold else "black"
                ax.text(j, i, fmt_fn(data[i, j]),
                        ha="center", va="center", color=color, fontsize=8)

        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Chart saved to: {output_path}")


# --------------------------------------------------
# Main logic
# --------------------------------------------------
def main():
    print("=== Label Comparison Tool ===\n")

    manual_file = select_csv("Select MANUALLY labeled CSV")
    if not manual_file:
        print("No manual file selected. Exiting.")
        return

    auto_file = select_csv("Select AUTO-labeled CSV")
    if not auto_file:
        print("No auto file selected. Exiting.")
        return

    print(f"Manual file: {manual_file}")
    print(f"Auto file:   {auto_file}\n")

    manual_df = pd.read_csv(manual_file)
    auto_df = pd.read_csv(auto_file)

    # --------------------------------------------------
    # Validate required base columns
    # --------------------------------------------------
    base_required = {"Timestamp", "Badge_Name"}

    for name, df in [("Manual", manual_df), ("Auto", auto_df)]:
        missing = base_required - set(df.columns)
        if missing:
            raise ValueError(f"{name} file missing required columns: {missing}")

    # --------------------------------------------------
    # Identify label columns
    # --------------------------------------------------
    manual_label_col = "activity_label"

    auto_label_candidates = [
        "activity_label",
        "auto_activity_label",
        "threshold_activity_label",
        "peak_activity_label"
    ]

    if manual_label_col not in manual_df.columns:
        raise ValueError("Manual file missing 'activity_label' column")

    auto_label_col = None
    for col in auto_label_candidates:
        if col in auto_df.columns:
            auto_label_col = col
            break

    if auto_label_col is None:
        raise ValueError(
            "Auto file missing label column. "
            "Expected one of: " + ", ".join(auto_label_candidates)
        )

    print(f"Detected auto label column: {auto_label_col}\n")

    # --------------------------------------------------
    # Prepare data
    # --------------------------------------------------
    manual_df["Timestamp"] = pd.to_datetime(manual_df["Timestamp"])
    auto_df["Timestamp"] = pd.to_datetime(auto_df["Timestamp"])

    manual_df["manual_label"] = manual_df[manual_label_col].apply(normalize_label)
    auto_df["auto_label"] = auto_df[auto_label_col].apply(normalize_label)

    # Handle Person_Name column
    has_manual_names = "Person_Name" in manual_df.columns
    has_auto_names = "Person_Name" in auto_df.columns

    if has_manual_names:
        manual_df = manual_df[["Timestamp", "Badge_Name", "Person_Name", "manual_label"]]
    else:
        manual_df["Person_Name"] = ""
        manual_df = manual_df[["Timestamp", "Badge_Name", "Person_Name", "manual_label"]]
        print("⚠️ Manual file doesn't have Person_Name column")

    if has_auto_names:
        auto_df = auto_df[["Timestamp", "Badge_Name", "Person_Name", "auto_label"]]
    else:
        auto_df["Person_Name"] = ""
        auto_df = auto_df[["Timestamp", "Badge_Name", "Person_Name", "auto_label"]]
        print("⚠️ Auto file doesn't have Person_Name column")

    # --------------------------------------------------
    # Align datasets
    # --------------------------------------------------
    merged = pd.merge(
        manual_df,
        auto_df,
        on=["Timestamp", "Badge_Name"],
        how="inner",
        suffixes=("_manual", "_auto")
    )

    # Merge person names: prefer manual names, but use auto names if manual is empty
    merged["Person_Name"] = merged.apply(
        lambda row: row["Person_Name_manual"] if pd.notna(row["Person_Name_manual"]) and row["Person_Name_manual"].strip() != ""
        else row["Person_Name_auto"],
        axis=1
    )

    # Clean up temporary columns
    merged = merged.drop(columns=["Person_Name_manual", "Person_Name_auto"])

    merged["label_match"] = merged["manual_label"] == merged["auto_label"]

    # --------------------------------------------------
    # Speaker-state pre-computation (reused throughout)
    # --------------------------------------------------
    speaker_df = compute_speaker_states(merged)
    badges_sorted = sorted(merged["Badge_Name"].unique().tolist())
    person_name_map = {
        row["Badge_Name"]: row["Person_Name"]
        for _, row in merged[["Badge_Name", "Person_Name"]].drop_duplicates().iterrows()
        if pd.notna(row["Person_Name"]) and str(row["Person_Name"]).strip()
    }
    classes = badges_sorted + ["no_speaker"]
    speaker_cm = build_speaker_cm(speaker_df, classes)
    speaker_acc, speaker_class_metrics = compute_multiclass_metrics(speaker_cm, classes)

    # Report name merging results
    if has_auto_names and not has_manual_names:
        print("✓ Copied person names from auto-labeled data to comparison output")
    elif has_auto_names and has_manual_names:
        names_filled = ((manual_df["Person_Name"].isna() | (manual_df["Person_Name"].str.strip() == "")) &
                       (auto_df["Person_Name"].notna() & (auto_df["Person_Name"].str.strip() != ""))).sum()
        if names_filled > 0:
            print(f"✓ Filled {names_filled} missing names from auto-labeled data")

    # --------------------------------------------------
    # Overall Metrics
    # --------------------------------------------------
    TP = ((merged.manual_label == "active") &
          (merged.auto_label == "active")).sum()

    TN = ((merged.manual_label == "not_active") &
          (merged.auto_label == "not_active")).sum()

    FP = ((merged.manual_label == "not_active") &
          (merged.auto_label == "active")).sum()

    FN = ((merged.manual_label == "active") &
          (merged.auto_label == "not_active")).sum()

    accuracy = (TP + TN) / len(merged) if len(merged) else 0
    precision = TP / (TP + FP) if (TP + FP) else 0
    recall = TP / (TP + FN) if (TP + FN) else 0
    specificity = TN / (TN + FP) if (TN + FP) else 0

    # --------------------------------------------------
    # Per-Badge/Person Metrics
    # --------------------------------------------------
    per_badge_metrics = {}

    for badge_name in sorted(merged["Badge_Name"].unique()):
        badge_data = merged[merged["Badge_Name"] == badge_name]

        # Get person name for this badge (if available)
        person_names = badge_data["Person_Name"].dropna()
        person_name = person_names.iloc[0] if len(person_names) > 0 and person_names.iloc[0].strip() != "" else ""

        # Calculate confusion matrix for this badge
        tp = ((badge_data.manual_label == "active") &
              (badge_data.auto_label == "active")).sum()

        tn = ((badge_data.manual_label == "not_active") &
              (badge_data.auto_label == "not_active")).sum()

        fp = ((badge_data.manual_label == "not_active") &
              (badge_data.auto_label == "active")).sum()

        fn = ((badge_data.manual_label == "active") &
              (badge_data.auto_label == "not_active")).sum()

        # Calculate metrics
        total = len(badge_data)
        acc = (tp + tn) / total if total else 0
        prec = tp / (tp + fp) if (tp + fp) else 0
        rec = tp / (tp + fn) if (tp + fn) else 0
        spec = tn / (tn + fp) if (tn + fp) else 0

        # No-speaker 3-class breakdown (per 500 ms bin from speaker_df)
        # For badge B: active / not_active (other speaking) / no_speaker
        sbins = speaker_df.copy()
        sbins["mc_manual"] = sbins["manual_speaker"].apply(
            lambda x: "active" if x == badge_name else ("no_speaker" if x == "no_speaker" else "not_active"))
        sbins["mc_auto"] = sbins["auto_speaker"].apply(
            lambda x: "active" if x == badge_name else ("no_speaker" if x == "no_speaker" else "not_active"))

        tn_other   = int(((sbins["mc_manual"] == "not_active") & (sbins["mc_auto"] == "not_active")).sum())
        tn_nsp     = int(((sbins["mc_manual"] == "no_speaker") & (sbins["mc_auto"] == "no_speaker")).sum())
        ns_fp      = int(((sbins["mc_manual"] == "no_speaker") & (sbins["mc_auto"] == "active")).sum())
        fn_as_nsp  = int(((sbins["mc_manual"] == "active")     & (sbins["mc_auto"] == "no_speaker")).sum())
        total_bins = len(sbins)
        bin_acc    = int((sbins["mc_manual"] == sbins["mc_auto"]).sum()) / total_bins if total_bins else 0

        per_badge_metrics[badge_name] = {
            "person_name": person_name,
            "total_samples": total,
            "TP": tp,
            "TN": tn,
            "FP": fp,
            "FN": fn,
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "specificity": spec,
            # No-speaker breakdown
            "TN_other_speaking": tn_other,
            "TN_no_speaker": tn_nsp,
            "NS_FP": ns_fp,
            "FN_as_no_speaker": fn_as_nsp,
            "bin_accuracy_3class": bin_acc,
            "total_bins": total_bins,
        }

    # --------------------------------------------------
    # Output
    # --------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    base_dir = Path("processed_data") / "label_comparison"
    run_dir = base_dir / f"comparison_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Create per-badge subdirectory
    per_badge_dir = run_dir / "per_badge"
    per_badge_dir.mkdir(exist_ok=True)

    # Save overall comparison
    csv_out = run_dir / f"label_comparison_{timestamp}.csv"
    summary_out = run_dir / f"summary_{timestamp}.txt"
    per_badge_summary_out = run_dir / f"per_badge_summary_{timestamp}.txt"

    merged.to_csv(csv_out, index=False)

    # Save per-badge CSV files
    for badge_name in sorted(merged["Badge_Name"].unique()):
        badge_data = merged[merged["Badge_Name"] == badge_name]
        badge_csv = per_badge_dir / f"{badge_name}_comparison.csv"
        badge_data.to_csv(badge_csv, index=False)

    # Save per-badge metrics summary as CSV for easy comparison
    metrics_df = pd.DataFrame.from_dict(per_badge_metrics, orient='index')
    metrics_df.index.name = 'Badge_Name'
    metrics_df = metrics_df.reset_index()
    # Reorder columns for better readability
    cols_order = ['Badge_Name', 'person_name', 'total_samples', 'TP', 'TN', 'FP', 'FN',
                  'accuracy', 'precision', 'recall', 'specificity']
    metrics_df = metrics_df[cols_order]
    metrics_csv = run_dir / f"per_badge_metrics_{timestamp}.csv"
    metrics_df.to_csv(metrics_csv, index=False)

    # Count how many badges have names
    badges_with_names = merged[merged["Person_Name"].notna() & (merged["Person_Name"].str.strip() != "")]["Badge_Name"].nunique()
    total_badges = merged["Badge_Name"].nunique()

    # --------------------------------------------------
    # Overall Summary
    # --------------------------------------------------
    summary = f"""
Label Comparison Summary - OVERALL
===================================
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Input files:
- Manual: {manual_file.name}
- Auto:   {auto_file.name}

Row counts:
- Manual rows: {len(manual_df)}
- Auto rows:   {len(auto_df)}
- Compared rows (aligned): {len(merged)}
- Dropped rows: {len(manual_df) + len(auto_df) - 2 * len(merged)}

Person Names:
- Badges with names: {badges_with_names}/{total_badges}
- Manual file had names: {has_manual_names}
- Auto file had names: {has_auto_names}

PRIMARY Metric - Speaker-State Accuracy (per 500ms bin, N+1 classes incl. no_speaker):
- Accuracy: {speaker_acc:.4f}  ({int(speaker_cm.diagonal().sum())} / {int(speaker_cm.sum())} bins correct)

Reference - Binary Per-Sample Metrics (active vs not_active, no_speaker collapsed into TN):
- Confusion: TP={TP}  TN={TN}  FP={FP}  FN={FN}
- Accuracy:    {accuracy:.4f}
- Precision:   {precision:.4f}
- Recall:      {recall:.4f}
- Specificity: {specificity:.4f}
"""

    with open(summary_out, "w") as f:
        f.write(summary)

    # --------------------------------------------------
    # Per-Badge Summary
    # --------------------------------------------------
    per_badge_summary = f"""
Label Comparison Summary - PER BADGE/PERSON
=============================================
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Total Badges: {total_badges}

"""

    for badge_name in sorted(per_badge_metrics.keys()):
        metrics = per_badge_metrics[badge_name]
        person_name = metrics["person_name"]
        header = f"{badge_name}" + (f" ({person_name})" if person_name else "")

        per_badge_summary += f"""
{'='*60}
{header}
{'='*60}
PRIMARY - 3-Class Accuracy (active / not_active / no_speaker, per 500ms bin):
- Accuracy: {metrics['bin_accuracy_3class']:.4f}  (over {metrics['total_bins']} bins)
- TN (other badge speaking):   {metrics['TN_other_speaking']:6d}
- TN (no speaker):             {metrics['TN_no_speaker']:6d}
- FP (no_speaker -> active):   {metrics['NS_FP']:6d}  (auto falsely activates during silence)
- FN (active -> no_speaker):   {metrics['FN_as_no_speaker']:6d}  (auto misses speech, calls it silence)

Reference - Binary Per-Sample (active vs not_active, no_speaker collapsed into TN):
Total Samples: {metrics['total_samples']}
- TP: {metrics['TP']:6d}  TN: {metrics['TN']:6d}  FP: {metrics['FP']:6d}  FN: {metrics['FN']:6d}
- Accuracy:    {metrics['accuracy']:.4f}
- Precision:   {metrics['precision']:.4f}
- Recall:      {metrics['recall']:.4f}
- Specificity: {metrics['specificity']:.4f}

"""

    with open(per_badge_summary_out, "w") as f:
        f.write(per_badge_summary)

    # --------------------------------------------------
    # Create comprehensive log file
    # --------------------------------------------------
    log_output = f"""
=== Comparison Complete ===
Output directory: {run_dir}

Files created:
  - Overall comparison: {csv_out.name}
  - Overall summary: {summary_out.name}
  - Per-badge summary: {per_badge_summary_out.name}
  - Per-badge metrics CSV: {metrics_csv.name}
  - Per-badge data files: {per_badge_dir.name}/ ({total_badges} files)

{summary}

--- Per-Badge Metrics ---
{per_badge_summary}
"""

    # Save comprehensive log
    log_out = run_dir / f"complete_log_{timestamp}.txt"
    with open(log_out, "w") as f:
        f.write(log_output)

    # --------------------------------------------------
    # Multi-class speaker-state analysis (N badges + no_speaker)
    # --------------------------------------------------
    print("\nGenerating speaker-state confusion matrix...")
    overlap_bins = speaker_df.attrs.get("overlap_bins", 0)

    labels = [f"{b}\n({person_name_map.get(b, '')})" if person_name_map.get(b) else b
              for b in badges_sorted] + ["no_speaker"]

    # Build speaker-state summary text
    speaker_summary = f"""
Speaker-State Confusion Matrix (N badges + no_speaker)
======================================================
Total 500 ms bins analysed: {len(speaker_df)}
Overlap bins resolved (primary speaker by sample count): {overlap_bins}
Overall speaker-state accuracy: {speaker_acc:.4f}

Per-class metrics:
{'Class':<20} {'TP':>6} {'FP':>6} {'FN':>6} {'TN':>7}  {'Prec':>6} {'Rec':>6} {'F1':>6}
{'-'*72}"""

    for cls in classes:
        m = speaker_class_metrics[cls]
        display = f"{cls} ({person_name_map.get(cls, '')})" if person_name_map.get(cls) else cls
        speaker_summary += (
            f"\n{display:<20} {m['TP']:>6} {m['FP']:>6} {m['FN']:>6} {m['TN']:>7}"
            f"  {m['precision']:>6.3f} {m['recall']:>6.3f} {m['f1']:>6.3f}"
        )

    speaker_summary += "\n"

    # Save speaker-state metrics CSV
    speaker_metrics_df = pd.DataFrame([
        {"class": cls, **speaker_class_metrics[cls]} for cls in classes
    ])
    speaker_metrics_csv = run_dir / f"speaker_state_metrics_{timestamp}.csv"
    speaker_metrics_df.to_csv(speaker_metrics_csv, index=False)

    # Append to summary file
    with open(summary_out, "a") as f:
        f.write(speaker_summary)

    # Chart
    chart_path = run_dir / f"badge_comparison_chart_{timestamp}.png"
    n = len(badges_sorted)
    plot_comparison_grid(
        speaker_cm, labels, chart_path,
        title=f"Badge Speaker Comparison - {n} badges ({n+1}x{n+1})\n"
              f"{manual_file.name}  vs  {auto_file.name}"
    )

    # Print to console
    print(log_output)
    print(speaker_summary)
    print(f"\n💾 Complete log saved to: {log_out.name}")
    print(f"📊 Chart saved to: {chart_path.name}")


# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    main()