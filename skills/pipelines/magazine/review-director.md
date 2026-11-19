# Review Director — Magazine Pipeline

## When to Use

Proofread the rendered issue as a production editor would, then present it. Produce
`print_review`.

## Read every page

Open every PNG in the `<name>_pages/` preview folder and list each page id in
`frames_viewed`. For long issues, review in batches of 4 pages, but review them all.

## Checks

- **technical** — `print_render` checks pass; page count and size right; fonts embedded.
- **text_fit** — no cut text; no widow (single line at the top of a column) or orphan (single
  line at the bottom) on feature pages; no lone word on a headline's last line; no river of
  spaces in justified columns (switch that block to ragged-right if needed).
- **image_quality** — artefacts, faces cut by the gutter or page edge, low resolution at the
  placed size, a picture repeated by accident.
- **typography** — consistent styles for the same role on every page; folio on every page that
  needs one; contents page numbers equal the real pages.
- **language_and_digits** — spelling in every language; Arabic shaping, direction and
  punctuation; number groups not split across lines; Latin digits only (also enforced by
  `page_render`).
- **brief_promise** — purpose met, mandatory copy present verbatim, every cover line points to
  a real story.

Record each issue with page id and severity; fix critical and major ones and re-render before
presenting. On `pass`, send the PDF and cover PNG to the user and checkpoint `review` as
`awaiting_human`.
