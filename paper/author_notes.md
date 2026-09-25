# Author notes and evidence ledger

These notes accompany `manuscript.typ` and record evidence, reproducibility status, and remaining author questions. They are not part of the typeset paper. The current draft incorporates recovered local data and uses a two-column layout with 10-point Times New Roman; no venue-specific template has been selected.

The author list is Austin Sternberg, Bishop Harsch, and JungYoon Kim, with the Smart Communities and IoT Laboratory, Kent State University affiliation. This is the established manuscript author list. The remaining authorship work is contribution and submission approval documentation, not inferring authors from the poster.

## Current revision status

- **Verified:** the 16-record CSV and ARFF, all 48 source feature tables, and all 576 numerical feature values. The saved feature-to-export stage reproduces; the earlier sensor-to-feature stage has not been rerun.
- **Reconstructed:** the saved speaker-state matrix and adaptive binary counts, including original duplicate-row weighting and the unknown-to-inactive label convention.
- **Retained as historical results:** Random Forest and multilayer-perceptron scores from the poster. No classifier was retrained, and its original settings, folds, and predictions have not been recovered.
- **Corrected in the manuscript:** mixed meeting/lecture records, same-session segments, recurring participant-name strings, overlap of the speaker-comparison interval with a classification record, and annotation/alignment limitations.
- **Formatting verified:** all five numbered equations fit on one line; table cells have 5 pt horizontal padding, and the feature-count column sizes to its header. These choices are implemented in both `manuscript.typ` and `export_typst.py`. The PDF was rebuilt with installed Typst 0.14.2 and visually checked.

## Remaining author questions

1. **Complete classifier provenance.** The 16-record CSV, matching ARFF, and all 48 source feature tables are recovered and verified. All 576 numerical feature values reproduce from those tables; ARFF values match at six decimal places. Original WEKA logs, settings, fold seeds/assignments, predictions, and deployed firmware/analysis revisions remain unrecovered. Do not present a new run as reproduction of the historical scores.
2. **Establish label independence.** The poster calls labels self-reported. April 3 slide 12 explicitly says key statistics are displayed to inform the label decision; the exporter also displays predictors alongside an effectiveness rubric. The manuscript now describes manual, feature-informed labels rather than assuming independent self-reports. Determine who rated each meeting, when, with which questions, and whether the displayed features influenced ratings. This distinction can change the scientific interpretation of the entire classification result.
3. **Verify study administration and participant identities.** Recorded metadata establish nine SCI records, five HacKSU records, and two CS1 lecture records, spanning 2025-10-10 to 2026-04-10. Durations total 747.56 min, with a 29.15-76.26 min range and 45.41 min median. Two SCI records are consecutive April 3 segments. Metadata report 2-6 participants per record. There are 29 normalized name strings, not 29 verified individuals; 55 of 120 record pairs share a name. Recruitment, unique-person identity resolution, complete attendance, tasks, room conditions, exclusions, and badge placement still need author confirmation.
4. **Repair annotation validity before a new evaluation.** The original 5,373-bin speaker matrix is exactly reconstructed from the saved comparison. Its source interval matches `hacksu_meeting_3`; it is not an independent recording-level validation set. The manual input contains 45,491 active and 224,176 unknown labels, no explicit inactive labels. The comparison maps unknown to inactive. Determine whether unknown means deliberately unmarked silence or unannotated time; until verified, do not call it exhaustively annotated ground truth. Duplicate-key joins also weight observations unevenly.
5. **Document contributions, ethics, and funding.** Retain the established author list above. Obtain author contribution statements and submission approval, and document participant consent, ethics review approval or exemption, funding, and any conflicts of interest. The recovered sensor and feature files do not establish these details.
6. **Choose the venue and paper category.** The strongest current framing is a feasibility/system paper with transparent limitations. A full journal empirical paper would benefit from a larger evaluation, documented independent ratings, and validation on new teams.

## Poster versions and numerical reconciliation

The Kent State poster used for the original manuscript is the source of the historical classifier summaries. Its publication date is not established; it is not assumed to be chronologically newer solely because it contains more meetings.

| Item | Linked poster | PDF already in repository | Treatment in draft |
| --- | --- | --- | --- |
| Reported meetings | 16 | 14 | Describe the recovered sample as 16 session records, including segments and lectures |
| Cross-validation | 10 folds | 14 folds | Use 10 folds; do not infer grouped folds |
| Random Forest accuracy | 93.8% displayed; 15/16 in matrix | 92.9% in conclusions | Report exact 93.75% from linked matrix |
| MLP accuracy | 81.2% displayed; 13/16 in matrix | 92.9% in conclusions | Report exact 81.25% from linked matrix |
| Random Forest kappa | 0.9024 in figure; 0.902 in prose | 0.89 in conclusions | Use 0.9024 |
| MLP kappa | 0.7091 | 0.89 in conclusions | Use 0.7091 |
| Preliminary speaker result | Separate normalized speaker matrix | Abstract mentions "so far 85%" | Do not merge 85% with effectiveness accuracy |

The linked poster's confusion matrices are:

```text
Rows = actual low, medium, high; columns = predicted low, medium, high

Random Forest                 Multilayer perceptron
4  1  0                       3  2  0
0  7  0                       0  6  1
0  0  4                       0  0  4
```

Class supports are therefore 5, 7, and 4. Random Forest's only error is a low meeting predicted medium. The poster's statement that medium was harder for Random Forest confuses the affected precision and recall: medium precision is 7/8, but medium recall is 7/7. MLP has four correct high predictions and one false high prediction, so high precision is 4/5, not 1.0.

Random Forest MAE/RMSE are 0.2129/0.2612; MLP MAE/RMSE are 0.1758/0.3269. Lower MAE alone is not proof of better probability calibration. Do not combine the earlier poster's probability errors with the linked poster's matrices.

The draft's macro-F1 and balanced accuracy are new arithmetic summaries of the poster matrices, not new model results. `build_figures.py` recalculates them and checks kappa against the displayed summaries. No confidence interval is claimed from independent meeting trials because the sampling dependencies and validation design are unknown. The 7/16 majority-class reference is explicitly a full-dataset descriptive reference, not a cross-validated baseline.

## Source-to-claim mapping

The application-code evidence below was reviewed at revision `85e0fbce5203ae2757550a50a6c344bf00704469`; the collection, labeling, feature extraction, and legacy firmware files are unchanged in the paper branch base `5a9d5f8`. Local-data claims additionally use the file hashes in `local_data_audit.json`. Neither revision is established as the version deployed for the historical experiments.

| Manuscript material | Evidence location |
| --- | --- |
| Allowlist, receipt timestamps, CSV fields, optional GR | `Data Collection & Visualization/data_collection.py`, `create_notification_handler`, `save_to_csv`, `Scan_Devices` |
| Legacy hardware and scalar sound/motion calculations | `badge code/badge (1) acc.ino` and `badge (1) bk.ino` |
| Thresholds, normalization, candidate rules, centered vote | `Data Cleanup and Normalization/auto_label.py`, `__init__`, `compute_speech_presence`, `apply_peak_labeling` |
| Smoothing and dominant speaker resolution | Same file, `post_process_labels`, `add_speaker_column` |
| Separate 20 s rolling statistics | `Data Cleanup and Normalization/badge_data_processor.py`, `calculate_rolling_statistics` |
| Manual/automatic comparison tool | `Data Cleanup and Normalization/label_comparison.py` plus recovered comparison files; the saved matrix is reconstructed, with annotation and join limitations detailed below |
| 500 ms aggregation, turns, duration and participation measures | `Feature Extraction/feature_extraction.py`, `aggregate_to_bins`, `extract_turns`, `_slice_features` |
| Participant/window conventions | Same file, `compute_participant_features`, `compute_window_features` |
| 36 predictors, human label-entry interface, ARFF class | `Feature Extraction/weka_exporter.py`, feature lists, `flatten_meeting`, `meeting_summary`, `write_arff` |
| Independent later hardware/viewer development | `Nano33SenseRev2_SerialRealtime/README.md` and firmware |
| Historical 16-record classifier results | Kent State poster, embedded model summaries and confusion matrices transcribed in `derived_metrics.json` |
| Recovered sample and feature export | `audit_local_data.py`, `local_data_audit.json`, and the 53 hashed local inputs |
| Speaker diagnostic | Presentation transcription in `supplementary_evaluations.json`, independently reconstructed from the saved local comparison rows |
| Previous 14-meeting experiment | `COF Poster - SCI Smart Badge - Austin Sternberg.pdf`, not combined with linked results |

## Implementation issues affecting a future rerun

The algorithm concerns below come from the reviewed application source. The local audit additionally verifies constant self-succession features, duplicate-key multiplicities, and unknown-label handling. No application code or original data was changed for this paper revision.

- **Normalization and causality:** startup quartiles use the whole badge recording; the five-bin vote is centered. The denominator floor of 1 also depends on the physical/native scale of acceleration. Freeze and document units before interpreting the relative contribution of sound and motion.
- **Post-processing:** run metadata are built before short active periods are removed and are then reused for merging. The short-gap check uses adjacent numerical row indices after badge grouping, which need not be adjacent samples of the same badge. Treat stated smoothing thresholds as intended operations, not verified guarantees.
- **Sampling and signal definitions:** the poster's 16 Hz reporting rate differs from the legacy sketches' 100 ms delay. The legacy sound calculation uses an integer sum of squared samples and divides by buffer byte size, creating overflow/scaling concerns; the later Rev2 RMS implementation is different. Confirm the actual deployed firmware rather than using one version to describe another.
- **Missing bins:** the turn extractor detects changes in the observed speaker sequence but does not explicitly insert missing bins or break runs at time discontinuities. Distinguish packet absence from true silence and elapsed time from observed-bin time.
- **Gini and entropy:** group calculations include only detected speakers. Add zero-duration attendees for a full-attendee measure, label the revised metric distinctly, and rerun rather than retroactively changing reported values. For one detected speaker, current Gini is zero, which must not be read as full-group equity.
- **Back-to-back turns:** a first turn has zero prior gap and can enter the numerator. Use eligible between-turn transitions if the intended quantity is the proportion of transitions with no silence.
- **Self-succession:** the code checks `prev_speaker == badge` with a positive gap, although the immediately previous run in that situation is silence. `prev_real_speaker` is the available variable appropriate to the intended measure.
- **Window boundaries:** whole turns belong to their onset window. Clipping turns at boundaries would define a different feature and requires recomputation. Temporal slopes use window indices after dropping missing values, not actual elapsed time.
- **Redundancy and overlap:** speaking and silence ratios are complements; a one-speaker sequence does not measure overlap or prove interruption. Evaluate a parsimonious feature set within training folds.

## Submission preparation

Keep the results framed as perceived effectiveness classification, not established engagement measurement. Add a majority-class baseline, a simple regularized classifier, sound-only versus sound-plus-motion ablations, and grouped validation when data permit. Do not infer causal benefits, robust feature importance, privacy guarantees, or on-device/live prediction from the present results.

The manuscript cites verified primary literature rather than reproducing the poster's incomplete cross-study performance table. Open Badges is cited through its verified 2017 arXiv preprint; a 2016 workshop version also exists, but the bibliography deliberately uses one unambiguous source. No journal template, publication year for the project poster, institutional review number, or funding attribution was invented.

## Files and rebuilding

- `manuscript.typ`: primary editable typesetting source, with single-line numbered ASCII equations, padded tables, and bibliography support.
- `manuscript.md`: companion editable text and optional source for export regeneration.
- `manuscript.pdf`: PDF compiled from Typst.
- `references.bib`: bibliography for subsequent LaTeX/venue-template conversion.
- `figures/`: original diagrams and redrawn confusion matrices in PNG, SVG, and PDF.
- `derived_metrics.json`: arithmetic checks from poster counts with provenance.
- `build_paper.py`: compile the editable Typst manuscript with the installed or locally cached compiler.
- `build_figures.py`: redraw figures and verify arithmetic; does not train models or touch application code.
- `audit_local_data.py`: reproduce the saved feature export and speaker comparison without changing inputs.
- `local_data_audit.json`: audit results, sample metadata, and SHA-256 hashes of the 53 local data inputs.
- `supplementary_evaluations.json`: historical presentation results and recovered comparison counts.

Compile the main PDF with `python paper/build_paper.py`. No online Typst packages are required. `build_figures.py` redraws the SVG figures; `export_typst.py` refreshes Typst from Markdown but overwrites direct Typst edits. Author action items are maintained here. The manuscript and Markdown companion retain the scientific limitations, not an author-query checklist. Resolve the questions above and apply the selected venue requirements before submission.

## Historical presentation evidence

During the original manuscript preparation, the following material was visually transcribed from embedded figures and checked against slide text. The local-data audit verifies the adaptive binary and speaker-state counts; it does not independently verify the other presentation experiments. Source titles are kept here, not in the standalone manuscript. No new models were trained. `supplementary_evaluations.json` preserves counts, derived metrics, and reported scores.

- **Smart Badge - Feb 6.pptx**, dated February 6, 2026, slide 11: initial binary activity comparison. Manual active/inactive rows and automatic active/inactive columns give [[14003, 54898], [6388, 140693]]. Earlier slides describe fixed 1 s windows; this is not the current adaptive configuration.
- **Smart Badge - April 3.pptx**, dated April 3, 2026, slide 9: reported binary accuracy 0.8570, precision 0.6712, recall 0.3070, specificity 0.9693. The adjacent 7x7 matrix is a separate speaker-state comparison, not its binary count matrix. Its file labels are `processed_badge_data_20260225_103434.csv` and `hacksu_d3_2.3.csv`. The local files now reproduce these counts; see the recovery section. The seven states are Badge01, Badge04, Badge05, Badge07, Badge09, Badge10, and no_speaker. This matrix supplies the raw counts underlying the rounded normalized speaker matrix used previously.
- **April 3**, slide 12: statistics are displayed to inform effectiveness labeling. This supports a stronger construct-validity limitation than merely noting that the interface could display them. Rater identity, original rating instrument, and the exact procedure used for the 16-record dataset remain unresolved.
- **April 3**, slide 13: Naive Bayes 7/10 and J48 10/10 under stratified cross-validation, with class supports 3/3/4. Slide image positions and caption positions establish classifier attribution. A recommendation for leave-one-out validation elsewhere does not establish the fold count actually used.
- **Smart Badge Software Implementation.pptx**, undated, slide 8: supervised binary MLP, 66% training split, 15,850 test observations, 15,771 correct. Matrix order is not_active, active. This is neither the heuristic agreement result nor a meeting-effectiveness experiment. Training features, exact label provenance, and recording/participant independence need recovery before stronger interpretation.

The presentation experiments remain separately reported from the 16-record classifier evaluation. The recovered speaker comparison now has a matching classification-record interval; overlap of the earlier ten-record and supervised activity experiments, tuning history, and exact software revisions remain unknown. The 100% ten-meeting result and 99.5016% sample result must not replace the principal meeting-classification results or be presented as independent replication.

## Local-data recovery and reproducibility audit

Run `python paper/audit_local_data.py` from the repository root. It reads the ignored local data directories, writes `paper/local_data_audit.json`, and leaves source data untouched. `--data-root` accepts another checkout containing the data. Python, NumPy, and pandas are required. The audit imports the existing exporter and repeats its saved-table aggregation; it does not rerun sensor labeling, train models, or claim independent end-to-end reproduction. The JSON contains relative paths and SHA-256 hashes of all 53 data inputs, aggregate diagnostics, and per-record metadata, but no participant names or raw sensor rows.

- `Feature Extraction/weka_outputs/meeting_dataset.csv` and `.arff`: 16 rows; 36 predictors; class supports 5/7/4. No missing predictor values. Both self-succession aggregates are identically zero. All 48 meeting/participant/window tables are present and reproduce the CSV features within absolute tolerance 1e-12 plus relative tolerance 1e-10. The ARFF agrees within its six-decimal rounding tolerance. This is strong consistency evidence but cannot authenticate an absent WEKA run log.
- `currentdata/label_comparison/comparison_20260304_103134/label_comparison_20260304_103134.csv`: reproduces from the two original inputs, including row multiplicities. Binary TP/TN/FP/FN are 14,174/219,087/6,943/31,992; the 7x7 speaker matrix exactly matches the presentation transcription. The 1,445 bins with multiple manually active badges are reduced by active-row count (alphabetical ties). The implementation's per-row overlap flag is cumulative; the audit independently counts overlap from active badge counts instead of using that flag.
- The manual input filename contains February 25, but the comparison's recorded interval is **2026-02-23 17:08:32.703 to 17:53:18.774**, exactly matching the metadata for `hacksu_meeting_3`. Do not infer acquisition dates from processing filenames. Equal intervals support dataset overlap; they do not verify that the same automatic-label version fed the classifier features.
- The manual/automatic files contain 269,667/272,096 rows and 50/2,479 duplicate badge-timestamp keys beyond the first. Both have the same 269,617 unique keys. The many-to-many join produces 272,196 rows, 2,579 beyond the unique-key count. The saved `Dropped rows: -2629` is not a meaningful coverage statistic. No deduplication rule was invented, and historical metrics were not silently replaced.
- Most manual rows are `unknown`, which the comparison normalizes to inactive. The paper now describes agreement under this coding convention rather than assuming verified negative annotations. Annotator instructions, annotation completeness, and inter-rater agreement remain unresolved.

The manuscript now separates recovered facts from historical classifier scores and remaining author queries. The local feature outputs include participant names; these remain in ignored local data, not in the paper or audit artifact. The worktree data directories are junctions to the original checkout, so any future data-processing writes would affect that original data too.
