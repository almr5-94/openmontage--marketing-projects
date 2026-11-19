# maison-issue

A collectible art magazine for the user's own house, a client's house or an invented house: one theme framed as an incomplete inventory, a singular cover object, a commissioned image set that pairs archive and contemporary work, long-form writing in the house voice (Arabic as a native RTL edition), a disciplined Maison grid, and a luxury critique gate scored by Claude and by the local models before export.

Manifest: `pipeline_defs/maison-issue.yaml` · stage guides: `skills/pipelines/maison-issue/`

| # | Stage | Produces | Tools | Human approves | What happens |
|---|---|---|---|---|---|
| 1 | `house_brief` | print_brief, decision_log | - | yes | house.yaml loaded; theme in one word or idea; guest voice; languages, page count, trim, paper, finish |
| 2 | `inventory` | maison_inventory, decision_log | - | yes | 20-40 candidates drafted (local model or Claude), sequenced story -> character -> influence, elected by the human or Claude |
| 3 | `cover_object` | asset_manifest, decision_log | met_art, cleveland_art, rijks_art, aic_art, generative_art, image_crop | yes | One singular object, generous negative space; CC0 object, a drawing plate, or an elected Runway generation |
| 4 | `assets` | asset_manifest, decision_log | met_art, cleveland_art, rijks_art, aic_art, pexels_image, pixabay_image, generative_art, image_crop, collage | yes | One commission per story (light, palette, hand, paper); free first, then elected Runway MCP A consistency check on the whole set; each source used once (AP-5); face gate on every person |
| 5 | `writing` | editorial_copy | - | yes | Long-form features, captions and object notes in the house voice; Arabic written natively AP-1 copy lint clean; no superlatives without evidence |
| 6 | `layout` | layout_plan, print_render | editorial_layout, page_render | no | Maison grid preset from house.yaml (wide margins, quiet folio, constant masthead); archive/contemporary spreads |
| 7 | `critique` | maison_critique, quality_gate | editorial_layout, page_render | yes | maison critique (Claude + local models): every rubric criterion 4 or above, with evidence anti-AI-tells gate, face gate, provenance and brand_lint all pass (blocking) |
| 8 | `publish` | publish_log | editorial_layout | yes | Print PDF with bleed and crop marks, paper-colour proof, screen PDF, page PNGs, all handed over |
| 9 | `motion` | decision_log | - | yes | Optional: slow page-turn film, animated cover, drawing-in-progress reveal; HyperFrames and Remotion both offered; Runway MCP elected |

Every stage writes its choices to `decision_log.json`. The critique stage is blocking: see `maison/critique/rubric.md`.
