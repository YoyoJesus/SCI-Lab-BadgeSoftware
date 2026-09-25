# Smart badge manuscript draft

The main typesetting source is **`manuscript.typ`**. It uses a conventional two-column conference layout, 10-point Times New Roman, a full-width title, numbered equations in ASCII notation, citations from `references.bib`, and SVG figures. All manuscript source text and rendered PDF text use ASCII characters. Smart punctuation is disabled. No third-party Typst packages or network access are needed to compile it once Typst and the fonts are available.

```bash
python paper/build_paper.py
```

Run this from the repository root. The builder uses Typst on PATH, falling back to `paper/.tools/typst` if that file exists. The current PDF was built with installed Typst 0.14.2 and system Times New Roman fonts. Optional local compiler/font caches in `paper/.tools/` and `paper/.fonts/` are ignored and are not distributed with the repository. On another machine, install Typst and Times New Roman, or supply fonts in `paper/.fonts/`. The direct command is `typst compile --font-path paper/.fonts paper/manuscript.typ paper/manuscript.pdf`.

Files:

- `manuscript.typ` :  editable Typst paper.
- `manuscript.pdf` :  PDF compiled from Typst.
- `manuscript.docx` :  Word version exported from `manuscript.md`.
- `references.bib` :  source bibliography.
- `figures/` :  portable SVG, PDF, and PNG figures.
- `author_notes.md` :  evidence ledger, conflicting poster versions, and missing study details.
- `manuscript.md` :  companion Markdown text.
- `derived_metrics.json` :  arithmetic reconstructed from the supplied poster's matrices.
- `supplementary_evaluations.json` :  presentation experiment counts and derived metrics.

The manuscript is a venue-neutral feasibility study. Recovered local inputs reproduce all saved feature tables and exported predictors. Recovered WEKA option strings reproduce both reported classifier summaries under an explicit 10-fold seed-1 reconstruction. New baselines and session/context sensitivity checks are identified separately. Author-confirmed label provenance, incomplete speaker annotation, consent, absence of ethics review, funding, and contributions are documented in `author_notes.md` and `author_confirmations.json`.

## Optional export tools

`python paper/export_typst.py` regenerates the Typst source from Markdown. **This overwrites direct edits to `manuscript.typ`.** It is not necessary for normal Typst editing or compilation.

`python paper/export_docx.py` writes `manuscript.docx` from `manuscript.md` with the same two-column Times New Roman layout, for co-authors or venues that need Word. It requires `python-docx` (`pip install python-docx`) and does not modify the Markdown or Typst sources. Equations remain ASCII text, and figures use the PNG exports.

`python paper/build_figures.py` regenerates the vector figures and derived metrics. PNG/PDF figure exports require `rsvg-convert`; the manuscript itself uses the SVGs. This script does not modify the application or train any models.

## Audit recovered local data

`python paper/audit_local_data.py` checks the CSV/ARFF, reconstructs all 36 exported features for each of 16 records from the saved tables, and reconstructs the original speaker comparison from the manual and automatic files. It requires NumPy and pandas; it does not train classifiers or alter input data. Use `--data-root PATH` if the ignored data folders live in another checkout. The resulting `local_data_audit.json` records source hashes, sample composition, and annotation/alignment limitations. It deliberately omits participant names. The original feature audit remains a record of historical counts; it does not treat unannotated time as verified silence. The additional analyses below address annotation validity and classifier reproduction.

## Additional reproducibility checks

```text
python paper/audit_feature_sources.py
python paper/validate_annotations.py
python paper/evaluate_weka.py
python paper/test_validation.py
```

The source audit recomputes features in memory and writes `feature_source_audit.json`. The annotation validator preserves unknown labels and writes `annotation_validation.json`. The WEKA runner writes `weka_evaluation.json`, including settings, folds, predictions, probabilities, source hashes, and runtime versions; it defaults to `C:/Program Files/Weka-3-8-6` and accepts `--weka-home`, `--java`, `--historical-log`, and `--data-root`. Its temporary split files and command output are ignored under `paper/.tools/`. None of these scripts overwrites the original sensor data or feature tables. The historical fold seed is not logged; seed 1 is a reconstruction assumption that matches the reported summaries. These checks do not establish independent effectiveness or speaker-accuracy validation.
