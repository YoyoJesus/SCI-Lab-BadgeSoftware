# Human observer reference

Run a native PC panel alongside BLE collection to mark who is speaking.
The panel does not show model predictions, record audio, or infer labels.
Human annotations are a reference with timing and judgment uncertainty, not
proof of speech accuracy. No additional Python dependencies are required;
the standard Python Windows installer includes Tkinter.

## Collect and annotate on the same PC

From `TinyML_Speaker`, first start the receiver:

```powershell
.\run.bat receive --seconds 600 --recording-id session_01
```

Note which wearer corresponds to each `badge_01`, `badge_02`, etc. printed by
the receiver. These assignments can change on the next run. In a second terminal:

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

Intervals are flushed to a local CSV every second and on changes/close. If the
process is forcibly terminated, its last unflushed interval is absent and stays
unknown. Existing files are never overwritten. Start a new file after a crash.
You can correct the interval CSV afterward; do not create overlapping intervals
for the same badge. Different badges may overlap freely.

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
are retained, but alignment here uses PC arrival timestamps and observer UTC
timestamps, so transport latency and human reaction time remain limitations.

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
