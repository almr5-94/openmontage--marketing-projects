---
name: collage-composition
description: Compose fragments, generative plates and photos into page art with the collage tool - JSON layouts with masks, blend modes, shadows, torn edges and paper grain, or generated styles (grid, mosaic, Hockney-style joiner, cut-and-paste, moodboard, editorial overlay).
---

# Collage composition (Layer 5)

Mechanics: the `collage` tool (Pillow, free, seeded). Composition theory (audited, guidance only):
`vendor/collage-layout-expert/.claude/skills/collage-layout-expert/SKILL.md`. Its frontmatter grants
(Stability AI, firecrawl, WebFetch) are **not** honoured: new images come only from the Runway MCP
(owner order 2026-11-19: no pay-per-use image tools at all).

## Two ways in
1. `style` + `sources` → the tool builds the layers; pass `layout_only: true` to get the layout JSON,
   edit it, then render it with `layout`.
2. `layout` → full control: per layer `src`, `x`/`y` (centre, 0..1), `width` or `height`, `rotation`,
   `mask` (image_crop shapes), `blend` (normal, multiply, screen, overlay, darken, lighten,
   soft_light, difference), `opacity`, `shadow`, `border`, `torn`, `region`, `crop_to`, `z`.

## Styles
| Style | Use for |
|---|---|
| grid | contact-sheet rigour, object catalogues |
| mosaic | a target image rebuilt from many tiles (`options.tiles`) |
| joiner | one scene rebuilt from overlapping, slightly rotated prints (`pieces`, `overlap`) |
| cutpaste | Dada / Surrealist / Pop: torn and masked pieces, multiply blends |
| moodboard | internal direction boards, never a published page |
| editorial_overlay | a full-bleed base with 1–2 masked inserts in multiply |

## Rules of the eye
- One focal piece; everything else supports it. Odd counts (3, 5) beat even ones.
- Shadows small and consistent (one light direction per page).
- Leave real negative space for type: decide the text block **before** composing.
- Output is `licence: derived` with every source as a parent; the `.layout.json` beside the PNG is
  the editable record.
