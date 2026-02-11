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
            "specificity": spec
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

OVERALL Confusion Matrix (Manual = Ground Truth):
- True Positives (TP): {TP}
- True Negatives (TN): {TN}
- False Positives (FP): {FP}
- False Negatives (FN): {FN}

OVERALL Metrics:
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
Total Samples: {metrics['total_samples']}

Confusion Matrix:
- True Positives (TP):  {metrics['TP']:4d}
- True Negatives (TN):  {metrics['TN']:4d}
- False Positives (FP): {metrics['FP']:4d}
- False Negatives (FN): {metrics['FN']:4d}

Metrics:
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

    # Print to console
    print(log_output)
    print(f"\n💾 Complete log saved to: {log_out.name}")


# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    main()