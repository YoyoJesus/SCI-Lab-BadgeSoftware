#!/usr/bin/env python3
"""
Badge Data Stitcher
===================

Combines multiple badge data CSV files into a single file.

- Handles files where Badge_Name -> Person_Name differs per session
- Prompts for names on any file missing them
- Adds a Session column so rows can be traced back to their source file
- Output goes to processed_data/stitched/

Author: Badge Stitcher
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox


OUTPUT_DIR = Path("processed_data") / "stitched"


def select_files():
    root = tk.Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(
        title="Select badge data CSV files to stitch (select multiple)",
        filetypes=[("CSV files", "*.csv")]
    )
    root.destroy()
    return [Path(p) for p in paths]


def collect_names_for_badges(badges_without_names, file_label):
    """Ask the user for person names for badges that have none."""
    mapping = {}
    for badge in sorted(badges_without_names):
        root = tk.Tk()
        root.withdraw()
        name = simpledialog.askstring(
            "Person Name",
            f"[{file_label}]\nEnter name for {badge} (leave blank to skip):"
        )
        root.destroy()
        mapping[badge] = (name.strip() if name and name.strip() else "")
    return mapping


def load_file(path, session_index):
    """Load one CSV, fill/collect Person_Name, add Session column."""
    print(f"\nLoading [{session_index}] {path.name} ...")
    df = pd.read_csv(path)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])

    # Remove exact duplicates
    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        print(f"  Removed {before - len(df)} duplicate rows")

    # Ensure Person_Name column exists
    if "Person_Name" not in df.columns:
        df["Person_Name"] = ""

    # Determine which badges are missing names
    badges_without_names = []
    for badge in df["Badge_Name"].unique():
        badge_names = df.loc[df["Badge_Name"] == badge, "Person_Name"].dropna()
        badge_names = badge_names[badge_names.str.strip() != ""]
        if badge_names.empty:
            badges_without_names.append(badge)

    if badges_without_names:
        print(f"  Badges missing names: {badges_without_names}")
        root = tk.Tk()
        root.withdraw()
        assign = messagebox.askyesno(
            "Missing Names",
            f"[{path.name}]\n\nBadges without names:\n"
            + "\n".join(f"  - {b}" for b in sorted(badges_without_names))
            + "\n\nAssign names now?"
        )
        root.destroy()

        if assign:
            name_map = collect_names_for_badges(badges_without_names, path.name)
            for badge, name in name_map.items():
                if name:
                    df.loc[df["Badge_Name"] == badge, "Person_Name"] = name
                    print(f"  {badge} -> {name}")

    # Show final badge/name summary for this file
    print("  Badge assignments:")
    for badge in sorted(df["Badge_Name"].unique()):
        names = df.loc[df["Badge_Name"] == badge, "Person_Name"].dropna()
        names = names[names.str.strip() != ""]
        person = names.iloc[0] if not names.empty else "(unnamed)"
        print(f"    {badge}: {person}")

    df["Session"] = path.stem
    return df


def stitch(files):
    frames = []
    for i, path in enumerate(files, start=1):
        df = load_file(path, i)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["Timestamp", "Badge_Name"]).reset_index(drop=True)

    print(f"\nTotal rows after stitching: {len(combined):,}")
    print(f"Sessions: {combined['Session'].nunique()}")
    print(f"Time range: {combined['Timestamp'].min()} to {combined['Timestamp'].max()}")
    print("\nPer-session row counts:")
    for session, count in combined.groupby("Session").size().items():
        print(f"  {session}: {count:,} rows")

    return combined


def save(combined):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    root = tk.Tk()
    root.withdraw()
    filename = simpledialog.askstring(
        "Output File Name",
        "Enter output file name (without .csv):",
        initialvalue=f"stitched_{timestamp}"
    )
    root.destroy()

    if not filename or not filename.strip():
        filename = f"stitched_{timestamp}"

    out_path = OUTPUT_DIR / f"{filename.strip()}.csv"
    combined.to_csv(out_path, index=False)
    print(f"\nSaved to: {out_path}")
    return out_path


def main():
    print("=== Badge Data Stitcher ===\n")

    files = select_files()
    if not files:
        print("No files selected. Exiting.")
        return

    print(f"Selected {len(files)} file(s):")
    for f in files:
        print(f"  {f.name}")

    combined = stitch(files)
    out_path = save(combined)

    print("\nDone.")
    print(f"Output: {out_path}")
    print(f"Rows:   {len(combined):,}")
    print(f"Badges: {sorted(combined['Badge_Name'].unique())}")


if __name__ == "__main__":
    main()
