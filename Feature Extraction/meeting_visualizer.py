#!/usr/bin/env python3
"""
Meeting Productivity Visualizer
================================

Loads the three feature CSVs produced by feature_extraction.py and generates
a multi-page dashboard saved as a PNG (and optionally displayed interactively).

Usage:
  python meeting_visualizer.py feature_extraction_outputs/hacksu_meeting_1/
  python meeting_visualizer.py feature_extraction_outputs/hacksu_meeting_1/ --show
  python meeting_visualizer.py feature_extraction_outputs/hacksu_meeting_1/ --out my_report.png
  python meeting_visualizer.py feature_extraction_outputs/hacksu_meeting_1/ --anonymize

Author: SCI-Lab Badge Software
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless by default; overridden if --show is passed
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Color palette — one consistent color per participant across all charts
# ---------------------------------------------------------------------------

PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B3", "#937860", "#DA8BC3", "#8C8C8C",
    "#CCB974", "#64B5CD",
]


def _anonymize(mf, pf, wf):
    """Replace real person names with Person 1, Person 2, ... sorted alphabetically."""
    real_names = sorted(pf["person_name"].unique())
    name_map   = {name: f"Person {i+1}" for i, name in enumerate(real_names)}

    pf = pf.copy()
    pf["person_name"] = pf["person_name"].map(name_map)

    mf = mf.copy()
    mf["participants"] = ", ".join(sorted(name_map.values()))

    return mf, pf, wf, name_map


def _person_colors(persons):
    """Return {person_name: hex_color} dict."""
    return {p: PALETTE[i % len(PALETTE)] for i, p in enumerate(sorted(persons))}


# ---------------------------------------------------------------------------
# Load CSVs
# ---------------------------------------------------------------------------

def load_features(folder: Path):
    required = ["meeting_features.csv", "participant_features.csv", "window_features.csv"]
    missing = [f for f in required if not (folder / f).exists()]
    if missing:
        sys.exit(f"ERROR: Missing files in {folder}: {missing}\nRun feature_extraction.py first.")

    mf = pd.read_csv(folder / "meeting_features.csv")
    pf = pd.read_csv(folder / "participant_features.csv")
    wf = pd.read_csv(folder / "window_features.csv")

    # Parse window timestamps for x-axis labels
    wf["window_start"] = pd.to_datetime(wf["window_start"])
    wf["window_label"] = wf["window_start"].dt.strftime("%-Mmin")  # e.g. "5min"
    # Windows are 0-indexed — label by elapsed minutes from meeting start
    meeting_start = wf["window_start"].min()
    wf["elapsed_min"] = ((wf["window_start"] - meeting_start).dt.total_seconds() / 60).round(1)
    wf["window_label"] = wf["elapsed_min"].astype(str) + "m"

    return mf.iloc[0], pf, wf


# ---------------------------------------------------------------------------
# Page 1: Meeting overview dashboard
# ---------------------------------------------------------------------------

def page_overview(mf, pf, wf, colors):
    fig = plt.figure(figsize=(16, 20))
    fig.patch.set_facecolor("#F8F8F8")
    gs = gridspec.GridSpec(
        4, 3,
        figure=fig,
        hspace=0.55,
        wspace=0.38,
        top=0.93, bottom=0.05,
        left=0.07, right=0.97,
    )

    meeting_id   = str(mf["meeting_id"])
    duration_min = mf["total_duration_sec"] / 60

    fig.suptitle(
        f"Meeting Productivity Report — {meeting_id}",
        fontsize=18, fontweight="bold", y=0.975,
    )
    fig.text(
        0.5, 0.955,
        f"{mf['meeting_date']}  |  {duration_min:.1f} min  |  "
        f"{int(mf['n_participants'])} participants: {mf['participants']}",
        ha="center", fontsize=10, color="#555555",
    )

    # -----------------------------------------------------------------------
    # (0,0) Speaking vs Silence donut
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    speak_pct  = mf["speaking_ratio"] * 100
    silence_pct = mf["silence_ratio"] * 100
    wedges, texts, autotexts = ax.pie(
        [speak_pct, silence_pct],
        labels=["Speaking", "Silence"],
        colors=["#4C72B0", "#DDDDDD"],
        autopct="%1.1f%%",
        startangle=90,
        wedgeprops={"width": 0.55, "edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 10},
    )
    for at in autotexts:
        at.set_fontsize(9)
    ax.set_title("Speaking Activity", fontsize=11, fontweight="bold", pad=10)

    # -----------------------------------------------------------------------
    # (0,1) Participation quality gauges (text panel)
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    ax.axis("off")

    metrics = [
        ("Gini Coefficient",       f"{mf['gini_speaking_time']:.3f}",
         "0 = perfectly equal, 1 = one person dominates"),
        ("Participation Entropy",  f"{mf['participation_entropy']:.3f}",
         "0 = one speaker, 1 = perfectly balanced"),
        ("Dominant Speaker",       f"{mf['dominant_speaker_fraction']*100:.1f}%",
         "Fraction of speaking time by top speaker"),
        ("Back-to-Back Turns",     f"{mf['back_to_back_ratio']*100:.1f}%",
         "Turns with no silence gap before them"),
        ("Turns / Minute",         f"{mf['turns_per_minute']:.2f}",
         "Pace of conversation"),
        ("Mean Turn Duration",     f"{mf['mean_turn_duration_sec']:.1f}s",
         "Average floor-hold length"),
    ]

    y = 0.95
    for label, value, note in metrics:
        ax.text(0.0, y, label,        fontsize=9,  fontweight="bold", transform=ax.transAxes)
        ax.text(0.62, y, value,       fontsize=11, fontweight="bold",
                color="#2060A0", transform=ax.transAxes)
        ax.text(0.0, y - 0.07, note, fontsize=7.5, color="#777777", transform=ax.transAxes)
        y -= 0.175

    ax.set_title("Meeting Metrics", fontsize=11, fontweight="bold")
    ax.add_patch(mpatches.FancyBboxPatch(
        (-0.02, 0), 1.04, 1.02,
        boxstyle="round,pad=0.02",
        facecolor="#EEEEFF", edgecolor="#BBBBDD", linewidth=1,
        transform=ax.transAxes, zorder=0,
    ))

    # -----------------------------------------------------------------------
    # (0,2) Turn count by participant (horizontal bar)
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[0, 2])
    pf_sorted = pf.sort_values("n_turns", ascending=True)
    bar_colors = [colors[p] for p in pf_sorted["person_name"]]
    bars = ax.barh(pf_sorted["person_name"], pf_sorted["n_turns"],
                   color=bar_colors, edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, pf_sorted["n_turns"]):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                str(int(val)), va="center", fontsize=9)
    ax.set_xlabel("Number of Turns", fontsize=9)
    ax.set_title("Turns per Person", fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    # -----------------------------------------------------------------------
    # (1,0-1) Speaking time per participant (horizontal bar, spans 2 cols)
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[1, 0:2])
    pf_sorted = pf.sort_values("speaking_sec", ascending=True)
    bar_colors = [colors[p] for p in pf_sorted["person_name"]]
    bars = ax.barh(pf_sorted["person_name"], pf_sorted["speaking_sec"] / 60,
                   color=bar_colors, edgecolor="white", linewidth=0.8)
    for bar, row in zip(bars, pf_sorted.itertuples()):
        mins = row.speaking_sec / 60
        pct  = row.speaking_fraction * 100
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"{mins:.1f}m  ({pct:.1f}%)", va="center", fontsize=9)
    ax.set_xlabel("Speaking Time (minutes)", fontsize=9)
    ax.set_title("Speaking Time per Person", fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    # -----------------------------------------------------------------------
    # (1,2) Mean turn duration per participant
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[1, 2])
    pf_sorted2 = pf.sort_values("mean_turn_duration_sec", ascending=True)
    bar_colors2 = [colors[p] for p in pf_sorted2["person_name"]]
    bars = ax.barh(pf_sorted2["person_name"], pf_sorted2["mean_turn_duration_sec"],
                   color=bar_colors2, edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, pf_sorted2["mean_turn_duration_sec"]):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}s", va="center", fontsize=9)
    ax.set_xlabel("Seconds", fontsize=9)
    ax.set_title("Mean Turn Duration", fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    # -----------------------------------------------------------------------
    # (2,0) Interruptions given vs received (scatter)
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[2, 0])
    for _, row in pf.iterrows():
        ax.scatter(row["n_turns_interrupting"], row["n_turns_interrupted"],
                   color=colors[row["person_name"]], s=120, zorder=3,
                   edgecolors="white", linewidths=1)
        ax.annotate(row["person_name"],
                    (row["n_turns_interrupting"], row["n_turns_interrupted"]),
                    textcoords="offset points", xytext=(5, 3), fontsize=8)
    max_val = max(
        pf[["n_turns_interrupting", "n_turns_interrupted"]].max().max(), 1
    ) + 1
    ax.plot([0, max_val], [0, max_val], "--", color="#AAAAAA", linewidth=1, zorder=0)
    ax.set_xlabel("Turns Interrupting Others", fontsize=9)
    ax.set_ylabel("Turns Interrupted by Others", fontsize=9)
    ax.set_title("Interruption Balance\n(above diagonal = interrupted more)", fontsize=10, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    # -----------------------------------------------------------------------
    # (2,1) Response latency per participant
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[2, 1])
    pf_rl = pf.dropna(subset=["response_latency_mean_sec"]).sort_values(
        "response_latency_mean_sec", ascending=True
    )
    bar_colors_rl = [colors[p] for p in pf_rl["person_name"]]
    bars = ax.barh(pf_rl["person_name"], pf_rl["response_latency_mean_sec"],
                   color=bar_colors_rl, edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, pf_rl["response_latency_mean_sec"]):
        ax.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2,
                f"{val:.2f}s", va="center", fontsize=9)
    ax.set_xlabel("Seconds", fontsize=9)
    ax.set_title("Mean Response Latency\n(after another speaker stops)", fontsize=10, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    # -----------------------------------------------------------------------
    # (2,2) First turn time (when did each person first speak?)
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[2, 2])
    pf_ft = pf.dropna(subset=["first_turn_time_sec"]).sort_values(
        "first_turn_time_sec", ascending=False
    )
    bar_colors_ft = [colors[p] for p in pf_ft["person_name"]]
    bars = ax.barh(pf_ft["person_name"], pf_ft["first_turn_time_sec"] / 60,
                   color=bar_colors_ft, edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, pf_ft["first_turn_time_sec"] / 60):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}m", va="center", fontsize=9)
    ax.set_xlabel("Minutes into meeting", fontsize=9)
    ax.set_title("Time of First Turn\n(later = slower to engage)", fontsize=10, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    # -----------------------------------------------------------------------
    # (3,0-2) Stacked area: per-person speaking time over windows
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[3, :])

    # Map badge names to person names
    badge_to_person = pf.set_index("badge_name")["person_name"].to_dict()
    speaking_cols = [c for c in wf.columns if c.startswith("speaking_sec_")]
    x = wf["elapsed_min"].values

    bottom = np.zeros(len(wf))
    for col in speaking_cols:
        badge = col.replace("speaking_sec_", "")
        person = badge_to_person.get(badge, badge)
        values = wf[col].fillna(0).values
        ax.fill_between(x, bottom, bottom + values,
                        alpha=0.85, color=colors.get(person, "#AAAAAA"),
                        label=person, step="post")
        bottom += values

    ax.set_xlim(x[0], x[-1] + (x[-1] - x[0]) / len(x))
    ax.set_xlabel("Elapsed Time (minutes)", fontsize=9)
    ax.set_ylabel("Speaking Time (sec per window)", fontsize=9)
    ax.set_title("Speaking Time by Person Over Meeting Duration", fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9, ncol=min(len(colors), 6),
              framealpha=0.7, edgecolor="#CCCCCC")
    ax.spines[["top", "right"]].set_visible(False)

    return fig


# ---------------------------------------------------------------------------
# Page 2: Timeline deep-dive
# ---------------------------------------------------------------------------

def page_timeline(mf, pf, wf, colors):
    fig = plt.figure(figsize=(16, 18))
    fig.patch.set_facecolor("#F8F8F8")
    gs = gridspec.GridSpec(
        4, 2,
        figure=fig,
        hspace=0.5,
        wspace=0.35,
        top=0.93, bottom=0.05,
        left=0.07, right=0.97,
    )

    meeting_id = str(mf["meeting_id"])
    fig.suptitle(
        f"Meeting Timeline — {meeting_id}",
        fontsize=18, fontweight="bold", y=0.975,
    )

    x = wf["elapsed_min"].values
    x_ticks = x
    x_labels = [f"{v:.0f}m" for v in x]

    def _style(ax, title, ylabel):
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_xlabel("Elapsed Time (minutes)", fontsize=9)
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(x_labels, fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlim(x[0] - 0.5, x[-1] + 0.5)

    # -----------------------------------------------------------------------
    # (0,0) Speaking ratio timeline
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    ax.fill_between(x, wf["speaking_ratio"] * 100, alpha=0.3, color="#4C72B0", step="post")
    ax.step(x, wf["speaking_ratio"] * 100, color="#4C72B0", linewidth=2, where="post")
    ax.axhline(mf["speaking_ratio"] * 100, color="#4C72B0", linestyle="--",
               linewidth=1, alpha=0.6, label=f"avg {mf['speaking_ratio']*100:.1f}%")
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter())
    ax.legend(fontsize=8)
    _style(ax, "Speaking Activity Over Time", "% of window speaking")

    # -----------------------------------------------------------------------
    # (0,1) Turns per minute timeline
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    ax.fill_between(x, wf["turns_per_minute"], alpha=0.3, color="#DD8452", step="post")
    ax.step(x, wf["turns_per_minute"], color="#DD8452", linewidth=2, where="post")
    ax.axhline(mf["turns_per_minute"], color="#DD8452", linestyle="--",
               linewidth=1, alpha=0.6, label=f"avg {mf['turns_per_minute']:.2f}")
    ax.legend(fontsize=8)
    _style(ax, "Conversation Pace (Turns/Min)", "turns per minute")

    # -----------------------------------------------------------------------
    # (1,0) Gini coefficient over time
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[1, 0])
    gini_vals = wf["gini_speaking_time"].ffill()
    ax.fill_between(x, gini_vals, alpha=0.25, color="#C44E52", step="post")
    ax.step(x, gini_vals, color="#C44E52", linewidth=2, where="post")
    ax.axhline(mf["gini_speaking_time"], color="#C44E52", linestyle="--",
               linewidth=1, alpha=0.6, label=f"avg {mf['gini_speaking_time']:.3f}")
    ax.set_ylim(0, 1)
    ax.axhspan(0.0, 0.2, alpha=0.06, color="green")
    ax.axhspan(0.4, 1.0, alpha=0.06, color="red")
    ax.text(x[-1] + 0.2, 0.1, "equal",  fontsize=7, color="green", va="center")
    ax.text(x[-1] + 0.2, 0.7, "skewed", fontsize=7, color="red",   va="center")
    ax.legend(fontsize=8)
    _style(ax, "Participation Inequality (Gini)", "Gini coefficient")

    # -----------------------------------------------------------------------
    # (1,1) Participation entropy over time
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[1, 1])
    ent_vals = wf["participation_entropy"].ffill()
    ax.fill_between(x, ent_vals, alpha=0.25, color="#55A868", step="post")
    ax.step(x, ent_vals, color="#55A868", linewidth=2, where="post")
    ax.axhline(mf["participation_entropy"], color="#55A868", linestyle="--",
               linewidth=1, alpha=0.6, label=f"avg {mf['participation_entropy']:.3f}")
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)
    _style(ax, "Participation Balance (Entropy)", "normalized entropy (1 = perfectly equal)")

    # -----------------------------------------------------------------------
    # (2,0) Active participants per window
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[2, 0])
    n_p = int(mf["n_participants"])
    bar_colors_w = [
        "#55A868" if v == n_p else ("#DD8452" if v >= n_p / 2 else "#C44E52")
        for v in wf["n_active_participants"].fillna(0)
    ]
    ax.bar(x, wf["n_active_participants"].fillna(0), color=bar_colors_w,
           width=(x[1] - x[0]) * 0.7 if len(x) > 1 else 1, edgecolor="white")
    ax.axhline(n_p, color="#555555", linestyle="--", linewidth=1, alpha=0.5,
               label=f"total participants ({n_p})")
    ax.set_ylim(0, n_p + 1)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.legend(fontsize=8)
    _style(ax, "Active Participants per Window", "unique speakers")

    # -----------------------------------------------------------------------
    # (2,1) Mean turn duration over time
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[2, 1])
    ax.fill_between(x, wf["mean_turn_duration_sec"].fillna(0), alpha=0.25,
                    color="#8172B3", step="post")
    ax.step(x, wf["mean_turn_duration_sec"].fillna(0), color="#8172B3",
            linewidth=2, where="post")
    ax.axhline(mf["mean_turn_duration_sec"], color="#8172B3", linestyle="--",
               linewidth=1, alpha=0.6, label=f"avg {mf['mean_turn_duration_sec']:.1f}s")
    ax.legend(fontsize=8)
    _style(ax, "Mean Turn Duration Over Time", "seconds")

    # -----------------------------------------------------------------------
    # (3,0-1) Per-person speaking time per window (grouped bar)
    # -----------------------------------------------------------------------
    ax = fig.add_subplot(gs[3, :])
    badge_to_person = pf.set_index("badge_name")["person_name"].to_dict()
    speaking_cols   = [c for c in wf.columns if c.startswith("speaking_sec_")]
    n_persons = len(speaking_cols)
    bar_width = 0.8 / n_persons
    window_range = np.arange(len(wf))

    for i, col in enumerate(speaking_cols):
        badge  = col.replace("speaking_sec_", "")
        person = badge_to_person.get(badge, badge)
        offset = (i - n_persons / 2 + 0.5) * bar_width
        ax.bar(
            window_range + offset,
            wf[col].fillna(0) / 60,
            width=bar_width * 0.9,
            color=colors.get(person, "#AAAAAA"),
            label=person,
            edgecolor="white",
            linewidth=0.5,
        )

    ax.set_xticks(window_range)
    ax.set_xticklabels(x_labels, fontsize=8)
    ax.set_xlabel("Elapsed Time (minutes)", fontsize=9)
    ax.set_ylabel("Speaking Time (minutes)", fontsize=9)
    ax.set_title("Speaking Time per Person per Window", fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9, ncol=min(n_persons, 6),
              framealpha=0.7, edgecolor="#CCCCCC")
    ax.spines[["top", "right"]].set_visible(False)

    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Visualize meeting productivity features from feature_extraction.py outputs."
    )
    parser.add_argument(
        "feature_dir", type=Path,
        help="Folder containing meeting_features.csv, participant_features.csv, window_features.csv",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Output PNG path (default: <feature_dir>/meeting_dashboard.png)",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Display charts interactively after saving.",
    )
    parser.add_argument(
        "--anonymize", action="store_true",
        help="Replace participant names with Person 1, Person 2, etc.",
    )
    args = parser.parse_args()

    if not args.feature_dir.exists():
        sys.exit(f"ERROR: Directory not found: {args.feature_dir}")

    mf, pf, wf = load_features(args.feature_dir)

    if args.anonymize:
        mf, pf, wf, name_map = _anonymize(mf, pf, wf)
        print(f"  Anonymized: {name_map}")

    persons = pf["person_name"].unique()
    colors  = _person_colors(persons)

    print(f"Building charts for {mf['meeting_id']} ...")

    if args.show:
        matplotlib.use("TkAgg")

    fig1 = page_overview(mf, pf, wf, colors)
    fig2 = page_timeline(mf, pf, wf, colors)

    out_path = args.out or (args.feature_dir / "meeting_dashboard.png")

    # Save both pages as a tall combined PNG
    from matplotlib.backends.backend_pdf import PdfPages
    pdf_path = out_path.with_suffix(".pdf")
    with PdfPages(pdf_path) as pdf:
        pdf.savefig(fig1, bbox_inches="tight", dpi=150)
        pdf.savefig(fig2, bbox_inches="tight", dpi=150)

    # Also save page 1 as the quick-view PNG
    fig1.savefig(out_path, bbox_inches="tight", dpi=150)

    print(f"Saved PNG : {out_path}")
    print(f"Saved PDF : {pdf_path}  (both pages)")

    if args.show:
        plt.show()

    plt.close("all")


if __name__ == "__main__":
    main()
