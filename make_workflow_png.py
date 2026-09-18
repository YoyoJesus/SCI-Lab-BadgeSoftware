"""
Generate workflow_chart.png — 1x6 grid layout for poster.
Run:  python make_workflow_png.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
import numpy as np

# ── Palette — matches meeting_visualizer.py ────────────────────────────────────
PALETTE = [
    "#4C72B0",  # Data Gathering     — blue
    "#DD8452",  # Activity Labeling  — orange
    "#55A868",  # Feature Extraction — green
    "#C44E52",  # Weka Export        — red
    "#8172B3",  # Model Training     — purple
    "#937860",  # Analysis           — brown
]

CARD_BG   = "#FDE68A"
BODY_COL  = "#1C1917"
ARROW_COL = "#374151"
FIG_BG    = "#F8F9FA"   # matches weka_visualizer.py fig background

# ── Font sizes ────────────────────────────────────────────────────────────────
FS_BULLET = 18
FS_FOOTER = 20
FS_FILE   = 18
FS_TITLE  = 22

# ── Card content ──────────────────────────────────────────────────────────────
CARDS = [
    {
        "footer": "Data Gathering",
        "bullets": [
            "Wearable BLE voice badges",
            "Streams Sound, RSSI,",
            "  & Acceleration",
            "Multiple badges at once",
            "Unified timestamped CSV",
        ],
        "file": "data_collection.py",
    },
    {
        "footer": "Activity Labeling",
        "bullets": [
            "Split data into 500 ms windows",
            "IQR-normalize sound & accel.",
            "  per badge",
            "1s rolling vs. 60s baseline",
            "  threshold detects speech",
            "Accel. weighted 1.2x for",
            "  speaker identification",
            "Majority vote across 5 bins",
            "Post-process: remove short",
            "  bursts & fill gaps",
        ],
        "file": "auto_label.py",
    },
    {
        "footer": "Feature Extraction",
        "bullets": [
            "Speaking & silence ratio",
            "Turns per minute &",
            "  mean turn duration",
            "Turn equity (Gini coeff.)",
            "Per-participant talk share",
        ],
        "file": "feature_extraction.py",
    },
    {
        "footer": "Weka Export",
        "bullets": [
            "Join feature tables",
            "Label meeting effectiveness:",
            "  low / medium / high",
            "Export to .csv & .arff",
        ],
        "file": "weka_exporter.py",
    },
    {
        "footer": "Model Training",
        "bullets": [
            "Load .arff into Weka",
            "Random Forest",
            "Multilayer Perceptron",
            "Naive Bayes",
        ],
        "file": "Weka (external)",
    },
    {
        "footer": "Analysis & Visualization",
        "bullets": [
            "Review classifier accuracy",
            "Cross-validation in Weka",
            "Identify key features",
            "Visualize results",
        ],
        "file": "weka_visualizer.py",
    },
]

# ── Figure & grid — 1 row × 6 columns ────────────────────────────────────────
COLS, ROWS = 6, 1
FIG_W, FIG_H = 32, 9

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
fig.patch.set_facecolor(FIG_BG)
ax.set_facecolor(FIG_BG)

MARGIN_X = 0.5
MARGIN_Y = 0.5
TITLE_H  = 0.9
GAP_X    = 0.5
GAP_Y    = 1.0   # unused for 1 row, kept for formula consistency

CARD_W = (FIG_W - 2 * MARGIN_X - (COLS - 1) * GAP_X) / COLS
CARD_H = (FIG_H - MARGIN_Y - TITLE_H - (ROWS - 1) * GAP_Y - 0.3) / ROWS

FOOTER_H = 0.95


def card_pos(idx):
    col = idx % COLS
    row = idx // COLS
    x = MARGIN_X + col * (CARD_W + GAP_X)
    y = FIG_H - TITLE_H - MARGIN_Y - (row + 1) * CARD_H - row * GAP_Y
    return x, y


def rounded_rect(ax, x, y, w, h, radius=0.18, fc=CARD_BG, ec="#F59E0B", lw=1.8, zorder=3):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad={radius}",
        linewidth=lw, edgecolor=ec, facecolor=fc, zorder=zorder,
    ))


# ── Icon drawing functions (lower-right of yellow area) ───────────────────────

def icon_data_gathering(ax, cx, cy, s, col):
    """Radio wave arcs emanating upward from a centre point."""
    for r, alpha in [(s * 0.28, 0.45), (s * 0.56, 0.65), (s * 0.85, 0.90)]:
        theta = np.linspace(np.pi * 0.15, np.pi * 0.85, 50)
        ax.plot(cx + r * np.cos(theta), cy + r * np.sin(theta),
                color=col, lw=2.0, alpha=alpha, zorder=7, solid_capstyle="round")
    ax.plot(cx, cy, "o", color=col, ms=5, zorder=7)


def icon_activity_labeling(ax, cx, cy, s, col):
    """Sound waveform — rising amplitude in the centre."""
    x = np.linspace(cx - s, cx + s, 120)
    env = np.exp(-((x - cx) / (s * 0.55)) ** 2) + 0.25
    y = cy + s * 0.55 * env * np.sin((x - cx) / s * 3.5 * np.pi)
    ax.plot(x, y, color=col, lw=2.2, zorder=7, solid_capstyle="round")


def icon_feature_extraction(ax, cx, cy, s, col):
    """Three vertical bars of varying height (bar chart)."""
    bar_w = s * 0.38
    heights = [s * 0.55, s * 0.90, s * 0.70]
    offsets = [-s * 0.65, 0.0, s * 0.65]
    for dx, h in zip(offsets, heights):
        ax.add_patch(Rectangle(
            (cx + dx - bar_w / 2, cy - s * 0.45), bar_w, h,
            facecolor=col, alpha=0.88, zorder=7,
        ))


def icon_weka_export(ax, cx, cy, s, col):
    """Down-arrow feeding into a small table."""
    # Arrow
    ax.annotate("",
        xy=(cx, cy - s * 0.18), xytext=(cx, cy + s * 0.60),
        arrowprops=dict(arrowstyle="-|>", color=col, lw=2.2, mutation_scale=16),
        zorder=7)
    # Table box
    bx, by = cx - s * 0.65, cy - s * 0.50
    bw, bh = s * 1.30, s * 0.38
    ax.add_patch(Rectangle((bx, by), bw, bh,
                 facecolor="none", edgecolor=col, lw=1.8, zorder=7))
    for frac in [1/3, 2/3]:
        ax.plot([bx, bx + bw], [by + bh * frac, by + bh * frac],
                color=col, lw=1.2, zorder=7)
    ax.plot([bx + bw / 2, bx + bw / 2], [by, by + bh],
            color=col, lw=1.2, zorder=7)


def icon_model_training(ax, cx, cy, s, col):
    """Decision-tree diagram — root, two children, four leaves."""
    nodes = {
        "root": (cx,           cy + s * 0.50),
        "l1":   (cx - s * 0.55, cy),
        "r1":   (cx + s * 0.55, cy),
        "ll":   (cx - s * 0.80, cy - s * 0.50),
        "lr":   (cx - s * 0.30, cy - s * 0.50),
        "rl":   (cx + s * 0.30, cy - s * 0.50),
        "rr":   (cx + s * 0.80, cy - s * 0.50),
    }
    edges = [("root", "l1"), ("root", "r1"),
             ("l1", "ll"), ("l1", "lr"),
             ("r1", "rl"), ("r1", "rr")]
    for a, b in edges:
        ax.plot([nodes[a][0], nodes[b][0]], [nodes[a][1], nodes[b][1]],
                color=col, lw=1.8, zorder=7)
    sizes = {"root": 7, "l1": 6, "r1": 6,
             "ll": 5, "lr": 5, "rl": 5, "rr": 5}
    for name, (nx, ny) in nodes.items():
        ax.plot(nx, ny, "o", color=col, ms=sizes[name], zorder=8)


def icon_analysis(ax, cx, cy, s, col):
    """Small line chart with axis lines."""
    # Axes
    ax.plot([cx - s, cx - s], [cy - s * 0.5, cy + s * 0.65],
            color=col, lw=1.5, alpha=0.55, zorder=7)
    ax.plot([cx - s, cx + s], [cy - s * 0.5, cy - s * 0.5],
            color=col, lw=1.5, alpha=0.55, zorder=7)
    # Data line
    xs = np.linspace(cx - s * 0.85, cx + s * 0.85, 6)
    ys = np.array([0.05, 0.40, 0.30, 0.65, 0.55, 0.90]) * s * 1.1 + cy - s * 0.45
    ax.plot(xs, ys, color=col, lw=2.2, zorder=7, solid_capstyle="round")
    ax.plot(xs, ys, "o", color=col, ms=4.5, zorder=8)


ICON_FNS = [
    icon_data_gathering,
    icon_activity_labeling,
    icon_feature_extraction,
    icon_weka_export,
    icon_model_training,
    icon_analysis,
]


# ── Card drawing ──────────────────────────────────────────────────────────────

def draw_card(ax, idx, card):
    x, y = card_pos(idx)
    col = PALETTE[idx]

    # Card body (yellow)
    rounded_rect(ax, x, y, CARD_W, CARD_H, ec=col)

    # Footer strip
    ax.add_patch(FancyBboxPatch(
        (x, y), CARD_W, FOOTER_H,
        boxstyle="round,pad=0.20",
        linewidth=0, facecolor=col, zorder=4,
    ))
    # Flatten the top of the footer so it meets the body cleanly
    ax.add_patch(Rectangle(
        (x, y + FOOTER_H * 0.45), CARD_W, FOOTER_H * 0.6,
        facecolor=col, linewidth=0, zorder=4,
    ))

    # Footer: stage name + filename
    ax.text(x + CARD_W / 2, y + FOOTER_H * 0.72,
            card["footer"],
            ha="center", va="center",
            fontsize=FS_FOOTER, fontweight="bold", color="white", zorder=5)
    ax.text(x + CARD_W / 2, y + FOOTER_H * 0.26,
            card["file"],
            ha="center", va="center",
            fontsize=FS_FILE, color="white", fontstyle="italic", zorder=5)

    # Bullets
    bullet_top = y + CARD_H - 0.25
    bullet_bot = y + FOOTER_H + 0.12

    bullets  = card["bullets"]
    line_h   = FS_BULLET / 72 * 1.55
    total_h  = len(bullets) * line_h
    avail    = bullet_top - bullet_bot
    gap      = (avail - total_h) / max(len(bullets), 1)
    gap      = max(gap, line_h * 0.15)
    gap      = min(gap, line_h * 0.60)

    cur_y = bullet_top
    bx    = x + 0.18
    for bullet in bullets:
        is_cont = bullet.startswith("  ")
        prefix  = "      " if is_cont else "\u2022  "
        ax.text(bx, cur_y,
                f"{prefix}{bullet.strip()}",
                ha="left", va="top",
                fontsize=FS_BULLET, color=BODY_COL,
                linespacing=1.35, zorder=5)
        cur_y -= line_h + gap

    # Icon — lower-right corner of the yellow area
    icon_s  = 0.44
    icon_cx = x + CARD_W - icon_s * 1.15
    icon_cy = y + FOOTER_H + icon_s * 1.05
    ICON_FNS[idx](ax, icon_cx, icon_cy, s=icon_s, col=col)


# ── Arrows ────────────────────────────────────────────────────────────────────

def draw_h_arrow(ax, from_idx, to_idx):
    x0, y0 = card_pos(from_idx)
    x1, _  = card_pos(to_idx)
    mid_y  = y0 + CARD_H / 2
    ax.annotate("",
        xy=(x1, mid_y), xytext=(x0 + CARD_W, mid_y),
        arrowprops=dict(arrowstyle="-|>", color=ARROW_COL, lw=3.5, mutation_scale=28),
        zorder=6)


# ── Render ────────────────────────────────────────────────────────────────────

for i, card in enumerate(CARDS):
    draw_card(ax, i, card)

for i in range(COLS - 1):
    draw_h_arrow(ax, i, i + 1)

ax.text(FIG_W / 2, FIG_H - 0.20,
        "Smart Badge Software \u2014 Research Pipeline",
        ha="center", va="top",
        fontsize=FS_TITLE, fontweight="bold", color="#1C1917", zorder=5)

plt.tight_layout(pad=0.1)
plt.savefig("workflow_chart.png", dpi=200, bbox_inches="tight", facecolor=FIG_BG)
print("Saved workflow_chart.png")
