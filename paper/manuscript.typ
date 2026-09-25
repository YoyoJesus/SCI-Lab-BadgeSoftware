// Standalone Typst manuscript. Compile from the repository root:
// typst compile paper/manuscript.typ paper/manuscript.pdf
// No online Typst packages are required.
#set document(
  title: "Estimating Perceived Meeting Effectiveness from Wearable Sound and Motion Signals: A Smart Badge Feasibility Study",
  author: ("Austin Sternberg", "Bishop Harsch", "JungYoon Kim"),
)
#set page(paper: "us-letter", margin: (x: 0.65in, top: 0.75in, bottom: 0.75in), columns: 2)
#set columns(gutter: 0.25in)
#set text(font: "Times New Roman", size: 10pt, lang: "en", hyphenate: false)
#set smartquote(enabled: false)
// Bibliography styles can insert Unicode punctuation even from ASCII input.
#show "\u{2013}": "-"
#show "\u{2014}": ": "
#show "\u{2018}": "'"
#show "\u{2019}": "'"
#show "\u{201c}": "\""
#show "\u{201d}": "\""
#set par(justify: true, leading: 0.45em, first-line-indent: 1em, spacing: 0.5em)
#set heading(numbering: none)
#set math.equation(numbering: "(1)")
#set figure(gap: 5pt)
#set table(inset: (x: 5pt, y: 3pt), stroke: 0.4pt)
#show heading.where(level: 1): it => block(width: 100%, above: 11pt, below: 6pt)[#set par(justify: false, first-line-indent: 0pt); #align(center)[#text(size: 10pt, weight: "regular")[#upper(it.body)]]]
#show heading.where(level: 2): it => block(above: 8pt, below: 4pt)[#text(size: 10pt, weight: "regular", style: "italic")[#it.body]]
#show figure.caption: set text(size: 8pt)
#show raw: set text(size: 7pt)
#let feature-table(columns, ..cells) = {
  set text(size: 8pt)
  set par(justify: false, first-line-indent: 0pt)
  table(columns: columns, ..cells)
}
#let ascii-equation(number, expression) = block(above: 7pt, below: 7pt, width: 100%)[
  #set par(justify: false, first-line-indent: 0pt)
  #grid(columns: (1fr, auto), column-gutter: 6pt, align: (center, right),
    box(text(size: 9pt, expression)),
    [#text(size: 9pt)[(#number)]],
  )
]


#place(top + center, float: true, scope: "parent", clearance: 18pt)[
#block(width: 100%)[
#set par(justify: false, first-line-indent: 0pt)
#set text(hyphenate: false)
#align(center)[
#text(size: 22pt, weight: "regular")[Estimating Perceived Meeting Effectiveness \
from Wearable Sound and Motion Signals: \
A Smart Badge Feasibility Study]

#v(8pt)
#text(size: 11pt)[Austin Sternberg, Bishop Harsch, and JungYoon Kim]

#text(size: 10pt)[Smart Communities and IoT Laboratory, Kent State University]
]
]
]

*Abstract: *Wearable sensing can describe conversational participation without retaining intelligible speech. This paper presents a Bluetooth Low Energy smart badge pipeline that converts sound-level and motion measurements into estimated speaker activity and 36 session-level predictors. Sixteen records comprise private meetings and two small classroom lectures. Low, medium, and high effectiveness labels were assigned from the automatic-label outputs; the target is therefore an author-assigned, sensor-informed judgment, not an independent outcome measure. Recovered files reproduce all 48 feature tables and 576 exported predictor values. Using logged WEKA model settings and an explicit 10-fold seed-1 reconstruction, Random Forest correctly classifies 15/16 records (93.75%) and a multilayer perceptron 13/16 (81.25%), matching the reported confusion matrices and probability-error summaries. Paired majority and regularized-logistic baselines classify 7/16 and 11/16 records, respectively. A speaker-label audit finds that only 16.87% of unique badge-timestamp keys were annotated, all as active. Automatic activity recovers 30.83% of these annotated active keys; precision, specificity, and overall accuracy cannot be established because unknown time was never annotated. The results demonstrate numerical reproducibility and classification of the available judgments, while feature-informed labels, recurring participants, limited class coverage, and incomplete speech annotations preclude independent effectiveness or speaker-accuracy claims.

*Keywords:* wearable sensing; sociometric badges; meeting effectiveness; speaker activity; participation balance; Bluetooth Low Energy.

= I. Introduction

Small-group meetings involve more than the content of individual statements. The distribution of speaking time, intervals of silence, and transitions between speakers provide observable descriptions of how participants share the conversational floor. These descriptions may be useful to researchers studying collaboration and to facilitators reviewing group interaction. They do not, by themselves, establish whether participants are attentive, whether a decision is correct, or whether a meeting achieves its goals.

Wearable sociometric systems have previously used sound, motion, and proximity measurements to study organizational behavior. Olguin Olguin et al. demonstrated a wearable platform connecting measured interaction patterns with self-reported organizational outcomes. Their work provides a basis for studying nonverbal interaction features without requiring a full linguistic account of a meeting. @olguin2009sensible

This study develops a smart badge workflow for a narrower task: classifying perceived meeting effectiveness from sensor-derived interaction summaries. Each participant wears a badge that transmits sound level, acceleration, and received signal strength indicator (RSSI) to a central host. A heuristic labeler estimates speaker activity, feature extraction summarizes the meeting at several temporal and social levels, and a classifier assigns a low, medium, or high effectiveness label. The transmitted measurements summarize acoustic activity rather than retaining an intelligible audio recording.

Two inference stages must be distinguished. Speaker-state estimation assigns a badge identity or a no-speaker state to a time bin. Meeting classification maps aggregated features to an effectiveness label. Success at the second stage does not establish accuracy at the first, and neither stage directly measures cognitive engagement. Accordingly, this paper uses _perceived meeting effectiveness_ for the classification target and _estimated speaker activity_ for the intermediate measurements.

This work contributes an integrated BLE acquisition and analysis system, a mapping from estimated speaker activity to a compact meeting representation, and a feasibility evaluation that distinguishes meeting-classification performance from the accuracy of intermediate measurements. The evaluation examines three-class effectiveness prediction across 16 session records and identifies the measurement and generalization challenges that remain for broader use.

= II. Related Work

Sociometric badges established wearable measurement of conversational and physical interaction as an approach to organizational research. The platform described by Olguin Olguin et al. combines several sensing modalities and relates behavioral measurements to organizational outcomes. The present work follows this general approach but concentrates on a small-group pipeline based on acoustic level and movement, with RSSI retained in the collected records. It does not establish a new sensing modality or a new classification algorithm. @olguin2009sensible

Open Badges provides an open-source framework for collecting and visualizing face-to-face interaction data using wearable devices or smartphones. Its emphasis on accessible instrumentation and feedback is closely related to the present implementation. Here, the specific engineering focus is the integration of heuristic cross-badge labeling, multilevel meeting features, and an export path for supervised classification. A controlled comparison would be needed to establish improvements over an existing badge system. @lederman2017openbadges

Measurement validation is a separate requirement from system construction. Kayhan et al. examine wearable-badge sensing in structured meetings and develop validation procedures for sensor outputs and derived measures. Their study motivates checking both the input measurements and the interaction metrics built from them. This distinction is particularly relevant when an effectiveness classifier consumes automatically estimated speaking turns. @kayhan2018signals

WEKA supplies the classification workbench used in the project. Its established data-mining environment allows the exported meeting representation to be evaluated using multiple learning algorithms. The contribution of the present system lies in the sensing and feature workflow rather than in modifying these algorithms. @hall2009weka

Wearable interaction studies address different prediction targets and evaluation settings. Accuracy estimates for face-to-face interaction detection, speaker identification, and meeting-effectiveness classification are therefore not directly comparable without a common task and dataset.

= III. System and Methods

== A. Acquisition and data representation

The BLE host implementation discovers devices from a configured address allowlist, connects to recognized badges, and receives notifications through sensor characteristics. Each decoded observation is appended to a unified CSV file with a host-generated receipt timestamp, badge identifier, optional participant name, sound level, RSSI, acceleration, and the original scalar-data payload. The collector also permits an optional fourth numeric field named `GR`; this field is not used in the meeting representation described below.

The acquisition system targets approximately six to eight concurrently connected badges and a nominal reporting rate of 16 Hz. In the recovered auto-labeled files, mean rates of unique host timestamps per badge range from 13.24 to 16.89 Hz across records. These are observed record rates, not a benchmark of radio throughput or a measurement of the microphone sampling frequency. The deployed firmware version remains unidentified, so the legacy sketches alone do not establish its timing or signal definitions.

Badge firmware reduces microphone samples to a scalar acoustic-level measurement and summarizes movement from accelerometer readings. In the legacy implementation, the acoustic measurement is a power-like aggregate, and the movement summary is the sum of absolute changes across three axes. These values are device-specific and should not be interpreted as calibrated decibels or direct measurements of speech-induced vibration. Firmware variants that change signal definitions require recalibration before their outputs can be combined.

Time alignment uses host receipt timestamps rounded down to 500 ms bins. This establishes a common analysis grid, but it does not measure or correct device-to-host transport latency. Address allowlisting restricts which devices contribute records; it does not remove ambient acoustic noise. Figure 1 summarizes the implemented analysis path.

#figure(
  image("figures/pipeline.svg", width: 100%, alt: "Pipeline from wearable sensing to meeting classification."),
  placement: top, scope: "parent",
  caption: [Implemented research workflow. Speaker estimation and feature extraction run on recorded data; live acquisition does not imply a validated live effectiveness predictor. The 20 s descriptive-statistics utility is separate from the 36-predictor export path.],
)

== B. Adaptive speaker-activity estimation

Let s\_i(t) denote the sound measurement and a\_i(t) the acceleration summary for badge i. The labeler first compares a short rolling mean of sound with a longer rolling quantile baseline:

#ascii-equation(1, "v_i(t) = 1{m_i(t) > q_0.45^s(t)}.")

Here, m\_i(t) is the 1 s sound mean, and q\_p^x(t) is the rolling p-quantile of signal x\_i over 60 s. The indicator 1{condition} equals 1 when the condition holds and 0 otherwise.

The short window is 1 s and the baseline window is 60 s. The baseline requires at least ten observations. Sound and acceleration are separately normalized relative to each badge's rolling lower quartile and interquartile range (IQR):

#ascii-equation(2, "z_i^x = (x_i - q_0.25^x) / max(IQR_i^x, 1).")

Here, x is either sound s or acceleration a; ^x identifies the signal rather than an exponent. Time arguments are omitted in (2), and IQR\_i^x = q\_0.75^x - q\_0.25^x.

The implementation substitutes whole-recording quartiles where the rolling quartiles are initially unavailable. The lower bound of 1 in the denominator is expressed in the input signal's native units. It prevents division by a very small spread but also makes the normalization sensitive to signal scale.

The combined score is

#ascii-equation(3, "c_i(t) = z_i^s(t) + 1.2 * clip(z_i^a(t), 0, 2.5).")

Acceleration is intended to help distinguish the wearer's activity from sound received by neighboring badges. This rationale is a design hypothesis: the available evidence does not isolate speech-related vibration from gestures, posture changes, or unrelated movement.

A sample is eligible when its score is at least 0.75 and either the sound-presence condition holds or its score is at least 3.5. Within each 500 ms bin, the badge associated with the highest eligible sample score becomes the raw winner. A centered five-bin vote then requires at least three wins before the central bin is assigned active to a badge. Votes are counted over available observed bins; the threshold remains three at recording boundaries.

The code next applies per-badge post-processing intended to remove active runs shorter than 2 s, merge active periods separated by gaps shorter than 1.5 s, and fill brief inactive gaps shorter than 0.5 s. It then assigns a single `auto_speaker` per bin; when multiple active labels remain, the highest-scoring active badge determines the speaker. These parameters specify the default labeling configuration; their sensitivity to sensor conditions and participant behavior requires evaluation.

The output is thus a dominant-speaker-or-silence sequence. It does not explicitly represent simultaneous speakers. In addition, centered voting uses future bins and startup normalization may use later samples from the recording. The present algorithm is an offline procedure; a strictly causal streaming version would require changes and separate validation.

== C. Temporal representations

The analysis uses several timescales with different purposes. They should not be treated as interchangeable training instances.

#feature-table((1.2fr, 3.5fr),
  table.header([Timescale], [Role in the implementation]),
  [500 ms], [Cross-badge speaker comparison and subsequent bin-level aggregation],
  [1 s and 60 s], [Short sound mean and adaptive threshold/normalization history],
  [Five observed bins], [Centered vote stabilizing the speaker assignment],
  [20 s], [Rolling minimum, maximum, mean, and standard deviation in a separate sensor-processing utility],
  [5 min, configurable], [Non-overlapping windows for interaction summaries and temporal trends],
  [Entire meeting], [One feature vector and one effectiveness label for classification],
)

The 20 s utility computes rolling statistics at sample timestamps. These descriptive signal summaries are separate from the meeting-classification representation: the WEKA exporter consumes meeting, participant, and temporal-window feature tables.

== D. Turns and participation features

Raw observations are aggregated into one record per badge and 500 ms bin. Numeric summaries include sound and acceleration means and maxima, median RSSI, and normalized-score summaries. The feature extractor forms a speaker sequence with one state per observed bin and defines a turn as a maximal run with an unchanged non-silence speaker. A turn lasting fewer than two bins is marked as a micro-turn. This rule operates downstream of the labeler's longer active-run suppression, so micro-turn statistics depend on the full labeling procedure.

For B observed bins and S bins assigned a speaker, the speaking and silence ratios are S/B and (B - S)/B. The observed-bin duration is D = 0.5B seconds, and the turn rate is 60K/D for K turns. These quantities characterize observed coverage: if bins are missing, D can differ from the elapsed recording duration.

Let d\_i denote the total estimated speaking duration of participant i and p\_i = d\_i / sum\_j(d\_j). Participation summaries include the dominant-speaker fraction max\_i(p\_i), normalized entropy, and the Gini coefficient:

#ascii-equation(4, "H = -sum_i(p_i * ln(p_i)) / ln(n).")

#ascii-equation(5, "G = sum_i sum_j |d_i - d_j| / (2n sum_i d_i).")

The current implementation computes these group-level quantities over participants with at least one detected turn. Silent participants are omitted from that denominator. Thus, low Gini or high entropy indicates balance among detected speakers, not necessarily inclusion of all attendees. The implementation assigns entropy zero when there is only one active participant; for positive speaking duration, the uncorrected Gini coefficient has a finite-group maximum of (n - 1)/n.

Participant summaries include speaking fraction, turn duration, immediate speaker transitions, and response latency after a different speaker. Variables named "interruptions" identify a speaker change with no intervening silence bin. At 500 ms resolution and with only one represented speaker, these transitions cannot establish conversational interruption or overlap.

For temporal features, the meeting is partitioned into configurable windows, with a default width of 5 min. The current code assigns a turn's full duration to the window in which it starts, including any portion extending beyond the window boundary. Window-level speaking-bin ratios and turn-duration summaries consequently use different boundary conventions. These details matter when interpreting within-meeting trends.

== E. Meeting representation and labels

The WEKA exporter combines the three summary tables into a single row per meeting. It produces 36 numerical predictors: 12 direct meeting measures, 14 participant-aggregation measures, and 10 temporal measures. The effectiveness class gives 37 ARFF attributes. Meeting identifiers are retained in the CSV export but excluded from ARFF predictors.

#feature-table((1.1fr, 3.4fr, auto),
  table.header([Feature family], [Contents], [Number]),
  [Meeting summaries], [Speaking and silence ratios; turn rate; mean and median turn duration; back-to-back ratio; mean gap; active-participant count; Gini; entropy; dominant-speaker fraction; micro-turn ratio], [12],
  [Participant aggregates], [Mean and population standard deviation of seven measures: speaking fraction, mean turn duration, two immediate-transition ratios, response latency, self-succession count, and micro-turn ratio], [14],
  [Temporal aggregates], [Population standard deviation and linear slope for five window measures: speaking ratio, Gini, turn rate, active-participant count, and back-to-back ratio], [10],
)

Slopes are calculated against consecutive window indices rather than elapsed seconds. RSSI and raw acceleration are collected and available for inspection, but neither is directly included in the final 36 predictors; acceleration influences them indirectly through speaker labeling. Speaking and silence ratios are complementary, and other summaries may be redundant.

Austin Sternberg assigned the low, medium, and high effectiveness labels based on the automatic-label outputs. The label-entry interface displays interaction statistics and describes low as unproductive, dominated, or disorganized; medium as average with some issues; and high as balanced, structured, or productive. A contemporaneous rating log and exact rating times are unavailable. These labels are researcher judgments informed by the sensing pipeline, not participant self-reports or independent assessments of meeting outcomes. Classification can therefore learn consistency with the rater's interpretation of the automatic outputs; independent outcome validity is not established.

== F. Study setting and participant consent

We collected data during private meetings attended by Austin Sternberg and during two small classroom lectures taught by a member of our laboratory. All participants consented to data collection. We did not obtain institutional ethics review or an exemption.

= IV. Experimental Evaluation

== A. Dataset composition and evaluation protocol

The recovered classification dataset contains 16 session-level records, with five rated low effectiveness, seven medium, and four high. The CSV and ARFF agree in row order, labels, and all 36 predictors at the ARFF export precision of six decimal places. Reconstructing the exporter calculations from each record's saved meeting, participant, and window tables reproduces all 576 predictor values within numerical tolerance. No predictor values are missing; the mean and standard deviation of self-succession count are zero throughout, leaving 34 nonconstant predictors. Recomputing the unchanged feature extractor on the 16 saved auto-labeled sensor files also reproduces all 48 feature tables with default 5 min windows and a two-bin micro-turn threshold. These checks reproduce the saved-label-to-feature-to-export path, not the generation or validity of the automatic speaker labels.

Record identifiers distinguish nine SCI meeting records (four low, three medium, two high), five HacKSU meeting records (three medium, two high), and two CS1 lecture records (one low, one medium). Stored timestamps span October 10, 2025 through April 10, 2026. Record durations range from 29.15 to 76.26 min (median 45.41 min), totaling 747.56 min. Saved metadata list two to six participants per record; this is neither a verified attendance count nor a count of unique recruited participants. Two SCI records are successive segments on April 3 with the same recorded participant names. The unit of classification is consequently a labeled session record, not necessarily an independent meeting.

The recovered class counts agree with the reported experiment. A local WEKA application log records a 16-instance meeting-effectiveness relation and the Random Forest and multilayer-perceptron option strings. Using WEKA 3.8.6, those options, and 10-fold stratified cross-validation with evaluation seed 1 reproduces both reported confusion matrices, kappa values, MAE, and RMSE at their published precision. The log does not record the data hash, evaluation mode, fold seed, or original predictions; seed 1 is an explicit reconstruction assumption, not a recovered historical fact. Current input hashes, commands, fold membership, and predicted probabilities are retained with the reproducibility scripts.

Random Forest uses 100 trees, 100% bag size, automatic feature-subset size, minimum leaf weight 1, variance threshold 0.001, one execution slot, and model seed 1. The multilayer perceptron uses learning rate 0.3, momentum 0.2, 500 epochs, no validation holdout, validation threshold 20, an automatically sized hidden layer, and model seed 0. These are the recorded option values. Evaluation randomization uses seed 1, separately from each model's seed. Table 1 gives the reported results now matched by the numerical reconstruction; new baselines and sensitivity checks are distinguished below.

Additional evaluations address activity estimation and earlier classification experiments. The recovered speaker-state comparison contains 5,373 aligned 500 ms bins from a six-badge recording. Its timestamps match the start and end of the third HacKSU classification record, so it cannot be treated as an independent recording-level validation set. Binary activity comparisons operate on badge-level rows rather than bins. The overlap of the earlier ten-record effectiveness experiment and supervised activity experiment with the recovered classification records remains unresolved.

== B. Meeting-classification results

Table 1 summarizes accuracy, Cohen's kappa, mean absolute error (MAE), and root mean squared error (RMSE) for both classifiers. Macro-F1 and balanced accuracy are calculated from the integer confusion matrices. These metrics complement overall accuracy by giving each effectiveness class equal weight.

#figure(
  feature-table((2fr, 1fr, 1fr),
  table.header([Metric], [Random Forest], [Multilayer perceptron]),
  [Correct records], [15/16], [13/16],
  [Accuracy], [93.75%], [81.25%],
  [Cohen's kappa], [0.9024], [0.7091],
  [Macro-F1, derived], [0.9407], [0.8130],
  [Balanced accuracy, derived], [0.9333], [0.8190],
  [MAE], [0.2129], [0.1758],
  [RMSE], [0.2612], [0.3269],
),
  kind: table, supplement: [Table],
  caption: [Meeting-effectiveness classification with 10-fold cross-validation.],
)

Random Forest misclassified one low-effectiveness meeting as medium. The multilayer perceptron misclassified two low meetings as medium and one medium meeting as high. Both models correctly classified all four high meetings, although the multilayer perceptron also assigned high to one medium meeting. Four correct high-class predictions are insufficient to establish reliable performance in that class across new meetings or groups.

Figure 2 presents the confusion matrices. Random Forest recalls are 0.800, 1.000, and 1.000 for low, medium, and high effectiveness, respectively. Corresponding multilayer-perceptron recalls are 0.600, 0.857, and 1.000. The sole Random Forest error is a low-effectiveness meeting classified as medium. This error reduces medium-class precision to 0.875 while medium-class recall remains 1.000.

#figure(
  image("figures/confusion_matrices.svg", width: 100%, alt: "Meeting-effectiveness classification confusion matrices."),
  placement: top, scope: "parent",
  caption: [Meeting-effectiveness confusion matrices for Random Forest and the multilayer perceptron. Rows are actual labels and columns are predicted labels. Each panel summarizes reported predictions for 16 session records.],
)

The paired WEKA ZeroR majority-class baseline obtains 7/16 correct predictions (43.75%) under the same reconstructed 10-fold split. Its macro-F1 is 0.2029 and balanced accuracy is 0.3333. Unlike a full-dataset majority reference, its class prediction is learned within each training fold.

The multilayer perceptron has lower reported MAE despite lower classification accuracy and higher RMSE. These error summaries describe different properties of the predicted probabilities and do not establish superior calibration. Reconstructed probabilities are now available, but calibration has not been assessed on independent outcomes. Similarly, the two-meeting difference in correct classifications does not establish statistical superiority of one model.

== C. Speaker-state comparison

The manual annotation workflow provides a graphical interface for inspecting sensor traces and assigning activity labels. In our annotation files, unknown denotes time that was never annotated. The recovered manual file contains 45,491 active rows and 224,176 unknown rows, with no explicit inactive annotations. The historical comparison maps unknown to inactive. Consequently, its negative-class counts, overall accuracy, and full speaker-state agreement cannot be interpreted as validated speech or silence performance.

An initial fixed-window activity heuristic had reported counts of 14,003 true positives, 54,898 false negatives, 6,388 false positives, and 140,693 true negatives across 215,982 badge observations. Its accuracy was 71.62%, precision 68.67%, recall 20.32%, and specificity 95.66%. For the subsequent adaptive comparison, the recovered saved rows reproduce 14,174 true positives, 31,992 false negatives, 6,943 false positives, and 219,087 true negatives: accuracy 85.70%, precision 67.12%, recall 30.70%, and specificity 96.93%, conditional on unknown being coded inactive. These configurations were not evaluated here on a common, independently annotated sample; their difference is not a controlled estimate of improvement.

The adaptive join contains 272,196 rows but only 269,617 unique badge-timestamp keys. The manual and automatic inputs contain respectively 50 and 2,479 duplicate keys beyond the first occurrence; the many-to-many join produces 2,579 excess rows. All unique keys match between the inputs. Thus, row totals are duplicate-weighted and the saved negative dropped-row count is a join artifact, not evidence of additional annotation coverage. These historical counts are retained for traceability rather than silently replaced by a deduplicated analysis.

Reconstructing the historical speaker-state comparison exactly reproduces 2,724 matching assignments among 5,373 bins (50.70%), with macro-F1 0.4116 and balanced accuracy 0.4106 under the unknown-to-inactive convention. Table 2 preserves the corresponding reference supports and recalls for traceability; unannotated time is not verified no-speaker time. In 1,445 bins (26.89%), multiple badges have active annotations. The comparison chooses the badge with the most active rows, breaking ties alphabetically, thereby reducing overlap to a single state and retaining duplicate-row weighting.

#figure(
  feature-table((2fr, 1fr, 1fr),
  table.header([Reference state], [Support], [Recall]),
  [Badge 01], [1,431], [39.13%],
  [Badge 04], [304], [33.22%],
  [Badge 05], [866], [41.22%],
  [Badge 07], [197], [18.27%],
  [Badge 09], [259], [62.55%],
  [Badge 10], [357], [19.61%],
  [No speaker], [1,959], [73.40%],
),
  kind: table, supplement: [Table],
  caption: [Historical speaker-state comparison with unannotated time coded as no-speaker. These are not validated accuracy estimates.],
)

A new annotation-aware analysis collapses only duplicate keys with concordant labels, rejects conflicting duplicate keys, and joins each badge-timestamp key once. No conflicting keys occur in these two inputs. Of 269,617 matched unique keys, 45,472 (16.87%) have an explicit annotation, all active; 224,145 remain unannotated. The automatic labels identify 14,019 of the annotated active keys, giving conditional recall of 30.83%. This is recall on the annotated subset, not necessarily all speech. Precision, specificity, and overall binary accuracy are unavailable because there are no verified negatives. Fully annotated recordings, explicit overlap handling, and independent raters are required for a complete speaker evaluation.

== D. Earlier classification experiments

A separate ten-meeting effectiveness experiment contained three low, three medium, and four high ratings. Under stratified cross-validation, Naive Bayes classified seven meetings correctly (70%; kappa = 0.5455), while J48 classified all ten correctly (100%; kappa = 1.0000). The Naive Bayes errors comprised one low meeting assigned medium and two medium meetings assigned low. The fold count and relationship between this dataset and the 16-meeting dataset are not established. These results document an initial evaluation of the classification workflow; they do not support a direct ranking against the Random Forest and multilayer-perceptron results in Table 1.

An additional supervised activity experiment used a multilayer perceptron with a 66% training split and 15,850 held-out observations. It correctly classified 15,771 observations (99.5016%; kappa = 0.9900). The confusion matrix contains 7,888 correctly classified inactive observations, 7,883 correctly classified active observations, and 79 active observations assigned inactive. This sample-level binary result addresses a different target from meeting effectiveness and uses a learned classifier rather than the heuristic speaker estimator. Without separation by recording or participant, temporally related samples may occur on both sides of a percentage split. Its high accuracy therefore does not establish performance on new recordings or validate the deployed speaker-state pipeline.

== E. Feature interpretation

Micro-turn ratio, back-to-back ratio, and speaking ratio describe distinct aspects of floor sharing and are candidate explanatory features. Their presence in the feature set does not establish their relative predictive importance. An importance analysis or ablation study is needed to determine whether each measure contributes beyond correlated predictors. Speaker-state errors also complicate interpretation because estimated turn counts and participation measures can reflect labeling errors as well as actual interaction.

== F. New baselines and validation sensitivity

New evaluations use the same saved 36-predictor ARFF, including its original six-decimal precision, with no hyperparameter search. WEKA Logistic uses a fixed ridge parameter of 1.0, training-fold standardization, and optimization to convergence. ZeroR, Logistic, Random Forest, and the multilayer perceptron use paired test folds. Table 3 compares reconstructed 10-fold evaluation with leave-one-session-out evaluation over 15 context/date groups, keeping both April 3 SCI segments together. Fold membership, predictions, probabilities, and runtime versions are retained in the companion artifacts.

#figure(
  feature-table((1.6fr, 0.7fr, 1.1fr),
  table.header([Model], [10-fold], [Session-held-out]),
  [Majority (ZeroR)], [7], [7],
  [Ridge logistic], [11], [11],
  [Random Forest], [15], [15],
  [Multilayer perceptron], [13], [13],
),
  kind: table, supplement: [Table],
  caption: [Correct records out of 16 in paired evaluations. Session grouping does not separate recurring participants.],
)

In the reconstructed 10-fold evaluation, Logistic has macro-F1 0.6758 and balanced accuracy 0.6524. Leaving one of the three recorded contexts out gives 4/16 correct for ZeroR, 10/16 for Logistic, 16/16 for Random Forest, and 13/16 for the multilayer perceptron. These are new exploratory checks, not additional independent datasets. In particular, the perfect Random Forest context-held-out score does not resolve feature-informed labeling or participant overlap. No significance or generalization claim is made from these small, dependent comparisons.

= V. Discussion and Limitations

== A. Feasibility and construct validity

The implementation demonstrates a practical route from wearable sensor streams to a fixed-length session representation. Numerical reconstruction establishes consistency of the saved feature calculations and reported classifier summaries. However, the rater used automatic outputs to assign the target. Predictors and labels therefore share information by design: high classification accuracy may reflect the labeling procedure rather than an independently measured meeting outcome. Recurring participants and context can also contribute. These results should be interpreted as modeling author-assigned ratings, not as validation of effectiveness measurement.

Speaking balance is also not equivalent to meeting quality. A briefing can appropriately concentrate speaking time in one person; a productive planning discussion may contain silence; an attentive participant may say little. The intended use should therefore remain contextual analysis and participant reflection until independent outcome measures establish a stronger interpretation. Cognitive engagement, fairness, and objective productivity are not validated targets in this study.

== B. Sample size and evaluation independence

The dataset has 16 session records and 36 exported predictors, two of which are constant zero. Each changed prediction alters accuracy by 6.25 percentage points, making performance estimates sensitive to individual meetings. Ten-fold validation necessarily uses very small test folds, and the class counts do not permit every fold to contain all three classes. Neither the reported accuracy nor kappa resolves uncertainty from limited data or repeated participants.

Recurring membership is visible in the saved metadata: 55 of 120 record pairs share at least one normalized participant-name string. Joining records transitively by shared names produces two components of 12 and four records. Holding out the larger component leaves training data with no medium class, preventing a complete two-way three-class evaluation on these participant-group proxies. Names are not verified identities, so even these components require confirmation. All reconstructed 10-fold, session-held-out, and context-held-out folds retain some shared names between training and test. Session and context checks therefore test narrower forms of dependence, not generalization to unseen participants.

== C. Reliability of intermediate measurements

The speaker-state comparison makes intermediate validation a priority. False silence can change speaking ratios and fragment turns; speaker swaps can distort participation balance. Smoothing can suppress brief acknowledgments or merge distinct events. Missing timestamps can also create apparent continuity because the turn extractor groups consecutive observed speaker states without explicitly breaking at unobserved time bins.

Several feature conventions affect interpretation. Group equality measures omit non-speaking attendees; the first turn can enter the back-to-back numerator; and the self-succession implementation checks the preceding state even when silence intervenes. Both exported self-succession aggregates are zero in every record. The source-data audit finds 22 missing global 500 ms bins across five records, with 0-10 missing bins per record; it does not establish complete per-badge coverage. The original extractor is preserved for numerical reproduction. Corrected turn boundaries, full-attendee denominators, and window clipping would define revised features and require a separately versioned analysis.

A useful next evaluation would separately measure speech presence, speaker identity, and downstream feature error against independently annotated intervals. Sound-only and sound-plus-motion ablations would test the value of acceleration. Threshold, voting, and smoothing sensitivity analyses would establish whether classification persists under reasonable labeling changes. Simultaneous speech should be annotated explicitly rather than forced into a single-speaker state.

== D. Data minimization and participant privacy

The badge design reduces retained speech content by transmitting scalar summaries rather than a microphone waveform. The microphone nevertheless processes audio samples transiently to compute those summaries. Moreover, the collector can store participant names, device identifiers, timestamps, and behavioral histories. Avoiding intelligible audio retention is therefore a data-minimization property, not a guarantee of anonymity or complete privacy.

We retain participant names and raw records locally and exclude them from the manuscript and accompanying analysis artifacts.

== E. Toward prospective feedback

The system supports live sensing and visualization, but effectiveness prediction currently relies on recorded-data processing and whole-meeting summaries. A prospective feedback system would need a causal speaker estimator, explicitly defined trailing-window features, a measured end-to-end delay, and validation on partial meetings. The Rev2 sensor viewer provides a possible instrumentation platform, not evidence that these prediction requirements have been met.

A larger study could evaluate whether descriptive feedback changes participation and whether participants find it useful. Such an intervention should be assessed separately from classification performance. Battery life, packet delivery, cross-device calibration, and performance as the number of concurrent badges increases also require measurement before claiming deployment scalability.

= VI. Conclusion

This BLE smart badge pipeline converts sound and motion measurements into estimated speaker activity and session features. Recovered data and logged model settings reproduce the reported Random Forest and multilayer-perceptron summaries under an explicit seed-1 reconstruction. New baselines and session/context checks document the behavior of these models on the available 16 records. However, labels were assigned from automatic outputs, participants recur across folds, and most speaker-reference time was never annotated. The defensible contribution is a reproducible exploratory pipeline and a characterization of its limitations. Independent outcome ratings and fully annotated speaker data are needed to establish measurement validity.

= Declarations

*Funding.* This study received no funding.

*Author contributions.* Austin Sternberg collected the data and assigned effectiveness labels. Bishop Harsch contributed the initial automatic labeler on which the subsequent implementation was based and assisted with post-collection data processing. JungYoon Kim provided research supervision, badge hardware, and laboratory resources. Sternberg and Harsch jointly presented the poster version of the work.

#bibliography("references.bib", style: "ieee", title: [References])
