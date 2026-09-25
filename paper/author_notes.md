# Author notes and evidence ledger

These notes accompany `manuscript.typ`; they are not submission text. The draft remains venue-neutral, as requested. The author list is Austin Sternberg, Bishop Harsch, and JungYoon Kim, affiliated with the Smart Communities and IoT Laboratory, Kent State University.

## Issues addressed in this revision

| Issue | Evidence and disposition |
| --- | --- |
| Classifier provenance | Recovered `~/wekafiles/weka.log`, which records the 16-instance relation and RF/MLP settings. WEKA 3.8.6 with those settings and explicit 10-fold evaluation seed 1 matches both reported confusion matrices, accuracy, kappa, MAE, and RMSE. The original fold seed, data hash, and per-record predictions were not logged; the new run is a numerical reconstruction, not proof of the historical fold assignments. |
| Feature reproduction | All 16 saved auto-labeled files reproduce all 48 feature tables with the unchanged extractor's default settings. All 576 exported predictor values reproduce from those tables, and the ARFF matches the CSV at six decimals. Automatic labeling and deployed firmware remain outside this reproduction boundary. |
| Baselines and grouping | Added paired WEKA ZeroR and fixed-ridge Logistic baselines, leave-session-out checks, and exploratory leave-context-out checks. All folds and probabilities are saved. Every evaluated fold shares participant-name strings across training/test. Name-overlap components contain 12 and four records; one component has no medium class, preventing a complete two-way three-class participant-group evaluation. |
| Effectiveness-label source | Austin confirms assigning low/medium/high from automatic-label outputs. These are researcher-assigned, sensor-informed judgments, not independent participant self-reports. The manuscript now states the resulting circularity rather than assuming independent labels. |
| Meaning of unknown | Austin confirms unknown means never annotated. Historical negative-class and full speaker-state accuracy claims are withdrawn as validation claims; their arithmetic is retained only as a historical comparison. |
| Duplicate-safe annotation analysis | The new validator collapses concordant duplicate keys, excludes conflicting keys, and uses a one-to-one join. Neither input has conflicting label keys. Of 269,617 unique matched keys, 45,472 are annotated active and none inactive; 14,019 active keys are detected (30.83% conditional recall). Overall accuracy, precision, and specificity are unavailable. |
| Collection context and consent | Austin reports private meetings he attended and two small classroom lectures taught by a lab member. He reports all participants consented. This is author confirmation, not independent consent documentation. |
| Ethics review and funding | Austin states no institutional ethics/IRB review was obtained and no funding was received. No review approval or exemption is claimed. Consent does not imply institutional review. These facts are disclosed in the manuscript. |
| Contributions | Austin: data collection and effectiveness labeling. Bishop: initial auto-labeler foundation and post-collection processing. Dr. Kim: research supervision, badge hardware, and laboratory resources. Austin and Bishop jointly presented the poster. |
| Venue and formatting | Remain venue-neutral. All five numbered equations fit on one line. Tables use 5 pt horizontal padding and an automatically sized feature-count column. The PDF is built with installed Typst 0.14.2. |

Author-provided facts are recorded in `author_confirmations.json`, dated 2026-09-25. They are distinguished from file-derived findings. No participant names or raw sensor records are included in the new audit outputs.

## What remains unresolved

1. **Independent effectiveness measurement requires new labels.** A retrospective classifier rerun cannot make labels derived from automatic outputs independent. Obtain ratings collected without the predictor display and a defined instrument before claiming effectiveness validity. Current models estimate the existing author's judgments.
2. **Complete speaker validation requires new annotation.** Only 16.87% of unique badge-timestamp keys are explicitly annotated, all active. Annotate speech and non-speech across defined intervals, record overlap, and establish inter-rater agreement. The 30.83% value is conditional recall on the annotated subset, not full-recording recall or overall accuracy.
3. **Participant-independent evaluation needs verified identities and broader class coverage.** There are 29 normalized name strings, not 29 verified individuals. Resolve aliases, document attendance/recruitment and tasks, and obtain data supporting all classes across independent groups. Session/context-held-out results do not solve participant overlap.
4. **Historical collection details remain incomplete.** The deployed firmware revision, calibration/units, badge placement, exact effectiveness-rating times, exclusions, and original evaluation seed/folds are not established by the recovered artifacts. Observed packet timing is now measured, but it does not identify firmware.
5. **Submission-specific administration remains outstanding.** Final author approval, conflicts-of-interest declarations, and the selected venue's submission requirements have not been supplied. There is no claim of ethics approval or exemption. Venue selection is intentionally deferred, not a missing task for this revision. Study setting and participant consent are described in Methods; funding and author contributions appear in Declarations after the conclusion. The manuscript speaks directly in the authors' voice; attribution of these facts to author confirmation is retained only in this evidence ledger.

## Reproduction and new evaluation results

The reconstructed 10-fold seed-1 results are: ZeroR 7/16, ridge Logistic 11/16, Random Forest 15/16, and MLP 13/16. Keeping the two April 3 SCI segments together in 15 leave-session-out folds gives the same correct totals. Leaving out each of the three recorded contexts gives 4/16, 10/16, 16/16, and 13/16 respectively. The context-held-out 100% RF score is an exploratory result on the same feature-informed labels with participant overlap, not independent replication or proof of generalization.

Logistic uses ridge 1.0 with WEKA's training-fold standardization and optimization to convergence; no hyperparameter search was performed. RF and MLP use the recovered command strings. WEKA's evaluation seed 1 is distinct from RF's model seed 1 and MLP's model seed 0. Input ARFF precision and order are preserved. The original features, including constant self-succession columns and known conventions below, are retained.

`weka_evaluation.json` records model settings, source-log and ARFF hashes, WEKA JAR hash, Java/WEKA versions, train/test IDs, shared-name counts, class counts, predictions, probabilities, and metrics. It reconstructs fold membership from WEKA's output and checks that models use paired folds and each record is tested exactly once per protocol.

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

The draft's macro-F1 and balanced accuracy are new arithmetic summaries of the poster matrices, not new model results. `build_figures.py` recalculates them and checks kappa against the displayed summaries. No confidence interval based on independent meeting trials is claimed because the records share participants and feature-informed labeling. The original 7/16 full-dataset majority reference has now been supplemented by a paired training-fold ZeroR baseline, which also obtains 7/16.

## Source-to-claim mapping

The application-code evidence below was reviewed at revision `85e0fbce5203ae2757550a50a6c344bf00704469`; the collection, labeling, feature extraction, and legacy firmware files are unchanged in the paper branch base `5a9d5f8`. Local-data claims additionally use file hashes in `local_data_audit.json`, `feature_source_audit.json`, `annotation_validation.json`, and `weka_evaluation.json`. Neither revision is established as the version deployed for the historical experiments.

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
| Classifier results and settings | Poster transcription in `derived_metrics.json`; recovered WEKA application-log commands and numerical reconstruction in `weka_evaluation.json` |
| Recovered sample and feature export | `audit_local_data.py`, `local_data_audit.json`, and the 53 hashed local inputs |
| Speaker diagnostic | Presentation transcription in `supplementary_evaluations.json`, independently reconstructed from the saved local comparison rows |
| Previous 14-meeting experiment | `COF Poster - SCI Smart Badge - Austin Sternberg.pdf`, not combined with linked results |

## Known implementation limits retained for reproduction

The original extractor and labeler remain unchanged so historical outputs can be reproduced. Reproduction does not validate their behavioral interpretation. The concerns below are not marked fixed by the new classifier runs; they define a separately versioned future feature/labeling pipeline. The annotation-aware analysis already avoids duplicate joins and preserves unknown as unannotated without modifying the legacy comparison.

- **Normalization and causality:** startup quartiles use the whole badge recording; the five-bin vote is centered. The denominator floor of 1 also depends on the physical/native scale of acceleration. Freeze and document units before interpreting the relative contribution of sound and motion.
- **Post-processing:** run metadata are built before short active periods are removed and are then reused for merging. The short-gap check uses adjacent numerical row indices after badge grouping, which need not be adjacent samples of the same badge. Treat stated smoothing thresholds as intended operations, not verified guarantees.
- **Sampling and signal definitions:** the poster's 16 Hz reporting rate differs from the legacy sketches' 100 ms delay. The legacy sound calculation uses an integer sum of squared samples and divides by buffer byte size, creating overflow/scaling concerns; the later Rev2 RMS implementation is different. The source-data audit measures per-badge unique host-timestamp rates of 13.24-16.89 Hz, but this does not identify the deployed firmware or acoustic units.
- **Missing bins:** the turn extractor detects changes in the observed speaker sequence but does not explicitly insert missing bins or break runs at time discontinuities. The recovered files have 22 missing global bins across five records (0-10 per record). This count does not establish per-badge completeness. A revised extractor must distinguish packet absence from silence and elapsed time from observed-bin time.
- **Gini and entropy:** group calculations include only detected speakers. Add zero-duration attendees for a full-attendee measure, label the revised metric distinctly, and rerun rather than retroactively changing reported values. For one detected speaker, current Gini is zero, which must not be read as full-group equity.
- **Back-to-back turns:** a first turn has zero prior gap and can enter the numerator. Use eligible between-turn transitions if the intended quantity is the proportion of transitions with no silence.
- **Self-succession:** the code checks `prev_speaker == badge` with a positive gap, although the immediately previous run in that situation is silence. `prev_real_speaker` is the available variable appropriate to the intended measure.
- **Window boundaries:** whole turns belong to their onset window. Clipping turns at boundaries would define a different feature and requires recomputation. Temporal slopes use window indices after dropping missing values, not actual elapsed time.
- **Redundancy and overlap:** speaking and silence ratios are complements; a one-speaker sequence does not measure overlap or prove interruption. Evaluate a parsimonious feature set within training folds.

## Historical presentation evidence

During the original manuscript preparation, the following material was visually transcribed from embedded figures and checked against slide text. The local-data audit verifies the adaptive binary and speaker-state counts under their historical convention. Those counts are not validated negative-class performance because unknown means unannotated. The other presentation experiments have not been independently reproduced. Source titles are kept here, not in the standalone manuscript. `supplementary_evaluations.json` preserves those historical counts, derived metrics, and reported scores. New reconstruction and baseline runs are stored separately in `weka_evaluation.json`.

- **Smart Badge - Feb 6.pptx**, dated February 6, 2026, slide 11: initial binary activity comparison. Manual active/inactive rows and automatic active/inactive columns give [[14003, 54898], [6388, 140693]]. Earlier slides describe fixed 1 s windows; this is not the current adaptive configuration.
- **Smart Badge - April 3.pptx**, dated April 3, 2026, slide 9: reported binary accuracy 0.8570, precision 0.6712, recall 0.3070, specificity 0.9693. The adjacent 7x7 matrix is a separate speaker-state comparison, not its binary count matrix. Its file labels are `processed_badge_data_20260225_103434.csv` and `hacksu_d3_2.3.csv`. The local files now reproduce these counts; see the recovery section. The seven states are Badge01, Badge04, Badge05, Badge07, Badge09, Badge10, and no_speaker. This matrix supplies the raw counts underlying the rounded normalized speaker matrix used previously.
- **April 3**, slide 12: statistics are displayed to inform effectiveness labeling. This supports a stronger construct-validity limitation than merely noting that the interface could display them. The collecting author has now confirmed assigning the 16-record ratings from automatic-label outputs; a contemporaneous rating log and exact rating times remain unavailable.
- **April 3**, slide 13: Naive Bayes 7/10 and J48 10/10 under stratified cross-validation, with class supports 3/3/4. Slide image positions and caption positions establish classifier attribution. A recommendation for leave-one-out validation elsewhere does not establish the fold count actually used.
- **Smart Badge Software Implementation.pptx**, undated, slide 8: supervised binary MLP, 66% training split, 15,850 test observations, 15,771 correct. Matrix order is not_active, active. This is neither the heuristic agreement result nor a meeting-effectiveness experiment. Training features, exact label provenance, and recording/participant independence need recovery before stronger interpretation.

The presentation experiments remain separately reported from the 16-record classifier evaluation. The recovered speaker comparison now has a matching classification-record interval; overlap of the earlier ten-record and supervised activity experiments, tuning history, and exact software revisions remain unknown. The 100% ten-meeting result and 99.5016% sample result must not replace the principal meeting-classification results or be presented as independent replication.

## Files and reproducibility commands

Run from the repository root with Python, NumPy, and pandas. The WEKA runner defaults to the installed Windows WEKA 3.8.6 directory; use `--weka-home` and `--java` for another installation. Data paths are configurable with `--data-root`.

```text
python paper/audit_local_data.py
python paper/audit_feature_sources.py
python paper/validate_annotations.py
python paper/evaluate_weka.py
python paper/test_validation.py
python paper/build_paper.py
```

- `audit_local_data.py` / `local_data_audit.json`: original export and historical comparison audit, with hashes of 53 data inputs. Its binary/speaker metrics intentionally retain the historical unknown-to-inactive convention; use `annotation_validation.json` for the annotation-aware interpretation.
- `audit_feature_sources.py` / `feature_source_audit.json`: in-memory recomputation of the 48 feature tables from 16 saved auto-labeled files, 64 input hashes, timestamp-rate and missing-bin diagnostics.
- `validate_annotations.py` / `annotation_validation.json`: unique-key alignment and annotated-positive recall; unknown remains unannotated.
- `evaluate_weka.py` / `weka_evaluation.json`: numerical reconstruction, fixed baselines, and explicit session/context sensitivity protocols. Temporary split ARFFs and command output stay under ignored `paper/.tools/`.
- `test_validation.py`: regression checks for duplicate handling, preservation of unknown labels, and transitive participant grouping.
- `author_confirmations.json`: author-provided study information, with unresolved details identified.
- `manuscript.typ` and `manuscript.md`: synchronized paper content; Typst is the primary typesetting source. `export_typst.py` regenerates Typst and overwrites direct edits. `build_paper.py` compiles without regenerating it.
- `derived_metrics.json`, `supplementary_evaluations.json`, and `figures/`: retained historical arithmetic and figures. New results are identified separately.

The data directories in this worktree are junctions to the original checkout. All new research scripts read those inputs and write their results under `paper/`; they do not overwrite source sensor files, annotations, or existing feature tables. The original comparison filenames are processing identifiers: their recorded interval is February 23, 2026, matching `hacksu_meeting_3`, despite February 25 appearing in the manual filename.
