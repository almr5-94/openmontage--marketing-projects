# maison-drawing-series

A named, numbered drawing series for a house ("Drawing <theme> No. <n>") with a fixed hand - medium look, line weight, palette, paper - locked by a style-lock sheet so plate No. 1 and No. 30 look like the same artist. Free seeded vector drawing first (generative_art), then the repo's hand-drawn style systems, then elected Runway generation; individual print plates, a series index page and an archive page by year, month and series.

Manifest: `pipeline_defs/maison-drawing-series.yaml` · stage guides: `skills/pipelines/maison-drawing-series/`

| # | Stage | Produces | Tools | Human approves | What happens |
|---|---|---|---|---|---|
| 1 | `series_brief` | print_brief, decision_log | - | yes | Series name, theme, numbering, year; the hand: medium look, line weight, palette, paper |
| 2 | `hand` | studio_proposal, decision_log | generative_art, image_crop | yes | 2-3 hand options rendered as test plates (seeds logged); engine route elected: generative_art, scripts/style_refs families, or Runway MCP (paid) |
| 3 | `assets` | asset_manifest, decision_log | generative_art, image_crop, met_art, cleveland_art, rijks_art | yes | Each plate in the fixed hand at print resolution; face gate on every figure; seeds logged |
| 4 | `style_lock` | quality_gate | image_crop | yes | Style-lock sheet (montage of every plate beside plate No. 1); outliers redone |
| 5 | `layout` | layout_plan, print_render | editorial_layout, page_render | no | Plate pages on a paper-light ground, a series index, an archive page grouped by year, month, series |
| 6 | `critique` | maison_critique, quality_gate | editorial_layout, page_render | yes | maison critique (Claude + local models): every rubric criterion 4 or above, with evidence anti-AI-tells gate, face gate, provenance and brand_lint all pass (blocking) |
| 7 | `publish` | publish_log | editorial_layout | yes | Plates as print PNGs and a series PDF handed over |

Every stage writes its choices to `decision_log.json`. The critique stage is blocking: see `maison/critique/rubric.md`.
