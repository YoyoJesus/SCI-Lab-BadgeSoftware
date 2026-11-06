# Paper-based on-badge detection

Source: ../paper/manuscript.md section 3.2 and
../Data Cleanup and Normalization/auto_label.py. Preserve the 1 s sound mean,
60 s baseline, 0.45 presence quantile, quartile normalization with denominator
floor 1, acceleration weight 1.2 clipped to [0, 2.5], score floor 0.75, and
fallback 3.5. Acceleration is the sum of absolute axis changes in g, matching
the legacy badge. Sound is mean-square microphone power divided by two,
approximating the legacy full-block convention while avoiding its overflow.
Numerical equivalence to historical sound data is not claimed.

Firmware samples summaries at 10 Hz. A 600-observation history approximates
time-based windows while sampling stays regular. Startup requires ten readings;
missing data resets history. No future samples are used for normalization.
The badge sends a score and local candidate flag. Only the PC can compare badges.
The receiver selects the highest eligible sample per 500 ms arrival-time bin,
then applies a centered five-bin vote requiring three wins. It writes labeled
CSV for downstream feature extraction. Legacy run-length post-processing is
not part of this streaming detector.

The default is the deterministic paper rule, requiring no training. An optional
shallow decision tree learns from normalized sound, normalized acceleration,
normalized presence margin, gyro and magnetic magnitude, temperature, humidity,
pressure, and proximity. It exports C++ without a runtime dependency.
Manual labels are preferred. Auto labels require explicit opt-in and measure
agreement, not speech accuracy. When deployed, its confidence >= 0.6 supplies
the candidate flag; the paper candidate and ranking score remain available.
Whole recordings are held out for evaluation. Evaluate the paper rule, a tree
using paper features alone, and the full tree on the same held-out recordings.

Standalone firmware targets Nano 33 BLE Sense Rev2. Existing code remains intact.
Raw audio is transient and never sent or recorded. Local scalar data and model
artifacts are ignored by git. Engagement inference stays on the PC.

## Implementation plan

The independent PC reference uses an observer-only Tkinter panel. Per-badge
states support overlapping speakers and explicit unknown intervals. State
changes and one-second checkpoints save half-open UTC intervals. Focus loss
pauses annotation. Merge by recording/badge and PC arrival timestamp, preserving
unknown time and excluding a configurable transition margin. Evaluate only
annotated samples; prediction output is hidden from the observer panel.

1. Test causal normalization, thresholds, voting, invalid readings, grouped
   training, model export, and transport validation.
2. Build headless replay/train/receive commands and matching C++ detection.
3. Add Windows setup/run/build scripts, document deployment and limitations,
   run available tests/toolchain checks, and commit the new folder.
