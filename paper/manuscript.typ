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
#set table(inset: 3pt, stroke: 0.4pt)
#show heading.where(level: 1): it => block(width: 100%, above: 11pt, below: 6pt)[#set par(justify: false, first-line-indent: 0pt); #align(center)[#text(size: 10pt, weight: "regular")[#upper(it.body)]]]
#show heading.where(level: 2): it => block(above: 8pt, below: 4pt)[#text(size: 10pt, weight: "regular", style: "italic")[#it.body]]
#show figure.caption: set text(size: 8pt)
#show raw: set text(size: 7pt)
#let feature-table(columns, ..cells) = {
  set text(size: 8pt)
  set par(justify: false, first-line-indent: 0pt)
  table(columns: columns, ..cells)
}
#let ascii-equation(number, ..lines) = block(above: 7pt, below: 7pt, width: 100%)[
  #set par(justify: false, first-line-indent: 0pt)
  #grid(columns: (1fr, auto), column-gutter: 6pt, align: (center, right),
    text(size: 9pt, stack(dir: ttb, spacing: 2pt, ..lines.pos().map(line => text(line)))),
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

*Abstract: *Wearable sensing can characterize conversational participation while reducing the need to retain speech content. This paper presents a Bluetooth Low Energy smart badge pipeline for estimating perceived meeting effectiveness from sound-level and motion measurements. The system collects participant-associated sensor streams, estimates a dominant speaker in 500 ms bins using adaptive sound thresholds and cross-badge comparison, and summarizes speaking activity, turn-taking, and participation balance. Meeting, participant, and temporal-window summaries are combined into 36 numerical predictors for three-class classification in WEKA. A feasibility evaluation comprised 16 meetings labeled low, medium, or high effectiveness and used 10-fold cross-validation. The classification results show 15 of 16 correct predictions for Random Forest (93.75%; Cohen's kappa = 0.9024) and 13 of 16 for a multilayer perceptron (81.25%; kappa = 0.7091). However, a separate six-badge speaker-state comparison achieves only 50.70% accuracy across 5,373 observations, with substantial missed speech and attribution errors. The results therefore support preliminary feasibility of classifying the available meeting labels, rather than established measurement accuracy or generalization to new groups. The principal contributions are an inspectable sensing-to-feature pipeline, explicit definitions of its interaction measures, and an analysis of the validation requirements for content-minimizing meeting analytics. Larger independently labeled datasets, grouped evaluation, and stronger speaker-state validation are needed before deployment as an effectiveness assessment tool.

*Keywords:* wearable sensing; sociometric badges; meeting effectiveness; speaker activity; participation balance; Bluetooth Low Energy.

= I. Introduction

Small-group meetings involve more than the content of individual statements. The distribution of speaking time, intervals of silence, and transitions between speakers provide observable descriptions of how participants share the conversational floor. These descriptions may be useful to researchers studying collaboration and to facilitators reviewing group interaction. They do not, by themselves, establish whether participants are attentive, whether a decision is correct, or whether a meeting achieves its goals.

Wearable sociometric systems have previously used sound, motion, and proximity measurements to study organizational behavior. Olguin Olguin et al. demonstrated a wearable platform connecting measured interaction patterns with self-reported organizational outcomes. Their work provides a basis for studying nonverbal interaction features without requiring a full linguistic account of a meeting. @olguin2009sensible

This study develops a smart badge workflow for a narrower task: classifying perceived meeting effectiveness from sensor-derived interaction summaries. Each participant wears a badge that transmits sound level, acceleration, and received signal strength indicator (RSSI) to a central host. A heuristic labeler estimates speaker activity, feature extraction summarizes the meeting at several temporal and social levels, and a classifier assigns a low, medium, or high effectiveness label. The transmitted measurements summarize acoustic activity rather than retaining an intelligible audio recording.

Two inference stages must be distinguished. Speaker-state estimation assigns a badge identity or a no-speaker state to a time bin. Meeting classification maps aggregated features to an effectiveness label. Success at the second stage does not establish accuracy at the first, and neither stage directly measures cognitive engagement. Accordingly, this paper uses _perceived meeting effectiveness_ for the classification target and _estimated speaker activity_ for the intermediate measurements.

This work contributes an integrated BLE acquisition and analysis system, a mapping from estimated speaker activity to a compact meeting representation, and a feasibility evaluation that distinguishes meeting-classification performance from the accuracy of intermediate measurements. The evaluation examines three-class effectiveness prediction across 16 meetings and identifies the measurement and generalization challenges that remain for broader use.

= II. Related Work

Sociometric badges established wearable measurement of conversational and physical interaction as an approach to organizational research. The platform described by Olguin Olguin et al. combines several sensing modalities and relates behavioral measurements to organizational outcomes. The present work follows this general approach but concentrates on a small-group pipeline based on acoustic level and movement, with RSSI retained in the collected records. It does not establish a new sensing modality or a new classification algorithm. @olguin2009sensible

Open Badges provides an open-source framework for collecting and visualizing face-to-face interaction data using wearable devices or smartphones. Its emphasis on accessible instrumentation and feedback is closely related to the present implementation. Here, the specific engineering focus is the integration of heuristic cross-badge labeling, multilevel meeting features, and an export path for supervised classification. A controlled comparison would be needed to establish improvements over an existing badge system. @lederman2017openbadges

Measurement validation is a separate requirement from system construction. Kayhan et al. examine wearable-badge sensing in structured meetings and develop validation procedures for sensor outputs and derived measures. Their study motivates checking both the input measurements and the interaction metrics built from them. This distinction is particularly relevant when an effectiveness classifier consumes automatically estimated speaking turns. @kayhan2018signals

WEKA supplies the classification workbench used in the project. Its established data-mining environment allows the exported meeting representation to be evaluated using multiple learning algorithms. The contribution of the present system lies in the sensing and feature workflow rather than in modifying these algorithms. @hall2009weka

Wearable interaction studies address different prediction targets and evaluation settings. Accuracy estimates for face-to-face interaction detection, speaker identification, and meeting-effectiveness classification are therefore not directly comparable without a common task and dataset.

= III. System and Methods

== A. Acquisition and data representation

The BLE host implementation discovers devices from a configured address allowlist, connects to recognized badges, and receives notifications through sensor characteristics. Each decoded observation is appended to a unified CSV file with a host-generated receipt timestamp, badge identifier, optional participant name, sound level, RSSI, acceleration, and the original scalar-data payload. The collector also permits an optional fourth numeric field named `GR`; this field is not used in the meeting representation described below.

The acquisition system is designed for approximately six to eight concurrently connected badges and a nominal sensor reporting rate of 16 Hz. Effective reporting rates depend on firmware timing, BLE transport, and host scheduling; these operating targets should not be interpreted as a throughput benchmark. Microphone sampling occurs at a higher rate than the transmission of scalar acoustic measurements.

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

#ascii-equation(2, "z_i^x(t) = [x_i(t) - q_0.25^x(t)]", "/ max(q_0.75^x(t) - q_0.25^x(t), 1).")

Here, x is either sound s or acceleration a; ^x identifies the signal rather than an exponent.

The implementation substitutes whole-recording quartiles where the rolling quartiles are initially unavailable. The lower bound of 1 in the denominator is expressed in the input signal's native units. It prevents division by a very small spread but also makes the normalization sensitive to signal scale.

The combined score is

#ascii-equation(3, "c_i(t) = z_i^s(t)", "+ 1.2 * clip(z_i^a(t), 0, 2.5).")

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

#ascii-equation(5, "G = sum_i(sum_j(abs(d_i - d_j)))", "/ (2 * n * sum_i(d_i)).")

The current implementation computes these group-level quantities over participants with at least one detected turn. Silent participants are omitted from that denominator. Thus, low Gini or high entropy indicates balance among detected speakers, not necessarily inclusion of all attendees. The implementation assigns entropy zero when there is only one active participant; for positive speaking duration, the uncorrected Gini coefficient has a finite-group maximum of (n - 1)/n.

Participant summaries include speaking fraction, turn duration, immediate speaker transitions, and response latency after a different speaker. Variables named "interruptions" identify a speaker change with no intervening silence bin. At 500 ms resolution and with only one represented speaker, these transitions cannot establish conversational interruption or overlap.

For temporal features, the meeting is partitioned into configurable windows, with a default width of 5 min. The current code assigns a turn's full duration to the window in which it starts, including any portion extending beyond the window boundary. Window-level speaking-bin ratios and turn-duration summaries consequently use different boundary conventions. These details matter when interpreting within-meeting trends.

== E. Meeting representation and labels

The WEKA exporter combines the three summary tables into a single row per meeting. It produces 36 numerical predictors: 12 direct meeting measures, 14 participant-aggregation measures, and 10 temporal measures. The effectiveness class gives 37 ARFF attributes. Meeting identifiers are retained in the CSV export but excluded from ARFF predictors.

#feature-table((1.1fr, 3.4fr, 0.6fr),
  table.header([Feature family], [Contents], [Number]),
  [Meeting summaries], [Speaking and silence ratios; turn rate; mean and median turn duration; back-to-back ratio; mean gap; active-participant count; Gini; entropy; dominant-speaker fraction; micro-turn ratio], [12],
  [Participant aggregates], [Mean and population standard deviation of seven measures: speaking fraction, mean turn duration, two immediate-transition ratios, response latency, self-succession count, and micro-turn ratio], [14],
  [Temporal aggregates], [Population standard deviation and linear slope for five window measures: speaking ratio, Gini, turn rate, active-participant count, and back-to-back ratio], [10],
)

Slopes are calculated against consecutive window indices rather than elapsed seconds. RSSI and raw acceleration are collected and available for inspection, but neither is directly included in the final 36 predictors; acceleration influences them indirectly through speaker labeling. Speaking and silence ratios are complementary, and other summaries may be redundant.

Meeting effectiveness is represented by manually assigned categories of low, medium, and high. During label entry, the workflow displays key interaction statistics to inform the rating decision, alongside qualitative descriptions of effectiveness. Consequently, the labels may depend on the same interaction measures used as predictors; they cannot be assumed to be independent outcome measurements. Independent ratings and a clearly specified rating instrument are needed to separate perceived effectiveness from the interaction measures used to predict it.

= IV. Experimental Evaluation

== A. Dataset composition and evaluation protocol

The primary dataset contains 16 meeting-level records, with five meetings rated low effectiveness, seven medium, and four high. Each record combines the meeting, participant, and temporal summaries described in Section 3 into 36 numerical predictors. A manually assigned effectiveness category provides the target label. Badge observations and within-meeting windows contribute to these summaries; each meeting contributes one classification instance.

Random Forest and a multilayer perceptron were evaluated in WEKA using 10-fold cross-validation on this dataset. Both classifiers address the same three-class prediction task. Results are presented as counts of correctly classified meetings, overall accuracy, Cohen's kappa, probability-error measures, and class-balanced metrics derived from the confusion matrices. The class distribution and small number of meetings are retained explicitly when interpreting these results.

Separate datasets assess the intermediate activity estimates and the earlier classification experiments. The speaker-state comparison contains 5,373 aligned observations from a six-badge recording pair, while the binary activity evaluations operate on individual badge observations. An earlier effectiveness experiment contains ten meeting records. These evaluations are reported separately because their units of analysis differ and their overlap with the primary dataset is not established. The 16 meeting records should not be interpreted as 16 independent participant groups; generalization to new groups requires a group-separated evaluation.

== B. Meeting-classification results

Table 1 summarizes accuracy, Cohen's kappa, mean absolute error (MAE), and root mean squared error (RMSE) for both classifiers. Macro-F1 and balanced accuracy are calculated from the integer confusion matrices. These metrics complement overall accuracy by giving each effectiveness class equal weight.

#figure(
  feature-table((2fr, 1fr, 1fr),
  table.header([Metric], [Random Forest], [Multilayer perceptron]),
  [Correct meetings], [15/16], [13/16],
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
  caption: [Meeting-effectiveness confusion matrices for Random Forest and the multilayer perceptron. Rows are actual labels and columns are predicted labels. Each panel summarizes predictions for 16 meetings.],
)

Always assigning the most common class, medium, would correctly label 7/16 meetings (43.75%) on this full dataset. This is a descriptive class-frequency reference, not a baseline evaluated within the reported cross-validation folds. A paired majority-class baseline should be included in a reproducible rerun.

The multilayer perceptron has lower reported MAE despite lower classification accuracy and higher RMSE. These error summaries describe different properties of the predicted probabilities and do not establish superior calibration. Calibration would require the underlying predictions and an appropriate assessment. Similarly, the two-meeting difference in correct classifications does not establish statistical superiority of one model.

== C. Speaker-state comparison

The manual annotation workflow provides a graphical interface for inspecting sensor traces and assigning activity labels. Automatic labels are compared with manual labels at two levels: binary activity for individual badge observations and a multiclass speaker identity for aligned time bins. The binary task treats active as the positive class. The speaker-state task includes six badge identities and a no-speaker state. These tasks have different denominators and should not be combined into one accuracy estimate.

An initial fixed-window activity heuristic produced 14,003 true positives, 54,898 false negatives, 6,388 false positives, and 140,693 true negatives across 215,982 badge observations. Its accuracy was 71.62%, precision 68.67%, recall 20.32%, and specificity 95.66%. A subsequent adaptive configuration yielded reported binary accuracy of 85.70%, precision of 67.12%, recall of 30.70%, and specificity of 96.93%. The latter result lacks an accompanying binary count matrix. Because a common evaluation sample and matched configurations are not established, the difference is descriptive rather than a controlled estimate of improvement. Both evaluations show much stronger rejection of inactive observations than recovery of active observations.

The separate speaker-identity comparison contains 5,373 aligned observations and 2,724 correct assignments, giving 50.70% accuracy. Table 2 reports class supports and recalls calculated from its integer confusion matrix. Macro-F1 is 0.4116 and balanced accuracy is 0.4106. These values differ from binary activity accuracy because a speaker assignment must identify the correct badge, not merely detect activity.

#figure(
  feature-table((2fr, 1fr, 1fr),
  table.header([Manual state], [Support], [Recall]),
  [Badge 01], [1,431], [39.13%],
  [Badge 04], [304], [33.22%],
  [Badge 05], [866], [41.22%],
  [Badge 07], [197], [18.27%],
  [Badge 09], [259], [62.55%],
  [Badge 10], [357], [19.61%],
  [No speaker], [1,959], [73.40%],
),
  kind: table, supplement: [Table],
  caption: [Speaker-state agreement with manual annotations. Support counts refer to aligned speaker-state observations.],
)

True speaker states are frequently assigned to no-speaker, with corresponding row percentages ranging from 29.73% to 63.45%. Thus, high meeting-level classification accuracy coexists with substantial error in the intermediate speaker representation. This comparison covers a separate six-badge recording pair; it does not establish measurement validity across all 16 classification meetings. Annotation instructions, inter-rater agreement, and correspondence between the validation recordings and classification meetings remain necessary for a complete assessment.

== D. Earlier classification experiments

A separate ten-meeting effectiveness experiment contained three low, three medium, and four high ratings. Under stratified cross-validation, Naive Bayes classified seven meetings correctly (70%; kappa = 0.5455), while J48 classified all ten correctly (100%; kappa = 1.0000). The Naive Bayes errors comprised one low meeting assigned medium and two medium meetings assigned low. The fold count and relationship between this dataset and the 16-meeting dataset are not established. These results document an initial evaluation of the classification workflow; they do not support a direct ranking against the Random Forest and multilayer-perceptron results in Table 1.

An additional supervised activity experiment used a multilayer perceptron with a 66% training split and 15,850 held-out observations. It correctly classified 15,771 observations (99.5016%; kappa = 0.9900). The confusion matrix contains 7,888 correctly classified inactive observations, 7,883 correctly classified active observations, and 79 active observations assigned inactive. This sample-level binary result addresses a different target from meeting effectiveness and uses a learned classifier rather than the heuristic speaker estimator. Without separation by recording or participant, temporally related samples may occur on both sides of a percentage split. Its high accuracy therefore does not establish performance on new recordings or validate the deployed speaker-state pipeline.

== E. Feature interpretation

Micro-turn ratio, back-to-back ratio, and speaking ratio describe distinct aspects of floor sharing and are candidate explanatory features. Their presence in the feature set does not establish their relative predictive importance. An importance analysis or ablation study is needed to determine whether each measure contributes beyond correlated predictors. Speaker-state errors also complicate interpretation because estimated turn counts and participation measures can reflect labeling errors as well as actual interaction.

= V. Discussion and Limitations

== A. Feasibility and construct validity

The implementation demonstrates a practical route from several wearable sensor streams to a fixed-length meeting representation. The reported classification results suggest that this representation contains information associated with the available effectiveness labels. The analysis does not establish what generated that association: actual conversational behavior, the labeling rubric, recurring groups, room conditions, or other correlated factors may contribute.

Speaking balance is also not equivalent to meeting quality. A briefing can appropriately concentrate speaking time in one person; a productive planning discussion may contain silence; an attentive participant may say little. The intended use should therefore remain contextual analysis and participant reflection until independent outcome measures establish a stronger interpretation. Cognitive engagement, fairness, and objective productivity are not validated targets in this study.

== B. Sample size and evaluation independence

The dataset has 16 meetings and 36 predictors. Each changed prediction alters accuracy by 6.25 percentage points, making performance estimates sensitive to individual meetings. Ten-fold validation necessarily uses very small test folds, and the class counts do not permit every fold to contain all three classes. Neither the reported accuracy nor kappa resolves uncertainty from limited data or repeated participants.

If the same team appears in both training and test folds, the evaluation may capture recurring team characteristics rather than generalization to an unfamiliar group. A future study should define the intended population and split by team or participant group where feasible. Meeting-level grouping must also be retained if window-level samples are used. Preprocessing, feature selection, and tuning should be learned within training folds, with a separate final evaluation wherever sufficient data are available.

== C. Reliability of intermediate measurements

The speaker-state comparison makes intermediate validation a priority. False silence can change speaking ratios and fragment turns; speaker swaps can distort participation balance. Smoothing can suppress brief acknowledgments or merge distinct events. Missing timestamps can also create apparent continuity because the turn extractor groups consecutive observed speaker states without explicitly breaking at unobserved time bins.

Several feature conventions affect interpretation of the interaction measures. Group-level equality measures omit non-speaking attendees. The back-to-back measure can count a meeting's first turn as having zero preceding gap. The self-succession implementation checks the immediately preceding state even when a silence interval intervenes, so its intended interpretation is not reliably represented. These conventions require targeted validation and sensitivity analysis before the resulting features are treated as behavioral measurements.

A useful next evaluation would separately measure speech presence, speaker identity, and downstream feature error against independently annotated intervals. Sound-only and sound-plus-motion ablations would test the value of acceleration. Threshold, voting, and smoothing sensitivity analyses would establish whether classification persists under reasonable labeling changes. Simultaneous speech should be annotated explicitly rather than forced into a single-speaker state.

== D. Data minimization and participant privacy

The badge design reduces retained speech content by transmitting scalar summaries rather than a microphone waveform. The microphone nevertheless processes audio samples transiently to compute those summaries. Moreover, the collector can store participant names, device identifiers, timestamps, and behavioral histories. Avoiding intelligible audio retention is therefore a data-minimization property, not a guarantee of anonymity or complete privacy.

Participant privacy requires informed participation, defined retention periods, controlled access, and separation of identities from released behavioral data. These safeguards are particularly relevant in classrooms and workplaces, where participation may be influenced by existing power relationships. Data minimization at the sensor level does not replace these study-governance requirements.

== E. Toward prospective feedback

The system supports live sensing and visualization, but effectiveness prediction currently relies on recorded-data processing and whole-meeting summaries. A prospective feedback system would need a causal speaker estimator, explicitly defined trailing-window features, a measured end-to-end delay, and validation on partial meetings. The Rev2 sensor viewer provides a possible instrumentation platform, not evidence that these prediction requirements have been met.

A larger study could evaluate whether descriptive feedback changes participation and whether participants find it useful. Such an intervention should be assessed separately from classification performance. Battery life, packet delivery, cross-device calibration, and performance as the number of concurrent badges increases also require measurement before claiming deployment scalability.

= VI. Conclusion

This work presents a BLE smart badge pipeline that converts sound-level and motion measurements into estimated speaker activity and meeting-level interaction features. In a 16-meeting feasibility evaluation, Random Forest achieves 93.75% classification accuracy and a multilayer perceptron achieves 81.25% under 10-fold cross-validation. These results indicate that the feature representation can distinguish effectiveness ratings within the study sample. Interpretation remains constrained by the small dataset, uncertainty about rating independence, and substantial speaker-state errors. Further evaluation should use independent effectiveness ratings, validated intermediate measurements, and test groups separated from training groups to establish usefulness across a wider range of meetings.

#bibliography("references.bib", style: "ieee", title: [References])
