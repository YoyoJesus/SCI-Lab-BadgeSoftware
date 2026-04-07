"""
weka_visualizer.py
Parses Weka classifier text output and produces clean visualizations.

Usage:
    python weka_visualizer.py <weka_output.txt>
    python weka_visualizer.py  (reads from clipboard / stdin prompt)
"""

import sys
import re
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np
from mpl_toolkits.axes_grid1 import make_axes_locatable


# ── Parsing helpers ───────────────────────────────────────────────────────────

def parse_run_info(text):
    info = {}
    for key, pattern in [
        ("scheme",    r"Scheme:\s+(.+)"),
        ("relation",  r"Relation:\s+(.+)"),
        ("instances", r"Instances:\s+(\d+)"),
        ("attributes",r"Attributes:\s+(\d+)"),
        ("test_mode", r"Test mode:\s+(.+)"),
    ]:
        m = re.search(pattern, text)
        if m:
            info[key] = m.group(1).strip()
    return info


def parse_summary(text):
    summary = {}
    patterns = {
        "correct_pct":   r"Correctly Classified Instances\s+\d+\s+([\d.]+)\s*%",
        "incorrect_pct": r"Incorrectly Classified Instances\s+\d+\s+([\d.]+)\s*%",
        "kappa":         r"Kappa statistic\s+([\d.]+)",
        "mae":           r"Mean absolute error\s+([\d.]+)",
        "rmse":          r"Root mean squared error\s+([\d.]+)",
        "rae":           r"Relative absolute error\s+([\d.]+)\s*%",
        "rrse":          r"Root relative squared error\s+([\d.]+)\s*%",
        "n_instances":   r"Total Number of Instances\s+(\d+)",
        "build_time":    r"Time taken to build model:\s+([\d.]+)\s+seconds",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            summary[key] = float(m.group(1))
    return summary


def parse_class_accuracy(text):
    """Returns list of dicts, one per class row."""
    section = re.search(
        r"=== Detailed Accuracy By Class ===(.*?)(?===|\Z)", text, re.DOTALL
    )
    if not section:
        return []

    rows = []
    # Header line identifies columns; data lines start with a float
    for line in section.group(1).splitlines():
        parts = line.split()
        # data rows: TP FP Precision Recall F-Measure MCC ROC PRC Class
        if len(parts) >= 9:
            try:
                float(parts[0])
                rows.append({
                    "tp_rate":    float(parts[0]),
                    "fp_rate":    float(parts[1]),
                    "precision":  float(parts[2]),
                    "recall":     float(parts[3]),
                    "f_measure":  float(parts[4]),
                    "mcc":        float(parts[5]),
                    "roc_area":   float(parts[6]),
                    "prc_area":   float(parts[7]),
                    "class":      parts[8],
                })
            except ValueError:
                continue
    return rows


def parse_confusion_matrix(text):
    section = re.search(
        r"=== Confusion Matrix ===(.*?)(?===|\Z)", text, re.DOTALL
    )
    if not section:
        return None, []

    lines = [l for l in section.group(1).splitlines() if l.strip()]
    matrix, labels = [], []
    for line in lines:
        # e.g.  " 2 1 0 | a = low"
        m = re.match(r"\s*([\d\s]+)\|\s*(\w+)\s*=\s*(\w+)", line)
        if m:
            matrix.append([int(x) for x in m.group(1).split()])
            labels.append(m.group(3))   # human-readable label
    return np.array(matrix) if matrix else None, labels


def parse_node_weights(text):
    """
    Returns dict: node_id -> {threshold, weights: {attrib: value}}
    Only parses input-layer nodes (those with Attrib lines).
    """
    nodes = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"Sigmoid Node (\d+)", line)
        if m:
            current = int(m.group(1))
            nodes[current] = {"threshold": None, "weights": {}}
            continue
        if current is None:
            continue
        t = re.match(r"\s+Threshold\s+([-\d.E]+)", line)
        if t:
            nodes[current]["threshold"] = float(t.group(1))
            continue
        a = re.match(r"\s+Attrib (\S+)\s+([-\d.E]+)", line)
        if a:
            nodes[current]["weights"][a.group(1)] = float(a.group(2))
    # Keep only nodes that have attribute weights (hidden nodes)
    return {k: v for k, v in nodes.items() if v["weights"]}


# ── Plot helpers ──────────────────────────────────────────────────────────────

COLORS = {
    "correct": "#4CAF50",
    "incorrect": "#F44336",
    "bar_palette": ["#2196F3", "#FF9800", "#9C27B0", "#00BCD4", "#E91E63",
                    "#8BC34A", "#FF5722", "#607D8B"],
    "heatmap_pos": "RdYlGn",
    "heatmap_conf": "Blues",
}


def fig_summary_card(info, summary, ax):
    """Render a text-based summary card on the given axes."""
    ax.axis("off")
    scheme_short = info.get("scheme", "").split()[0].split(".")[-1]

    lines = [
        ("Classifier",   scheme_short),
        ("Relation",     info.get("relation", "?")),
        ("Instances",    info.get("instances", "?")),
        ("Attributes",   info.get("attributes", "?")),
        ("Test mode",    info.get("test_mode", "?")),
        ("Build time",   f"{summary.get('build_time', '?')} s"),
        ("", ""),
        ("Accuracy",     f"{summary.get('correct_pct', '?'):.1f}%"),
        ("Kappa",        f"{summary.get('kappa', '?'):.4f}"),
        ("MAE",          f"{summary.get('mae', '?'):.4f}"),
        ("RMSE",         f"{summary.get('rmse', '?'):.4f}"),
    ]

    # Title sits clearly above the rows
    ax.text(0.5, 1.0, "Run Summary", transform=ax.transAxes,
            ha="center", va="top", fontsize=13, fontweight="bold")

    y = 0.88  # first row starts well below the title

    for label, value in lines:
        if label == "":
            y -= 0.03
            continue
        ax.text(0.02, y, label + ":", transform=ax.transAxes,
                ha="left", va="top", fontsize=9, color="#555555")
        ax.text(0.98, y, str(value), transform=ax.transAxes,
                ha="right", va="top", fontsize=9, fontweight="bold")
        y -= 0.075

    # Accuracy gauge (simple horizontal bar)
    acc = summary.get("correct_pct", 0) / 100
    bar_y = 0.05
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.02, bar_y), 0.96, 0.04,
        boxstyle="round,pad=0.01", linewidth=1,
        edgecolor="#cccccc", facecolor="#eeeeee",
        transform=ax.transAxes, clip_on=False
    ))
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.02, bar_y), 0.96 * acc, 0.04,
        boxstyle="round,pad=0.01", linewidth=0,
        facecolor=COLORS["correct"],
        transform=ax.transAxes, clip_on=False
    ))
    ax.text(0.5, bar_y + 0.02, f"{summary.get('correct_pct', 0):.1f}% correct",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=8, color="white", fontweight="bold")


def fig_per_class_metrics(class_rows, ax):
    if not class_rows:
        ax.axis("off")
        ax.text(0.5, 0.5, "No class data", ha="center", va="center")
        return

    metrics = ["tp_rate", "precision", "recall", "f_measure", "roc_area", "mcc"]
    labels  = ["TP Rate", "Precision", "Recall", "F-Measure", "ROC Area", "MCC"]
    classes = [r["class"] for r in class_rows]
    n_cls   = len(classes)
    n_met   = len(metrics)

    x = np.arange(n_met)
    width = 0.8 / n_cls

    for i, row in enumerate(class_rows):
        vals = [row[m] for m in metrics]
        offset = (i - n_cls / 2 + 0.5) * width
        bars = ax.bar(x + offset, vals, width,
                      label=row["class"],
                      color=COLORS["bar_palette"][i % len(COLORS["bar_palette"])],
                      edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.005,
                    f"{val:.2f}", ha="center", va="bottom",
                    fontsize=6, rotation=0)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.22)
    ax.set_ylabel("Score")
    ax.set_title("Per-Class Performance Metrics", fontweight="bold")
    ax.legend(title="Class", fontsize=8, title_fontsize=8)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)


def fig_confusion_matrix(matrix, labels, ax):
    if matrix is None:
        ax.axis("off")
        ax.text(0.5, 0.5, "No confusion matrix", ha="center", va="center")
        return

    n = len(labels)
    # Normalise row-wise for colour, display raw counts as text
    with np.errstate(divide="ignore", invalid="ignore"):
        norm = matrix.astype(float) / matrix.sum(axis=1, keepdims=True)
        norm = np.nan_to_num(norm)

    im = ax.imshow(norm, cmap=COLORS["heatmap_conf"], vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Predicted", fontsize=9)
    ax.set_ylabel("Actual", fontsize=9)
    ax.set_title("Confusion Matrix", fontweight="bold")

    for i in range(n):
        for j in range(n):
            text_color = "white" if norm[i, j] > 0.55 else "black"
            ax.text(j, i, str(matrix[i, j]),
                    ha="center", va="center",
                    fontsize=13, fontweight="bold", color=text_color)

    # Attach colorbar strictly to this axes so it doesn't bleed into neighbours
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="8%", pad=0.08)
    plt.colorbar(im, cax=cax, label="Row-normalised")


def fig_weight_heatmap(nodes, ax):
    if not nodes:
        ax.axis("off")
        ax.text(0.5, 0.5, "No weight data", ha="center", va="center")
        return

    # Collect all attribute names (same across all hidden nodes)
    sample_node = next(iter(nodes.values()))
    attribs = list(sample_node["weights"].keys())
    node_ids = sorted(nodes.keys())

    matrix = np.array([
        [nodes[nid]["weights"].get(a, 0) for a in attribs]
        for nid in node_ids
    ])

    # Shorten attribute names for readability
    short_attribs = [a.replace("part_mean_interruption_ratio_suffered",  "pm.int.suf")
                      .replace("part_mean_interruption_ratio_initiated", "pm.int.ini")
                      .replace("part_std_interruption_ratio_suffered",   "ps.int.suf")
                      .replace("part_std_interruption_ratio_initiated",  "ps.int.ini")
                      .replace("part_mean_response_latency_mean_sec",    "pm.resp.lat")
                      .replace("part_std_response_latency_mean_sec",     "ps.resp.lat")
                      .replace("part_mean_self_succession_count",        "pm.self.suc")
                      .replace("part_std_self_succession_count",         "ps.self.suc")
                      .replace("part_mean_mean_turn_duration_sec",       "pm.turn.dur")
                      .replace("part_std_mean_turn_duration_sec",        "ps.turn.dur")
                      .replace("part_mean_speaking_fraction",            "pm.spk.frac")
                      .replace("part_std_speaking_fraction",             "ps.spk.frac")
                      .replace("part_mean_micro_turn_ratio",             "pm.micro")
                      .replace("part_std_micro_turn_ratio",              "ps.micro")
                      .replace("win_slope_speaking_ratio",               "wslp.spk")
                      .replace("win_std_speaking_ratio",                 "wstd.spk")
                      .replace("win_slope_gini_speaking_time",           "wslp.gini")
                      .replace("win_std_gini_speaking_time",             "wstd.gini")
                      .replace("win_slope_turns_per_minute",             "wslp.tpm")
                      .replace("win_std_turns_per_minute",               "wstd.tpm")
                      .replace("win_slope_n_active_participants",        "wslp.nact")
                      .replace("win_std_n_active_participants",          "wstd.nact")
                      .replace("win_slope_back_to_back_ratio",           "wslp.b2b")
                      .replace("win_std_back_to_back_ratio",             "wstd.b2b")
                      .replace("median_turn_duration_sec",               "med.turn.dur")
                      .replace("mean_turn_duration_sec",                 "mean.turn.dur")
                      .replace("dominant_speaker_fraction",              "dom.spk.frac")
                      .replace("participation_entropy",                  "part.entropy")
                      .replace("n_active_participants",                  "n.active")
                      .replace("gini_speaking_time",                     "gini.spk")
                      .replace("speaking_ratio",                         "spk.ratio")
                      .replace("silence_ratio",                          "sil.ratio")
                      .replace("turns_per_minute",                       "tpm")
                      .replace("back_to_back_ratio",                     "b2b.ratio")
                      .replace("mean_gap_sec",                           "gap.sec")
                      .replace("micro_turn_ratio",                       "micro.ratio")
                      for a in attribs]

    vmax = np.abs(matrix).max()
    im = ax.imshow(matrix, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(attribs)))
    ax.set_xticklabels(short_attribs, rotation=90, ha="center", fontsize=5.5)
    ax.set_yticks(range(len(node_ids)))
    ax.set_yticklabels([f"Node {n}" for n in node_ids], fontsize=7)
    ax.set_title("Hidden Node Feature Weights", fontweight="bold")
    plt.colorbar(im, ax=ax, fraction=0.02, pad=0.02, label="Weight")


def fig_top_features(nodes, ax, top_n=15):
    """Bar chart of mean |weight| across all hidden nodes per feature."""
    if not nodes:
        ax.axis("off")
        return

    sample_node = next(iter(nodes.values()))
    attribs = list(sample_node["weights"].keys())

    mean_abs = {}
    for a in attribs:
        vals = [abs(nodes[nid]["weights"].get(a, 0)) for nid in nodes]
        mean_abs[a] = np.mean(vals)

    sorted_items = sorted(mean_abs.items(), key=lambda x: x[1], reverse=True)[:top_n]
    values = [v for _, v in sorted_items]

    def shorten(name):
        return (name
                .replace("part_mean_", "pm.")
                .replace("part_std_",  "ps.")
                .replace("win_slope_", "wslp.")
                .replace("win_std_",   "wstd.")
                .replace("_ratio",     " ratio")
                .replace("_sec",       " sec")
                .replace("_count",     " cnt")
                .replace("_duration",  " dur")
                .replace("_", " "))

    names = [shorten(k) for k, _ in sorted_items]

    colors = plt.cm.viridis(np.linspace(0.2, 0.85, len(values)))
    bars = ax.barh(range(len(values)), values, color=colors, edgecolor="white")
    ax.set_yticks(range(len(values)))
    ax.set_yticklabels(names, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("Mean |Weight|")
    ax.set_title(f"Top {top_n} Most Influential Features\n(mean |weight| across hidden nodes)",
                 fontweight="bold")
    ax.xaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=7)


# ── Main layout ───────────────────────────────────────────────────────────────

def build_dashboard(text, title="Weka Classifier Results"):
    info    = parse_run_info(text)
    summary = parse_summary(text)
    classes = parse_class_accuracy(text)
    matrix, labels = parse_confusion_matrix(text)
    nodes   = parse_node_weights(text)

    fig = plt.figure(figsize=(18, 14))
    fig.patch.set_facecolor("#F5F5F5")
    fig.suptitle(title, fontsize=16, fontweight="bold", y=0.98)

    gs = gridspec.GridSpec(
        3, 3,
        figure=fig,
        hspace=0.50, wspace=0.40,
        left=0.07, right=0.97, top=0.93, bottom=0.05,
    )

    # Row 0 left: summary card
    ax_card = fig.add_subplot(gs[0, 0])
    fig_summary_card(info, summary, ax_card)

    # Row 0 middle+right: per-class metrics
    ax_cls = fig.add_subplot(gs[0, 1:])
    fig_per_class_metrics(classes, ax_cls)

    # Row 1 left: confusion matrix
    ax_cm = fig.add_subplot(gs[1, 0])
    fig_confusion_matrix(matrix, labels, ax_cm)

    # Row 1 middle+right: top feature importance
    ax_top = fig.add_subplot(gs[1, 1:])
    fig_top_features(nodes, ax_top, top_n=15)

    # Row 2: full weight heatmap (spans all columns)
    ax_heat = fig.add_subplot(gs[2, :])
    fig_weight_heatmap(nodes, ax_heat)

    return fig


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        text = path.read_text(encoding="utf-8", errors="replace")
        title = f"Weka Results – {path.stem}"
    else:
        print("Paste Weka output below, then press Enter twice + Ctrl-Z (Win) / Ctrl-D (Mac/Linux):")
        lines = []
        try:
            while True:
                lines.append(input())
        except EOFError:
            pass
        text = "\n".join(lines)
        title = "Weka Classifier Results"

    if not text.strip():
        print("No input received.")
        sys.exit(1)

    fig = build_dashboard(text, title=title)

    # Save next to input file if one was given, else save to cwd
    if len(sys.argv) >= 2:
        out_path = Path(sys.argv[1]).with_suffix(".png")
    else:
        out_path = Path("weka_results.png")

    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {out_path.resolve()}")
    plt.show()


if __name__ == "__main__":
    main()
