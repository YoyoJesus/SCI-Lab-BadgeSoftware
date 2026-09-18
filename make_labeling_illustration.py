"""
Generate activity_labeling_illustration.png
A signal-level diagram showing how the auto-labeler works.
Run:  python make_labeling_illustration.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

np.random.seed(42)

FIG_BG  = "#FFFFFF"
TEAL    = "#0F766E"
AMBER   = "#F59E0B"
RED     = "#DC2626"
BLUE    = "#1D4ED8"
GRAY    = "#9CA3AF"
LGRAY   = "#F3F4F6"

# ── Simulate time axis (10 seconds, 500ms bins) ───────────────────────────────
t = np.arange(0, 10.0, 0.5)   # 20 bins

# Badge A: speaks from t=1 to t=4, and t=7 to t=8.5
# Badge B: speaks from t=5 to t=7
# Badge C: background noise throughout

def make_signal(t, speech_windows, base=40, speech_boost=30, noise=8):
    sig = base + np.random.randn(len(t)) * noise
    for (start, end) in speech_windows:
        mask = (t >= start) & (t < end)
        sig[mask] += speech_boost + np.random.randn(mask.sum()) * 5
    return np.clip(sig, 0, 100)

sound_A = make_signal(t, [(1.0, 4.0), (7.0, 8.5)], base=38, speech_boost=35)
sound_B = make_signal(t, [(5.0, 7.0)],              base=35, speech_boost=32)
sound_C = make_signal(t, [],                         base=36, speech_boost=0, noise=6)

# Accelerometer: spikes when that badge's wearer is speaking
def make_accel(t, speech_windows, base=0.3, spike=1.8, noise=0.15):
    sig = base + np.abs(np.random.randn(len(t))) * noise
    for (start, end) in speech_windows:
        mask = (t >= start) & (t < end)
        sig[mask] += spike + np.abs(np.random.randn(mask.sum())) * 0.3
    return sig

accel_A = make_accel(t, [(1.0, 4.0), (7.0, 8.5)])
accel_B = make_accel(t, [(5.0, 7.0)])
accel_C = make_accel(t, [])

# Combined score (norm_sound + 1.2 * norm_accel) — simplified
def norm(x): return (x - x.min()) / (x.max() - x.min() + 1e-9)

score_A = norm(sound_A) + 1.2 * norm(accel_A)
score_B = norm(sound_B) + 1.2 * norm(accel_B)
score_C = norm(sound_C) + 1.2 * norm(accel_C)

# Winner per bin
winner = np.argmax(np.stack([score_A, score_B, score_C], axis=0), axis=0)

# Rolling threshold on badge A sound (1s mean vs 60s baseline ~ use global mean)
baseline = np.mean(sound_A)
roll_mean = np.convolve(sound_A, np.ones(2)/2, mode='same')
speech_present_A = roll_mean > baseline * 1.08

# Final label for Badge A: winner==0 and speech present
label_A = (winner == 0) & speech_present_A
label_B = (winner == 1)
label_C = (winner == 2) & ~speech_present_A   # C never really wins cleanly

# ── Plot ─────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(4, 1, figsize=(14, 11),
                         gridspec_kw={"height_ratios": [2, 2, 2, 1.2]})
fig.patch.set_facecolor(FIG_BG)
fig.subplots_adjust(hspace=0.55, left=0.10, right=0.97, top=0.91, bottom=0.06)

fig.suptitle("Activity Labeling — How the Algorithm Works",
             fontsize=18, fontweight="bold", color="#1C1917", y=0.97)

t_mid = t + 0.25   # centre of each bin for bar plots

# ── Panel 1: Sound signals ────────────────────────────────────────────────────
ax = axes[0]
ax.set_facecolor(LGRAY)
ax.plot(t_mid, sound_A, color=TEAL,  lw=2,   label="Badge A (Person A)", zorder=3)
ax.plot(t_mid, sound_B, color=BLUE,  lw=2,   label="Badge B (Person B)", zorder=3)
ax.plot(t_mid, sound_C, color=GRAY,  lw=1.5, label="Badge C (Person C)", zorder=2, linestyle="--")
ax.axhline(baseline * 1.08, color=AMBER, lw=1.8, linestyle=":", label="Speech threshold")
ax.set_ylabel("Sound Level (dB)", fontsize=11)
ax.set_title("Raw Sound Signals & IQR Normalization", fontsize=12, fontweight="bold", color=TEAL, loc="left")
ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
ax.set_xlim(0, 10)
ax.set_ylim(15, 105)
ax.tick_params(labelbottom=False)
for spine in ax.spines.values(): spine.set_visible(False)

# ── Panel 2: Accelerometer signals ───────────────────────────────────────────
ax = axes[1]
ax.set_facecolor(LGRAY)
ax.bar(t_mid, accel_A, width=0.42, color=TEAL, alpha=0.8, label="Badge A accel.", zorder=3)
ax.bar(t_mid, accel_B, width=0.42, color=BLUE, alpha=0.6, label="Badge B accel.", zorder=3)
ax.bar(t_mid, accel_C, width=0.42, color=GRAY, alpha=0.4, label="Badge C accel.", zorder=2)
ax.set_ylabel("Acceleration (g)", fontsize=11)
ax.set_title("Accelerometer Weighted 1.2x — Vibration Identifies Speaker", fontsize=12, fontweight="bold", color=TEAL, loc="left")
ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
ax.set_xlim(0, 10)
ax.tick_params(labelbottom=False)
for spine in ax.spines.values(): spine.set_visible(False)

# ── Panel 3: Combined scores ──────────────────────────────────────────────────
ax = axes[2]
ax.set_facecolor(LGRAY)
ax.plot(t_mid, score_A, color=TEAL, lw=2.5, marker="o", ms=5, label="Score A", zorder=4)
ax.plot(t_mid, score_B, color=BLUE, lw=2.5, marker="s", ms=5, label="Score B", zorder=4)
ax.plot(t_mid, score_C, color=GRAY, lw=1.5, marker="^", ms=4, label="Score C", zorder=3, linestyle="--")
ax.set_ylabel("Combined Score", fontsize=11)
ax.set_title("Combined Score (norm_sound + 1.2 × norm_accel) — Highest Score Wins Bin", fontsize=12, fontweight="bold", color=TEAL, loc="left")
ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
ax.set_xlim(0, 10)
ax.tick_params(labelbottom=False)
for spine in ax.spines.values(): spine.set_visible(False)

# ── Panel 4: Final labels ─────────────────────────────────────────────────────
ax = axes[3]
ax.set_facecolor(LGRAY)

colors_map = {0: TEAL, 1: BLUE, 2: GRAY}
labels_map = {0: "Badge A active", 1: "Badge B active", 2: "No clear speaker"}

for j, bin_t in enumerate(t):
    if label_A[j]:
        col = TEAL
    elif label_B[j]:
        col = BLUE
    else:
        col = "#E5E7EB"
    ax.bar(t_mid[j], 1, width=0.48, color=col, edgecolor="white", linewidth=0.5, zorder=3)

ax.set_yticks([])
ax.set_xlim(0, 10)
ax.set_ylim(0, 1.3)
ax.set_xlabel("Time (seconds)", fontsize=12)
ax.set_title("Majority Vote + Post-Processing → Final Activity Labels", fontsize=12, fontweight="bold", color=TEAL, loc="left")
for spine in ax.spines.values(): spine.set_visible(False)

# Legend for labels panel
patch_A = mpatches.Patch(color=TEAL,      label="Badge A speaking")
patch_B = mpatches.Patch(color=BLUE,      label="Badge B speaking")
patch_N = mpatches.Patch(color="#E5E7EB", label="Silence / no speaker")
ax.legend(handles=[patch_A, patch_B, patch_N], loc="upper right", fontsize=9, framealpha=0.9)

plt.savefig("activity_labeling_illustration.png", dpi=200,
            bbox_inches="tight", facecolor=FIG_BG)
print("Saved activity_labeling_illustration.png")
