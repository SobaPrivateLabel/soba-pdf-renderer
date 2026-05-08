# IQ Super: PDF Template Renderer

Takes a `report_bundle.json` produced by the orchestrator and renders it to A4 PDF using Jinja2 + WeasyPrint.

This is the second half of the IQ Super pipeline. The orchestrator (in the separate `orchestrator/` folder) produces the JSON. This folder turns the JSON into the deliverable PDF the subscriber receives.

## Status

Working draft, May 5 evening. First pass of the template based on the designer's PDF for PandaRoll. Renders all eleven sections (cover, contents, exec summary, position score, costing, competitive landscape, language, visual identity, gaps, key issues, recommendations + flag, what to do next, contact) with proper conditional rendering for score-5 reports.

Known gaps versus the designer's PDF: no font yet (Manrope is loaded from Google Fonts at render time as a Filson Pro stand-in; subscribers will see Manrope until you license Filson). Spacing, type sizes, and exact pill positions will need a polish pass against side-by-side comparison with the designer's PDF.

## One-time setup

1. Open Terminal in this folder.
2. Install Python dependencies:
   ```
   pip3 install jinja2 weasyprint
   ```
3. Install WeasyPrint's system requirements (macOS):
   ```
   brew install pango
   ```
   On Linux the equivalent is `libpango-1.0-0 libpangoft2-1.0-0`. Windows is harder, see the official docs.
4. Test the render against the included sample bundle:
   ```
   python3 render_pdf.py test_bundle.json
   ```
   The first run downloads the Manrope font from Google Fonts (one-time, ~200ms). Output goes to `output/pandaroll_<timestamp>.pdf`.

## Running it

```
python3 render_pdf.py path/to/report_bundle.json
```

Default output is `./output/<company>_<timestamp>.pdf`. Override with `--out`:

```
python3 render_pdf.py bundle.json --out reports/may_run.pdf
```

## File layout

```
template/
├── README.md                     This file
├── render_pdf.py                 The render script
├── test_bundle.json              Synthetic bundle modelled on PandaRoll PDF
├── templates/
│   ├── report.html               Single Jinja2 template, all sections
│   └── main.css                  All styles in one file
├── assets/
│   ├── border.png                Lime squiggle border (full-page background)
│   ├── pug.png                   Ramen Rascal (contents page)
│   ├── cat.png                   Chairman Claw (recommendations page)
│   ├── bowl.png                  Empty bowl (position score page)
│   └── logo.png                  Soba: Private Label (contact page)
└── output/                       PDFs land here
```

## How to iterate on the design

1. **Wording, ordering, content shape.** Edit `templates/report.html`. The structure is one `<section class="page">` per page.
2. **Colours, fonts, spacing.** Edit `templates/main.css`. Design tokens are in the `:root` block at the top.
3. **Asset sizes.** Tweak the relevant rule in `main.css` (e.g. `.contents-illustration img { width: 78mm }`).
4. **Pin Manrope to disk.** Right now Manrope loads from Google Fonts at render time. If you want offline rendering or you license Filson, drop the font files into `fonts/` and update the `@import` line in `main.css` to `@font-face` declarations.

## Conditional rendering

The template knows about score 5. At score 5:
- The "What this position is costing you" section is skipped (the `if sections.costing` block returns null).
- The "What to do next" section is skipped.
- The "Key positioning issues" header swaps to "Key positioning strengths" (driven by `sections.key_issues_or_strengths.section_mode`).
- The contents page omits the skipped sections so the numbering stays sequential.

The current `test_bundle.json` is a score 3.5 example. To test score 5 rendering, set `sections.costing` and `sections.what_to_do_next` to `null` in the bundle and change `section_mode` to `"strengths"` plus update the priority labels (DEFINING / STRONG / NOTABLE).

## Gotchas

- **Don't access `.values` on a dict in Jinja.** It collides with the dict's `values()` method. The template uses `row['values']` instead. If you add a field called `values` (e.g. for tables), use bracket access.
- **WeasyPrint paths are tricky.** Asset URLs in the HTML are `../assets/something.png` because they're relative to `templates/`. The render script sets the `base_url` argument so this works. If you reorganise the folders, update both the HTML and `render_pdf.py`.
- **First render is slower.** Subsequent renders cache fonts and the border PNG; expect 2-5 seconds per report.

## What's next (not done in this draft)

- Spacing pass against the designer's PDF (paragraph margins, pill positioning, table row heights).
- Filson Pro substitution (when licensed).
- Score 5 test bundle for QA.
- Length-overflow handling: long sections currently can spill onto a second page in ways that look odd. WeasyPrint handles page breaks automatically, but the lime-bordered pages don't repeat their decorative elements on overflow pages. Worth tightening before launch.
- Wire `render_pdf.py` into the orchestrator so a single command runs the eight prompts AND produces the PDF in one go.
