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

    manual_df = manual_df[["Timestamp", "Badge_Name", "manual_label"]]
    auto_df = auto_df[["Timestamp", "Badge_Name", "auto_label"]]

    # --------------------------------------------------
    # Align datasets
    # --------------------------------------------------
    merged = pd.merge(
        manual_df,
        auto_df,
        on=["Timestamp", "Badge_Name"],
        how="inner"
    )

    merged["label_match"] = merged["manual_label"] == merged["auto_label"]

    # --------------------------------------------------
    # Metrics
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
    # Output
    # --------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    base_dir = Path("processed_data") / "label_comparison"
    run_dir = base_dir / f"comparison_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    csv_out = run_dir / f"label_comparison_{timestamp}.csv"
    summary_out = run_dir / f"summary_{timestamp}.txt"

    merged.to_csv(csv_out, index=False)

    summary = f"""
Label Comparison Summary
========================
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Input files:
- Manual: {manual_file.name}
- Auto:   {auto_file.name}

Row counts:
- Manual rows: {len(manual_df)}
- Auto rows:   {len(auto_df)}
- Compared rows (aligned): {len(merged)}
- Dropped rows: {len(manual_df) + len(auto_df) - 2 * len(merged)}

Confusion Matrix (Manual = Ground Truth):
- True Positives (TP): {TP}
- True Negatives (TN): {TN}
- False Positives (FP): {FP}
- False Negatives (FN): {FN}

Metrics:
- Accuracy:    {accuracy:.4f}
- Precision:   {precision:.4f}
- Recall:      {recall:.4f}
- Specificity: {specificity:.4f}
"""

    with open(summary_out, "w") as f:
        f.write(summary)

    print("\n=== Comparison Complete ===")
    print(f"Output directory: {run_dir}")
    print(summary)


# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    main()