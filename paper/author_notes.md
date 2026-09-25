# Author notes and evidence ledger

These notes accompany `manuscript.typ`; they are not part of the submission text. The manuscript is a substantive first draft for a conference or journal, not a claim that the feasibility study has been reproduced or that it is ready for submission. It uses a conventional two-column layout with 10-point Times New Roman. This is not a claim of compliance with a particular venue's template.

The paper is written as a standalone feasibility study. Its authors are Austin Sternberg, Bishop Harsch, and JungYoon Kim, as directed by the user. Kim is listed as a coauthor rather than separately acknowledged for supervision. Source reconciliation is retained here for author review and is excluded from the paper. No new experiments were conducted during this revision.

## Most important items to resolve

1. **Recover the 16-meeting experimental package.** Obtain the exact ARFF, original WEKA logs, classifier settings, fold seed/assignments, predictions, firmware revision, and analysis revision. The supplied materials include software, posters, and presentation summaries, not the underlying 16-meeting study data. Do not rerun corrected code and silently present its results as the original experiment.
2. **Establish label independence.** The poster calls labels self-reported. April 3 slide 12 explicitly says key statistics are displayed to inform the label decision; the exporter also displays predictors alongside an effectiveness rubric. The manuscript now describes manual, feature-informed labels rather than assuming independent self-reports. Determine who rated each meeting, when, with which questions, and whether the displayed features influenced ratings. This distinction can change the scientific interpretation of the entire classification result.
3. **Describe the actual sample.** Sixteen meetings does not establish the number of participants or independent groups. Add recruitment, unique participant/team counts, recurring membership, meeting duration and tasks, room conditions, exclusions, and badge placement.
4. **Validate the speaker estimates.** The poster has a six-badge speaker confusion matrix with low recalls. Identify the recordings and configuration behind that matrix and whether it applies to the classification dataset. April 3 slide 9 supplies raw counts for one comparison: 2,724/5,373 correct speaker states (50.70%). Recover independently annotated intervals and establish coverage before generalizing that result across meetings.
5. **Complete authorship, ethics, and funding details.** The poster lists three project members and an advisor; it does not settle paper authorship or document consent, review approval/exemption, funding, or individual contributions. Unresolved study-administration details remain author queries in these notes.
6. **Choose the venue and paper category.** The strongest current framing is a feasibility/system paper with transparent limitations. A full journal empirical paper would benefit from a larger evaluation, documented independent ratings, and validation on new teams.

## Poster versions and numerical reconciliation

The linked Kent State poster is the primary results source requested by the user. Its publication date is not established; it is not assumed to be chronologically newer solely because it contains more meetings.

| Item | Linked poster | PDF already in repository | Treatment in draft |
| --- | --- | --- | --- |
| Meetings | 16 | 14 | Use 16 for the described experiment |
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

All code references below refer to revision `85e0fbce5203ae2757550a50a6c344bf00704469`.

| Manuscript material | Evidence location |
| --- | --- |
| Allowlist, receipt timestamps, CSV fields, optional GR | `Data Collection & Visualization/data_collection.py`, `create_notification_handler`, `save_to_csv`, `Scan_Devices` |
| Legacy hardware and scalar sound/motion calculations | `badge code/badge (1) acc.ino` and `badge (1) bk.ino` |
| Thresholds, normalization, candidate rules, centered vote | `Data Cleanup and Normalization/auto_label.py`, `__init__`, `compute_speech_presence`, `apply_peak_labeling` |
| Smoothing and dominant speaker resolution | Same file, `post_process_labels`, `add_speaker_column` |
| Separate 20 s rolling statistics | `Data Cleanup and Normalization/badge_data_processor.py`, `calculate_rolling_statistics` |
| Manual/automatic comparison tool | `Data Cleanup and Normalization/label_comparison.py`; existence of tool is not evidence of completed validation |
| 500 ms aggregation, turns, duration and participation measures | `Feature Extraction/feature_extraction.py`, `aggregate_to_bins`, `extract_turns`, `_slice_features` |
| Participant/window conventions | Same file, `compute_participant_features`, `compute_window_features` |
| 36 predictors, human label-entry interface, ARFF class | `Feature Extraction/weka_exporter.py`, feature lists, `flatten_meeting`, `meeting_summary`, `write_arff` |
| Independent later hardware/viewer development | `Nano33SenseRev2_SerialRealtime/README.md` and firmware |
| 16-meeting results and speaker diagnostic | Linked poster, embedded model summaries and confusion matrices, visually inspected |
| Previous 14-meeting experiment | `COF Poster - SCI Smart Badge - Austin Sternberg.pdf`, not combined with linked results |

## Implementation issues affecting a future rerun

These are observations from reading the current source, not experimentally measured effects and not changes made to application code for this writing task.

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

- `manuscript.typ`: primary editable typesetting source, with numbered ASCII equations and bibliography support.
- `manuscript.md`: companion editable text and optional source for export regeneration.
- `manuscript.pdf`: PDF compiled from Typst.
- `references.bib`: bibliography for subsequent LaTeX/venue-template conversion.
- `figures/`: original diagrams and redrawn confusion matrices in PNG, SVG, and PDF.
- `derived_metrics.json`: arithmetic checks from poster counts with provenance.
- `build_paper.py`: compile the editable Typst manuscript with the installed or locally cached compiler.
- `build_figures.py`: redraw figures and verify arithmetic; does not train models or touch application code.

Compile the main PDF with `python paper/build_paper.py`. No online Typst packages are required. `build_figures.py` redraws the SVG figures; `export_typst.py` refreshes Typst from Markdown but overwrites direct Typst edits. Author queries remain in the Markdown companion and these notes, and are excluded from the typeset paper. Confirm the final author list, affiliation, missing study details, and venue-specific requirements before submission.

## Presentation evidence added in this revision

The following material was visually transcribed from embedded figures and checked against slide text. Source titles are kept here, not in the standalone manuscript. No new models were trained. `supplementary_evaluations.json` preserves counts, derived metrics, and reported scores.

- **Smart Badge - Feb 6.pptx**, dated February 6, 2026, slide 11: initial binary activity comparison. Manual active/inactive rows and automatic active/inactive columns give [[14003, 54898], [6388, 140693]]. Earlier slides describe fixed 1 s windows; this is not the current adaptive configuration.
- **Smart Badge - April 3.pptx**, dated April 3, 2026, slide 9: reported binary accuracy 0.8570, precision 0.6712, recall 0.3070, specificity 0.9693. The adjacent 7x7 matrix is a separate speaker-state comparison, not its binary count matrix. Its file labels are `processed_badge_data_20260225_103434.csv` and `hacksu_d3_2.3.csv`. The seven states are Badge01, Badge04, Badge05, Badge07, Badge09, Badge10, and no_speaker. This matrix supplies the raw counts underlying the rounded normalized speaker matrix used previously.
- **April 3**, slide 12: statistics are displayed to inform effectiveness labeling. This supports a stronger construct-validity limitation than merely noting that the interface could display them. Rater identity, original rating instrument, and the exact procedure used for the 16-meeting dataset remain unresolved.
- **April 3**, slide 13: Naive Bayes 7/10 and J48 10/10 under stratified cross-validation, with class supports 3/3/4. Slide image positions and caption positions establish classifier attribution. A recommendation for leave-one-out validation elsewhere does not establish the fold count actually used.
- **Smart Badge Software Implementation.pptx**, undated, slide 8: supervised binary MLP, 66% training split, 15,850 test observations, 15,771 correct. Matrix order is not_active, active. This is neither the heuristic agreement result nor a meeting-effectiveness experiment. Training features, exact label provenance, and recording/participant independence need recovery before stronger interpretation.

The presentation experiments are kept separate from the 16-meeting experiment. Their sample overlap, tuning history, and exact software revisions are unknown. The 100% ten-meeting result and 99.5016% sample result must not replace the principal meeting-classification results or be presented as independent replication.
