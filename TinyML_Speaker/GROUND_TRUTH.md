# Human observer reference

Run a native PC panel alongside BLE collection to mark who is speaking.
The panel does not show model predictions, record audio, or infer labels.
Human annotations are a reference with timing and judgment uncertainty, not
proof of speech accuracy. No additional Python dependencies are required;
the standard Python Windows installer includes Tkinter.

## Collect and annotate on the same PC

From `TinyML_Speaker`, first start the receiver:

```powershell
.\run.bat receive --seconds 600 --recording-id session_01 --rate 200 --send-seconds 5
```

Note which wearer corresponds to each `badge_01`, `badge_02`, etc. printed by
the receiver. These assignments can change on the next run. The viewer records
this mapping in `participants.md` for you (see [VIEWER.md](VIEWER.md)). In a
second terminal:

```powershell
.\run.bat annotate --badges badge_01 badge_02 --recording-id session_01 --output outputs/session_01_reference.csv
```

Use the same recording ID and exact badge IDs in both tools. Include every
badge you intend to annotate. Keep participant names out of IDs. Badge identity
must be checked by the observer; the panel cannot verify the wearer mapping.
Keep collection and annotation on the same PC without changing its clock.

The panel opens paused, with everyone unknown:

- **Enter / Start observing:** explicitly begin observing all listed people.
  Everyone initially becomes not speaking; immediately mark anyone speaking.
- **1–9:** toggle the corresponding wearer between speaking and not speaking.
  Several people can be speaking at once.
- **Speaking / Not speaking / Unknown:** set a wearer's state directly.
  Use Unknown when an individual cannot be judged reliably.
- **0 / Observed silence:** explicitly mark everyone as not speaking and resume.
- **Space / Pause:** mark everyone unknown until observation resumes.
- Moving focus to another application also pauses observation.
- **Save and close:** save the final interval and exit.

Only label time you can observe. The panel never converts pauses, missing
annotation, or times outside the reference recording into negative examples.
Use a second observer or adjudicated recordings to assess annotation agreement
before treating these labels as a stronger reference.

Intervals are flushed to a local CSV every 0.2 seconds and on changes/close. If the
process is forcibly terminated, its last unflushed interval is absent and stays
unknown. Existing files are never overwritten. Start a new file after a crash.
You can correct the interval CSV afterward; do not create overlapping intervals
for the same badge. Different badges may overlap freely.

## Add a second observer

The desktop viewer can serve a page for a second observer; see
[VIEWER.md](VIEWER.md#second-observer). To combine two reference files
yourself:

```powershell
.\run.bat combine outputs/session/reference.csv outputs/session/reference_observer2.csv --output outputs/session/reference_consensus.csv --report outputs/session/observer_agreement.json
```

The consensus keeps a label only where both observers gave the same known
label, and marks everything else unknown. The report gives time-weighted
agreement and Cohen's kappa over time both observers labeled, plus the median
gap between their speaking starts and ends (second minus first, matched within
3 s). That onset gap is a direct measurement of how differently the two
observers react, and a better basis for `--onset-ms` than detector agreement.
Merge the consensus file like any other reference file.

## Merge with the badge readings

Reference CSV fields are `Recording_ID`, `Badge_Name`, `Start`, `End`, and
`activity_label`. Start/end timestamps must include an explicit timezone;
the panel writes UTC.

After both tools finish, select the matching raw receiver CSV. For example,
this command selects the most recent raw file; verify that it is your session:

```powershell
$raw = Get-ChildItem outputs/*_raw.csv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
.\run.bat merge $raw.FullName outputs/session_01_reference.csv --output data/session_01_labeled.csv
```

The result preserves sensor features, recording IDs, and predictions, and adds
`activity_label` with `active`, `not_active`, or `unknown`. Existing manual labels
in the input are replaced in the new output by the selected reference intervals.
The source files are unchanged. Session and badge mismatches, invalid timestamps,
and overlapping intervals for a badge are rejected.

Intervals are start-inclusive and end-exclusive. By default, merging excludes
200 ms on either side of each state transition. One-second save checkpoints
with unchanged states are joined before applying this exclusion. This margin
does not correct observer reaction time or BLE latency. Configure it explicitly:

```powershell
.\run.bat merge $raw.FullName outputs/session_01_reference.csv --boundary-ms 300 --offset-ms 0 --output data/session_01_guarded.csv
```

`--offset-ms` shifts all reference intervals: positive shifts them later,
negative shifts them earlier. Choose offsets using a separate synchronization
exercise, not by maximizing model agreement. Do not use a boundary margin so
large that it removes the short turns you need to evaluate. Device timestamps
are retained.

Observers often press the speaking key after the wearer has already started
talking, while the end of a turn is marked more promptly. `--onset-ms` marks
that much time before each speaking interval as `unknown` instead of
`not_active`, without moving the interval ends:

```powershell
.\run.bat merge $raw.FullName outputs/session_01_reference.csv --onset-ms 1500 --output data/session_01_onset.csv
```

Measure your own delay with a separate exercise, such as marking a series of
claps on cue, and use that value rather than tuning it against detector
agreement. The default is 0. V2 capture reconstructs acquisition-time `Timestamp` from a PC
clock anchor and keeps bulk arrival time separately. Alignment uses this
acquisition estimate and observer UTC time; one-way clock-command delay, drift,
and human reaction time remain limitations. Legacy firmware uses arrival time
instead and should not be used for bulk/observer alignment.

## Compare the badge detector against the observer

```powershell
.\run.bat evaluate data/session_01_labeled.csv --prediction candidate --output outputs/session_01_hybrid_report.json
.\run.bat evaluate data/session_01_labeled.csv --prediction paper_candidate --output outputs/session_01_paper_report.json
```

Reports include annotated/unknown counts, a confusion matrix, precision, recall,
specificity, F1, and accuracy on annotated samples only. Undefined metrics are
null. These are sample-level reference-agreement statistics; adjacent samples
are correlated. If no model has been uploaded, `candidate` is the paper rule,
so those reports will describe the same detector. Train/test separation and
additional recordings are still needed to measure generalization.

## Train the hybrid model

Repeat collection and annotation for separate sessions, then:

```powershell
.\run.bat train data/session_01_labeled.csv data/session_02_labeled.csv data/session_03_labeled.csv
```

Training excludes unknown and warmup rows and requires both classes on either
side of its recording-level split. All chunks and badges from the same source
session must share one recording ID. Annotations and behavioral CSVs remain
local under ignored `outputs/` and `data/` folders.
