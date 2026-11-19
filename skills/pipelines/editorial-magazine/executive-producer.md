# Executive Producer — Editorial Magazine Pipeline

## When to Use

You run `editorial-magazine`: an art-led magazine made from **real art**, not from code-drawn
shapes. Read `skills/meta/print-production.md` and `qa/anti-patterns/CATALOGUE.md` first. The
failed "Sard Private Editions" issue (0 raster images, fallback fonts, diagrams) is what this
pipeline exists to never produce again.

## The run

```
feeling_brief -> art_system -> assets -> fragments -> matching_parts* -> geometric_layers
  -> fashion_direction* -> collage -> layout -> review_gate -> publish -> motion*      (* optional)
```

| Stage | Director | Artifact | Human gate |
|---|---|---|---|
| feeling_brief | feeling-brief-director | `print_brief` | yes |
| art_system | art-system-director | `studio_proposal`, `decision_log` | yes — palette, motif, type, image route |
| assets | source-art-director | `asset_manifest` | yes — the sources |
| fragments | fragment-director | `asset_manifest` | no — contact sheet reviewed |
| matching_parts | matching-parts-director | `asset_manifest`, `decision_log` | yes — every paid call |
| geometric_layers | geometric-layers-director | `asset_manifest` | no |
| fashion_direction | fashion-director | `shot_list` | yes |
| collage | collage-director | `asset_manifest` | yes — page art |
| layout | layout-director | `layout_plan`, `print_render` | no — checks must pass |
| review_gate | review-gate-director | `quality_gate`, `print_review` | yes — the proof |
| publish | export-director | `publish_log` | yes |
| motion | motion-director | `decision_log` | yes |

Start: `om new <id> --pipeline editorial-magazine` (or the MCP `init_project`), then
`python -m backlot open <id>`. Every stage writes under `projects/<id>/` and appends to
`decision_log.json` through `lib/decision_log.record` (the `actor` says who drove it).

## Rule Zero, free first

Free routes come first in every menu: museum art (`met_art`, `cleveland_art`, `rijks_art`,
`aic_art`), `pexels_image`, `pixabay_image`, `image_crop`, `generative_art`, `collage`,
`editorial_layout`. The **only** paid image route is the Runway MCP (owner order 2026-11-19: no
pay-per-call image tools at all), and each call needs a `paid_election` decision with the credit
cost and the user's yes. An optional stage that is skipped still writes its checkpoint with the
reason in `decision_log`.

## Blocking gates

`review_gate` blocks export unless the anti-AI-tells gate, the face gate, provenance and
brand_lint all pass. A failing page goes back to the stage that made it, with the gate's reasons.
Never lower a threshold to pass: fix the page, or record the user's own `anti_pattern_override`.
