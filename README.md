# IEEE Access Weed Detection Manuscript

LaTeX source for the IEEE Access manuscript "Impact of Multispectral Imaging and Vegetation Indices on Neural Network Performance for Weed Detection Using Agricultural UAVs".

## Build

Use `main.tex` as the main document. It is a small entry point that inputs the manuscript source in `access_revised_v2.tex`.

Recommended settings:

- Compiler: pdfLaTeX
- Bibliography: BibTeX
- Main document: `main.tex`

Local build:

```sh
latexmk -pdf main.tex
```

Overleaf should use the same entry point and can read the included `latexmkrc`.

## Diff PDF

Use the scripted latexdiff workflow when preparing a review-response diff PDF. The script accepts explicit original and revised TeX files so the caller can choose the comparison pair.

```sh
python3 scripts/build_diff_pdf.py \
  --old ../IEEE_Access_before_review/access_revised_v2.tex \
  --new access_revised_v2.tex \
  --output-name access_revised_v2_diff_before_review
```

Useful options:

- `--tex-only`: generate only the diff TeX file.
- `--clean-aux`: remove generated LaTeX auxiliary files after a successful build.
- `--strict-log`: fail if the final LaTeX log has unresolved references or citations.
- `--latexdiff-option` and `--latexmk-option`: pass extra options through to the underlying tools.

## Project Structure

- `main.tex`: Overleaf/GitHub entry point.
- `access_revised_v2.tex`: manuscript source.
- `IEEEexample.bib` and `IEEEabrv.bib`: bibliography files.
- `ieeeaccess.cls`, `IEEEtran.cls`, `logo.png`, `notaglinelogo.png`, and `bullet.png`: IEEE Access template assets needed for compilation.
- `images/`: figures and author photos used by the manuscript.
- `scripts/build_diff_pdf.py`: parameterized latexdiff PDF builder for review-response diffs.

## Version Control

The `.gitignore` excludes LaTeX build products such as `.aux`, `.bbl`, `.log`, and generated manuscript PDFs. Source files, bibliography files, class files, template assets, and figure files should be tracked.
