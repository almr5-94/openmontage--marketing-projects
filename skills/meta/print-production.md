# Print Production — shared rules for image-studio and magazine

Read this once at the start of any `image-studio` or `magazine` run. Every stage director in
those two pipelines assumes it.

## What the print studio is

OpenMontage started as a video system. The print studio reuses everything that is not
video-specific — the pipeline/checkpoint machinery, the decision log, the Backlot board, the
19 image-generation tools, stock sources and enhancement tools — and adds one engine:

| Piece | What it does |
|-------|--------------|
| `page_render` (`tools/graphics/page_render.py`) | HTML → PNG/JPG still at an exact pixel size, or HTML → print PDF + one PNG preview per page. Free, local (headless Chromium). Runs the proof checks below. |
| `print-studio/css/print-base.css` | Page box, 12-column grid, columns, editorial type (kicker, headline, dek, byline, drop cap, pull quote, caption, folio), cover parts, contents rows, RTL rules, `.still` frame. |
| `print-studio/templates/magazine/issue.html` | A 6-page starter issue: cover, contents, feature opener, feature body, Arabic page, back-cover ad. |
| `print-studio/templates/stills/social-post.html` | A still that reflows to any aspect ratio (vw/vh units), so one file renders every format. |

Pictures are **made** by image tools; pages are **set** in HTML. Never ask an image model to
render body text, prices, dates or Arabic copy into a picture — it misspells and mis-shapes
them. Text lives in HTML, on top of or beside the picture.

## Rule Zero still applies — elect tools out loud

The repo's tool-election rule (`AGENT_GUIDE.md` → Decision Communication Contract) covers
images exactly as it covers video:

- Before any paid image call, present a menu of the **real** registry tools that can do the
  job (`registry.capability_catalog()["image_generation"]` plus stock: `pexels_image`,
  `pixabay_image`, plus "the user's own photos" and "typographic only — no pictures"). Free
  and local options first. Name exact tool names, provider, rough unit price, and trade-off.
- Log the election in `decision_log` (`category: "provider_selection"`, `subject: "Image
  source"`) with **every** offered option in `options_considered`.
- `page_render` is free and local; it still gets one line in the tool plan, but needs no menu.
- A failed tool is a new election, never a silent fallback.

## Project layout

`init_project('<id>', title='<Title>', pipeline_type='image-studio' | 'magazine')` creates the
standard workspace. The print studio adds two folders:

```
projects/<id>/
├── artifacts/            print_brief, studio_proposal, editorial_copy, layout_plan, asset_manifest,
│                         print_render, print_review, publish_log, decision_log
├── assets/images/        generated / stock / user pictures (PNG/JPG)
│   └── components/       rejected or superseded takes — NEVER deleted (owner rule)
├── assets/fonts/         optional .woff2/.ttf files declared with @font-face
├── layout/               the HTML you author + a copy of print-base.css
│   ├── print-base.css
│   ├── issue.html        (magazine)  or  f01.html, f02.html ... (image-studio)
└── renders/              PDFs, PNG/JPG deliverables, <name>_pages/ previews
```

Copy `print-studio/css/print-base.css` and the whole `print-studio/fonts/` folder into `layout/`
and link both relatively (`<link rel="stylesheet" href="fonts/fonts.css">` then
`<link rel="stylesheet" href="print-base.css">`). Only the curated OFL families in
`print-studio/fonts/FONTS.yaml` may set visible text; Noto, DejaVu, Arial, Roboto, Inter and other
fallback faces are banned (AP-4) and the anti-AI-tells gate fails any PDF that embeds them. Images are referenced relatively
(`../assets/images/p01-cover.png`). Never link outside the project folder: a project must
render the same after the repo moves.

## Calling page_render

```python
from tools.graphics.page_render import PageRender
r = PageRender().execute({
    "html_path": "projects/<id>/layout/issue.html",
    "mode": "pdf",                       # or "still"
    "output_path": "projects/<id>/renders/issue.pdf",
    "size_preset": "magazine_standard",  # checked against every PDF page
    "expected_pages": 16,
    "preview_dpi": 110,                  # page PNGs for review; 0 = none
})
r.data["checks"]   # {"pass": bool, "problems": [...], "overflow": [...], ...}
```

Still mode: `"mode": "still", "size_preset": "instagram_post"` (or `width_px`/`height_px`),
`.png` or `.jpg` output. It renders at 2× and downsamples to the exact size, so type is sharp.

Size presets: `instagram_post` 1080×1350, `instagram_square` 1080×1080, `instagram_story`
1080×1920, `facebook_post` 1200×630, `linkedin_post` 1200×627, `x_post` 1600×900,
`youtube_thumbnail` 1280×720, `presentation_16_9` 1920×1080; print trims `a4`, `a5`, `a3`,
`us_letter`, `magazine_standard` 230×300 mm, `magazine_us` 203.2×276.2 mm, `poster_18x24`,
`poster_a2`.

## The proof checks (what `checks.pass` means)

| Check | Fails when |
|-------|-----------|
| overflow | a box with `overflow: hidden/clip` (every `.frame`, every `.page`) holds more content than it shows — i.e. text was cut off |
| missing_resources | an `<img>`, CSS `url()` or stylesheet the HTML points at does not exist |
| non_latin_digits | the visible text contains Arabic-Indic (٠-٩) or Persian (۰-۹) digits — owner rule: Latin digits everywhere, Arabic sentences included |
| pages / page size | PDF page count or size differs from `expected_pages` / the size preset |
| fonts_not_embedded | a font in the PDF is referenced but not embedded (a print shop will substitute it) |

`checks.pass == false` is a red gate: fix the HTML or the copy and render again. Do not
present a failing render to the user except to ask how to resolve a genuine conflict (e.g.
copy the user wrote verbatim does not fit the slot they chose).

The checks cannot see everything. **Always open the PNG previews and look** — at minimum every
cover, every opener and every page with an image. Typical misses: a face cut by the fold, a
headline over a busy part of the picture, a widow line at the top of a column, a caption under
the wrong picture.

## Typesetting rules

- **Text in boxes.** Wrap every text block that must not spill in a `.frame` (or give it
  `overflow: hidden` and a fixed height) so overflow is detected rather than hidden.
- **Fixed-height columns** use `.cols-2`/`.cols-3` plus `.cols-fill`; free-height columns
  balance by default.
- **Arabic.** Set `dir="rtl" lang="ar"` on the page or block. Fonts: `--font-arabic-text`
  (IBM Plex Sans Arabic) for body, `--font-arabic-display` (Amiri, calligraphic Naskh) for headlines. No
  letter-spacing on Arabic, no uppercase transforms, no hyphenation. Write digits as Latin
  `0-9`. Keep number groups on one line with `<span class="nowrap">230 × 300</span>` —
  do not force them left-to-right; the browser's bidi order is the natural reading order.
  Isolate Latin words, URLs and brand names with `<span class="ltr">`.
- **Never format numbers with an `ar` locale** in any helper script (`toLocaleString('ar')`
  emits Arabic-Indic digits). Use `ar-KW-u-nu-latn` if a locale is needed at all.
- **Print images at the right resolution.** Slot width in mm ÷ 25.4 × 300 = minimum pixels
  for print; × 150 for a screen PDF. A 230 mm full-bleed cover needs ≈ 2716 px wide for
  print. Upscale (`upscale`) when a generated image is smaller, and log it.
- **Bleed.** For a print-shop PDF, add 3 mm bleed: `@page { size: 236mm 306mm }` and extend
  full-bleed pictures 3 mm past the trim. Screen PDFs need no bleed. Record which one in
  `print_brief.delivery`.

## Generated media is never deleted

A rejected cover, a superseded take, an image the user disliked: move it into
`assets/images/components/` with a versioned name (`p01-cover.v2.png`). Never overwrite a take
with its retake, never `rm` an image folder.

## Hand-off to the user

A deliverable is handed over as a file (the session's file-send tool), never only as a path.
For magazines send the PDF and the cover PNG; for image sets send every final image.
