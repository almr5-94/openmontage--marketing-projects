---
name: generative-art
description: Seeded generative plates for print (flow fields, engraving, arches, voronoi, stipple, botanical L-systems, truchet, or a p5 sketch) with ink, paper and metal finishes, at 300 dpi PNG plus SVG, via the generative_art tool. Use for drawing series, textures, dividers and abstract art pages.
---

# Generative art (Layer 4)

`generative_art` is free, local and **seeded**: the same inputs and seed give the same SVG, byte for
byte. Record the seed — it is the plate's identity. Upstream guidance (audited):
`vendor/genart-skill/skills/genart/SKILL.md`, `vendor/genart-ops/skills/genart-ops/SKILL.md`.

## Inputs
- `algorithm`: flow_field, engraving (tone from `source_image`, cross-hatched), arches, voronoi,
  stipple (tone from `source_image`), botanical, truchet, p5 (`sketch_path`, seeded via tokenData).
- Size: `width_mm` + `height_mm` + `dpi` (300) — or `width_px` + `height_px`.
- Material: `paper` uncoated_offwhite | cream | coated_silk | newsprint | black | none;
  `finish` ink | brass | gold | silver | copper; `ink`, `ink_spread`, `palette`, `params`.
- Output: SVG + PNG in `assets/generative/`, provenance `generated-in-session` with the seed.

## Making it look made, not generated
- Pair a **museum source** with a generative treatment: an engraving or stipple of a real object
  reads as a print; a bare flow field reads as a screensaver.
- Limit the palette to the house palette (1 ink + paper is often best). Metal finishes only on
  one element per page.
- Drawing series: fix algorithm, palette, paper and params; vary only the seed and the source
  object. Produce a **style-lock sheet** (montage of all plates) before laying out.
- Never present a plate as a diagram or chart (AP-3) — no axes, arrows, labels inside the art.
