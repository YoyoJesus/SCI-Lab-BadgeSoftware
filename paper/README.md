# Smart badge manuscript draft

The main typesetting source is **`manuscript.typ`**. It uses a conventional two-column conference layout, 10-point Times New Roman, a full-width title, numbered equations in ASCII notation, citations from `references.bib`, and SVG figures. All manuscript source text and rendered PDF text use ASCII characters. Smart punctuation is disabled. No third-party Typst packages or network access are needed to compile it once Typst and the fonts are available.

```bash
python paper/build_paper.py
```

Run this from the repository root. The builder uses an installed Typst or the verified Typst 0.15.1 binary cached locally in the ignored `paper/.tools/` folder. Times New Roman's regular, bold, italic, and bold-italic fonts are cached locally in the ignored `paper/.fonts/` folder from Microsoft's Core Fonts distribution (`times32.exe`). These fonts and the compiler are not added to version control. On another machine, install Typst and Times New Roman, or provide those fonts with `--font-path`. The direct command is `typst compile --font-path paper/.fonts paper/manuscript.typ paper/manuscript.pdf`.

Files:

- `manuscript.typ` :  editable Typst paper.
- `manuscript.pdf` :  PDF compiled from Typst.
- `references.bib` :  source bibliography.
- `figures/` :  portable SVG, PDF, and PNG figures.
- `author_notes.md` :  evidence ledger, conflicting poster versions, and missing study details.
- `manuscript.md` :  companion Markdown text.
- `derived_metrics.json` :  arithmetic reconstructed from the supplied poster's matrices.
- `supplementary_evaluations.json` :  presentation experiment counts and derived metrics.

The manuscript is a feasibility-study manuscript. Author queries and submission requirements are in `author_notes.md`; they are excluded from the typeset paper. Model performance was transcribed from the linked poster and supplied presentations; no classifiers were retrained.

## Optional export tools

`python paper/export_typst.py` regenerates the Typst source from Markdown. **This overwrites direct edits to `manuscript.typ`.** It is not necessary for normal Typst editing or compilation.

`python paper/build_figures.py` regenerates the vector figures and derived metrics. PNG/PDF figure exports require `rsvg-convert`; the manuscript itself uses the SVGs. This script does not modify the application or train any models.
