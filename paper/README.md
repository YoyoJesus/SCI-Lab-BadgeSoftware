# Smart badge manuscript draft

The main typesetting source is **`manuscript.typ`**. It uses a conventional two-column conference layout, 10-point Times New Roman, a full-width title, numbered equations in ASCII notation, citations from `references.bib`, and SVG figures. All manuscript source text and rendered PDF text use ASCII characters. Smart punctuation is disabled. No third-party Typst packages or network access are needed to compile it once Typst and the fonts are available.

```bash
python paper/build_paper.py
```

Run this from the repository root. The builder uses Typst on PATH, falling back to `paper/.tools/typst` if that file exists. The current PDF was built with installed Typst 0.14.2 and system Times New Roman fonts. Optional local compiler/font caches in `paper/.tools/` and `paper/.fonts/` are ignored and are not distributed with the repository. On another machine, install Typst and Times New Roman, or supply fonts in `paper/.fonts/`. The direct command is `typst compile --font-path paper/.fonts paper/manuscript.typ paper/manuscript.pdf`.

Files:

- `manuscript.typ` :  editable Typst paper.
- `manuscript.pdf` :  PDF compiled from Typst.
- `references.bib` :  source bibliography.
- `figures/` :  portable SVG, PDF, and PNG figures.
- `author_notes.md` :  evidence ledger, conflicting poster versions, and missing study details.
- `manuscript.md` :  companion Markdown text.
- `derived_metrics.json` :  arithmetic reconstructed from the supplied poster's matrices.
- `supplementary_evaluations.json` :  presentation experiment counts and derived metrics.

The manuscript is a feasibility-study manuscript. Author queries and submission requirements are in `author_notes.md`; they are excluded from the typeset paper. Model performance was transcribed from the linked poster and supplied presentations; no classifiers were retrained. Recovered local data now verify the exported inputs and the saved speaker-comparison counts, with provenance and limitations recorded in `local_data_audit.json` and `author_notes.md`.

## Optional export tools

`python paper/export_typst.py` regenerates the Typst source from Markdown. **This overwrites direct edits to `manuscript.typ`.** It is not necessary for normal Typst editing or compilation.

`python paper/build_figures.py` regenerates the vector figures and derived metrics. PNG/PDF figure exports require `rsvg-convert`; the manuscript itself uses the SVGs. This script does not modify the application or train any models.

## Audit recovered local data

`python paper/audit_local_data.py` checks the CSV/ARFF, reconstructs all 36 exported features for each of 16 records from the saved tables, and reconstructs the original speaker comparison from the manual and automatic files. It requires NumPy and pandas; it does not train classifiers or alter input data. Use `--data-root PATH` if the ignored data folders live in another checkout. The resulting `local_data_audit.json` records source hashes, sample composition, and annotation/alignment limitations. It deliberately omits participant names. The original classifier settings and folds remain unavailable, so historical classification scores are not described as reproduced.
