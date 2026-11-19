# Concept Director — Magazine Pipeline

## When to Use

After the brief. Produce `studio_proposal` + `decision_log`; get approval. No paid call before
`approval.status` is `approved`.

## Design directions (two or three)

Each direction specifies:

- **Typography** — display face, text face, Arabic faces if any (locally installed: FreeSerif,
  DejaVu Sans, Noto Naskh Arabic, Noto Kufi Arabic; any other font must be added as a file in
  `assets/fonts/` with its licence noted).
- **Grid** — columns per page (2 for brochures, 3 for magazines), margins, gutter.
- **Image strategy** — photo-real generated, illustrated, stock photography, the user's photos,
  or typographic; the cover treatment specifically.
- **Palette** — 3–5 colours as hex.

Render a two-page mock of each direction (cover + one feature page) from
`print-studio/templates/magazine/issue.html` with grey picture boxes — `page_render` is free —
and show the PNGs. Directions are judged on pages, not on adjectives.

## Tool election (Rule Zero)

Present the image-source menu from `registry.capability_catalog()["image_generation"]` (only
`available` tools), free/local and stock first, then paid with unit price and trade-off;
include "user's photos" and "no pictures". Ask separately about `upscale` if print resolution
requires it, and `diagram_gen` if the issue has charts or diagrams. Log every election in
`decision_log` with all options considered.

## Cost

Line items per image (cover counted separately with 2 retries), upscales, and `page_render` at
0. Include the time estimate.
