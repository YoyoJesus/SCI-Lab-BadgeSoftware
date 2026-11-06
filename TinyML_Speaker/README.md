# Paper-based hybrid speaker badge

Runs local speaker-candidate detection on a Nano 33 BLE Sense Rev2, then sends
scalar readings to the PC over BLE. It builds on this repo's paper detector,
with an optional depth-four decision tree using additional onboard sensors.
Existing firmware and launchers are untouched. This is experimental firmware;
no wearer-detection accuracy or battery-life result is established.

## Start on Windows

Python 3.9 or later and a BLE adapter are required. From this folder:

```powershell
.\run.bat setup
.\run.bat test
```

Install [Arduino CLI](https://arduino.github.io/arduino-cli/latest/installation/)
on PATH, or put its executable in `.tools/arduino-cli.exe`. The setup below
installs the board core and libraries under this folder's ignored `.tools`:

```powershell
.\firmware.ps1 setup
.\firmware.ps1 build
.\firmware.ps1 boards
.\firmware.ps1 upload -Port COM5
```

The firmware script temporarily maps a free drive letter between T: and Z: to
the tool directory to avoid GCC's Windows path-length limit, then removes it.

Use the board's actual port, not the example value. If PowerShell blocks local
scripts, invoke them with `powershell -ExecutionPolicy Bypass -File .\firmware.ps1 build`.
Upload this standalone sketch to each badge. It boots without USB connected.
The LED follows its local candidate flag. Rapid blinking at startup indicates
IMU/BLE failure; slower blinking indicates microphone initialization failure.

## Collect using the paper rule first

```powershell
.\run.bat receive --scan
.\run.bat receive --seconds 300 --recording-id session_01
```

The receiver connects to badges advertising the new service. To select devices,
repeat `--address ADDRESS` using addresses from the scan. Device assignments
`badge_01`, etc. are printed at connection; assignments may change next run.
Use anonymous recording IDs, consistently across files from the same session.
The new service is deliberately separate from the legacy collector's protocol.

Scalar readings are flushed to `outputs/<timestamp>_raw.csv` as they arrive.
On shutdown or at the end, the receiver writes `<timestamp>_labeled.csv` with
`auto_activity_label`, `auto_speaker`, and `time_bin`. These columns and the
original `Timestamp`, `Badge_Name`, `Sound_Level`, and `Acceleration` columns
are intended for the existing Feature Extraction workflow. Engagement inference
is not run automatically. Labels are produced after collection in this version.
An abrupt process termination preserves raw rows; replay can recover labels.

## Add ML with the other sensors

Use the [human observer workflow](GROUND_TRUTH.md) to collect independent labels
and merge them into training-ready CSVs. Start the panel with:

```powershell
.\run.bat annotate --badges badge_01 badge_02 --recording-id session_01
```

The model inputs are normalized sound, normalized acceleration, normalized
presence margin, gyro magnitude (degrees/s), magnetic-field magnitude (uT),
temperature (C), humidity (%), pressure (kPa), and proximity (sensor counts).
This excludes external GSR wiring, which is not assumed. Extra sensors may
capture room or participant identity rather than speech, so improvement must
be measured, not assumed.

1. Collect multiple sessions with the new firmware. Include wearer speech,
   nearby speech, silence, movement, and noise. Keep the badges worn as deployed.
2. Copy recordings locally and add `activity_label`: `active` for wearer speech,
   `not_active` for verified wearer non-speech, or `unknown` for unannotated time.
   Never turn missing annotations into negatives. Include both labels in multiple
   recordings. `Recording_ID` must identify the whole source recording, not a
   badge or a chunk within the same recording.
3. Train with the labeled copies:

```powershell
.\run.bat train data/session_01.csv data/session_02.csv data/session_03.csv
.\firmware.ps1 upload -Port COM5
```

Training exports `firmware/SpeakerBadge/model.h` and `outputs/model/evaluation.json`.
The report uses whole-recording holdout; recurring participants can still leak
identity. The exported model uses only the training groups so the report refers
to the deployed model. It compares the paper rule, ML using only paper features,
and ML using all sensor features on the same held-out rows. Unknown and warmup rows are excluded. Missing auxiliary
sensors are represented by -1 and must be corrected before training.

With a model, its score >= 0.6 controls the local `candidate` flag. The paper's
`paper_candidate` and `speech_score` are retained for comparison. A missing
required sensor suppresses hybrid candidates; `model_score=-1` means no valid
model prediction. A score is not a calibrated probability. Remove the generated
header and rebuild/upload to return to paper-rule operation.

For an explicitly exploratory imitation of automatic labels:

```powershell
.\run.bat train outputs/example_labeled.csv --label auto_activity_label --allow-pseudo-labels
```

This measures agreement with automatic labels, not speaker accuracy. Historical
CSVs lack the additional sensor features and cannot train the hybrid model.
They can exercise the causal paper-rule adaptation:

```powershell
.\run.bat replay "path/to/legacy.csv" --output outputs/replay.csv
```

## Relationship to the paper

See [design](DESIGN.md) and the [paper](../paper/manuscript.md), section 3.2.
Local rules preserve the 1 s/60 s windows, 0.45 sound quantile, quartile
normalization, acceleration weight 1.2, acceleration clip 2.5, eligibility floor
0.75, and high-score fallback 3.5. Acceleration is the sum of absolute axis
changes in g. Audio power uses a wide accumulator instead of reproducing the
legacy overflow. It is not the RMS output of the newer full-sensor firmware.
Historical thresholds may therefore need validation on these readings.

Differences from the offline algorithm:

- A 10 Hz, 600-reading history approximates time-based rolling windows. Startup
  waits for ten readings instead of using future whole-recording quartiles.
  Gaps over 250 ms reset history. Sampling overruns are counted.
- PC winner selection uses the highest eligible score in each 500 ms bin and
  a centered five-bin vote requiring three wins. Available observed bins are
  used, following the original implementation. Short-run suppression and gap
  merging from the offline labeler are not applied.
- Timestamps are PC arrival times, not synchronized badge clocks. `device_ms`,
  sequence counters, and `seq_gap` support diagnosis but do not fix alignment.
- PC ranking still uses the paper score even in hybrid mode. This retains the
  single-dominant-speaker assumption and does not resolve simultaneous speakers.

Compare paper-only and hybrid sessions against independent labels before using
their engagement features interchangeably. Track false detections, missed turns,
overlap, onset delay, and downstream speaking-time/turn-count errors.

## Transport and local storage

Service `e8310001-65d2-4b11-91e0-87f64f931c82`, notify characteristic
`e8310002-65d2-4b11-91e0-87f64f931c82`. Newline-delimited ASCII is fragmented
into at most 20-byte notifications. `M,<model_id>` identifies the model.
`S` rows follow `FIELDS` in `pipeline.py`. Raw audio stays transient on the badge;
only scalars are transmitted. Optional sensor values use -1 when unavailable.
Raw CSVs contain behavioral data and remain local under ignored `outputs/`.
Training data belongs in ignored `data/`. Generated model headers and evaluation
artifacts are also ignored. Nothing is uploaded to a training service.

The first release needs physical-board checks for sampling cadence, sensor
availability, BLE delivery with several badges, memory use, and power consumption.

Validation performed: nineteen workflow pytest checks and the three existing paper
validation checks passed. Both paper-only and synthetic-model firmware builds
compiled with Arduino Mbed Nano core 4.6.0. Paper-only firmware used 361,816 bytes
of flash and 79,672 bytes of static RAM. The synthetic model checked the export
and compilation path only; no trained speech model is included. No firmware was
uploaded and no physical badge or BLE collection was tested.
The native observer panel was rendered with synthetic badge IDs, and its
state transitions and annotation merge/evaluation path were checked. Human
annotation reliability has not been measured.
