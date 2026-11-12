# Paper-based hybrid speaker badge

Runs local speaker-candidate detection on a Nano 33 BLE Sense Rev2, then sends
scalar readings to the PC over BLE. It builds on this repo's paper detector,
with an optional depth-four decision tree using additional onboard sensors.
Existing firmware and launchers are untouched. This is experimental firmware;
no wearer-detection accuracy or battery-life result is established.

## Start on Windows

For the combined live monitor and observer panel, see the [desktop viewer](VIEWER.md).
After setup, launch it with `.\run_viewer.bat`. The CLI workflow below remains available.

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
Upload this standalone sketch to each badge, giving each one a unique name:

```powershell
.\firmware.ps1 upload -Port COM5 -Name badge_01
```

The name (1-20 letters, digits, underscores, or hyphens) is built into that
badge's firmware and advertised over BLE, so the receiver, viewer, and CSV files
use it as the badge ID in every session. Label each physical badge to match.
Without `-Name`, the badge advertises the shared default name and the PC numbers
it by scan order, which can change between runs. Re-uploading, including after
training a model, needs the same `-Name` again. The sketch boots without USB connected.
The LED turns on after about 1 s of local speech (two 500 ms bins with at least
half their samples flagged), so it trails speech by 1 to 1.5 s. Rapid blinking at startup indicates
IMU/BLE failure; slower blinking indicates microphone initialization failure.

## Collect using the paper rule first

```powershell
.\run.bat receive --scan
.\run.bat receive --seconds 300 --recording-id session_01 --rate 200 --send-seconds 5
```

The receiver connects to badges advertising the new service. To select devices,
repeat `--address ADDRESS` using addresses from the scan. Named badges keep
their flashed name as the badge ID. Unnamed or duplicate-named badges get
`badge_01`, etc. by sorted order, printed at connection; those may change next run.
Use anonymous recording IDs, consistently across files from the same session.
The new service is deliberately separate from the legacy collector's protocol.

Scalar readings are flushed to `outputs/<timestamp>_raw.csv` as they arrive.
On shutdown or at the end, the receiver writes `<timestamp>_labeled.csv` with
`auto_activity_label`, `auto_speaker`, and `time_bin`. These columns and the
original `Timestamp`, `Badge_Name`, `Sound_Level`, and `Acceleration` columns
are intended for the existing Feature Extraction workflow. Engagement inference
is not run automatically. Labels are produced after collection in this version.
An abrupt process termination preserves raw rows; replay can recover labels.

## High-rate acquisition and bulk sending

The v2 firmware follows the acquisition design in
`../Nano33SenseRev2_SerialRealtime`: a high-priority thread reads acceleration
and gyroscope together over 400 kHz I2C, with BMI270 advanced power save disabled
and its output rate raised to 200 Hz when requested. Acquisition defaults to
200 Hz; `--rate` accepts 10, 50, 100, or 200. Actual cadence and fresh-data delivery
still require physical-board measurement.

A separate processing thread evaluates each acquired sample. The paper's
quartile history and short sound mean refresh at approximately 10 Hz, retaining
the 1 s/60 s timescales. Motion uses the nearest available reading to a 100 ms
axis difference, rather than shrinking the difference interval as rate rises.
The 16 kHz microphone, magnetometer, environment, and proximity retain their
own update rates; high-rate rows repeat their latest values.

Acquisition feeds a 128-sample processing queue. Processed predictions and sensor
features enter a separate 1,536-record output queue. BLE sends binary packets
of up to three records, independent of acquisition. Default sending is every
five seconds. `--send-seconds 0` sends immediately; values up to 600 are accepted.
The sender yields for 12 ms between BLE packets/replies; acquisition and inference
continue in their own threads. Configuration commands use separate acknowledged
writes, with the clock anchor taken after rate/send configuration completes.
Sending starts early at 1,152 queued records, approximately 5.76 s at 200 Hz or
11.52 s at 100 Hz, so requesting a longer interval does not increase buffer size.
If processing or BLE cannot keep up, new samples are dropped and counters advance;
buffering cannot guarantee lossless delivery.

Each record retains its acquisition-time `device_ms` and sequence number.
At connection, the PC sends a UTC clock anchor. `Timestamp` is reconstructed
from that anchor and acquisition time; `Arrival_Timestamp` records bulk delivery
time, and `Clock_Source` identifies the mapping. This prevents a whole burst
from being assigned one arrival-time bin. The anchor is approximate: one-way BLE
command delay, clock drift, and observer reaction time remain uncorrected.
Clock mapping supports a device-millisecond wrap for sessions within 24 days
of their anchor. `seq_gap` and cumulative `late_samples` expose missing samples.

Normal completion and Ctrl+C request STOP, drain the processing/output queues,
and await the badge's completion marker before disconnecting. Each badge gets
three connection attempts; a badge that still fails is reported and skipped, and
the others record. If a badge drops mid-session, the others keep recording while
it reconnects and refreshes its clock anchor. The badge keeps sampling while
disconnected, so its queue (about 7.7 seconds at 200 Hz) is sent after
reconnecting; anything beyond that shows up as `seq_gap`. A badge still
disconnected at stop, or a forced process termination, cannot recover unsent data. Use `--raw-only` for
long high-rate captures to skip the final in-memory speaker-labeling pass; raw
CSV recording itself does not retain all samples in a Python list.

The receiver also accepts the original v1 ASCII firmware, marked
`Clock_Source=arrival_legacy`. Rate controls and acquisition-clock anchoring
require v2 firmware. Reflash all badges used in a bulk/observer recording and
re-evaluate existing models on the higher-rate features.

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
.\firmware.ps1 upload -Port COM5 -Name badge_01
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
0.75, and high-score fallback 3.5. One addition: a sample only counts when its
sound is at least 8x the rolling quiet level (the sound Q25), because the
relative rule alone flagged about a third of samples in a silent room. Acceleration is the sum of absolute axis
changes in g. Audio power uses a wide accumulator instead of reproducing the
legacy overflow. It is not the RMS output of the newer full-sensor firmware.
Historical thresholds may therefore need validation on these readings.

Differences from the offline algorithm:

- A 10 Hz, 600-reading history approximates time-based rolling windows. Startup
  waits for ten readings instead of using future whole-recording quartiles.
  Gaps over 250 ms reset history. Sampling overruns are counted.
- PC winner selection counts a badge as speaking in a 500 ms bin when at least
  half its samples are flagged, and only in runs of at least two bins (1 s).
  The speaking badge with the highest flagged score wins the bin, then a
  centered five-bin vote requires three wins. Available observed bins are used,
  following the original implementation. The offline labeler's 2 s minimum and
  gap merging are not applied.
- V2 timestamps use the approximate PC/device anchor described above. Legacy
  firmware retains arrival-time timestamps, unsuitable for bulk alignment.
- PC ranking still uses the paper score even in hybrid mode. This retains the
  single-dominant-speaker assumption and does not resolve simultaneous speakers.

Compare paper-only and hybrid sessions against independent labels before using
their engagement features interchangeably. Track false detections, missed turns,
overlap, onset delay, and downstream speaking-time/turn-count errors.

## Transport and local storage

Service `e8310001-65d2-4b11-91e0-87f64f931c82`, notify characteristic
`e8310002-65d2-4b11-91e0-87f64f931c82`, command characteristic
`e8310003-65d2-4b11-91e0-87f64f931c82`. V2 notifications have a four-byte
little-endian `<BBH` header (type 4, version 1, record count 1–3), followed by
65-byte `<III13fB` records: sequence, acquisition milliseconds, cumulative drops,
13 floats in the order of `transport.FLOAT_FIELDS`, and ready/paper/hybrid flags
in bits 0–2. Three records occupy 199 bytes, requiring an ATT MTU of at least
202, comparable to the reference firmware's large notifications. Truncated or
malformed packets stop capture with an error rather than silently misaligning data.

Text notifications carry `M,<model_id>`, `C,<device_ms>,<host_utc_ms>`, command
status, and `D` for completed drain. Commands are newline-terminated `RATE`,
`SEND` (milliseconds), `CLOCK` (UTC milliseconds), `STOP`, and `STATUS`.
The original fragmented `S` ASCII rows remain supported by the PC decoder only.
Raw audio stays transient on the badge;
only scalars are transmitted. Optional sensor values use -1 when unavailable.
Raw CSVs contain behavioral data and remain local under ignored `outputs/`.
Training data belongs in ignored `data/`. Generated model headers and evaluation
artifacts are also ignored. Nothing is uploaded to a training service.

See the [single-board hardware check](HARDWARE_CHECK.md) for measured sampling
and BLE delivery. Multi-badge delivery, long-duration stability, runtime memory
headroom, power use, and speech-detection accuracy still need measurement.

Validation performed: thirty-five workflow pytest checks and the three existing paper
validation checks passed. Both paper-only and synthetic-model firmware builds
compiled with Arduino Mbed Nano core 4.6.0. The synthetic model checked the export
and compilation path only; no trained speech model is included. Paper-rule
firmware was uploaded and BLE collection tested on one physical Rev2 board.
The v2 paper-only build used 366,408 bytes of flash and 193,096 bytes of static
RAM. Runtime stacks, heap use, and throughput with other adapters or several
badges remain hardware checks. Receiver tests cover bulk packet validation, clock wrapping,
delayed delivery, sequence gaps, and final draining on normal completion/cancellation.
The native observer panel was rendered with synthetic badge IDs, and its
state transitions and annotation merge/evaluation path were checked. Human
annotation reliability has not been measured.
