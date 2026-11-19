# maison-campaign

High-art luxury marketing for a house: one idea and one image per execution, the product as an object of craft inside an artful scene or drawing, minimal copy (a line, the house name, sometimes nothing) and never discount or urgency language. Safe / Bold / Conceptual treatments from the fashion-direction skill under the Maison doctrine; a master composition with per-placement variants (single and double page print, out-of-home, social stills and carousels, 6-15 s motion, a campaign book) keeping safe areas and text-free versions.

Manifest: `pipeline_defs/maison-campaign.yaml` · stage guides: `skills/pipelines/maison-campaign/`

| # | Stage | Produces | Tools | Human approves | What happens |
|---|---|---|---|---|---|
| 1 | `campaign_brief` | print_brief, decision_log | - | yes | The one idea; the product as an object of craft; placements and sizes; languages |
| 2 | `treatments` | shot_list, studio_proposal, decision_log | generative_art, image_crop | yes | Safe / Bold / Conceptual treatments; house.yaml overrides fashion-direction defaults; shot list with Runway-ready prompts (qualities, never names) |
| 3 | `assets` | asset_manifest, decision_log | met_art, cleveland_art, rijks_art, aic_art, pexels_image, pixabay_image, generative_art, image_crop, collage | yes | One commanding image per execution; free first, then elected Runway MCP with credits shown; face gate on every person |
| 4 | `layout` | layout_plan, print_render | editorial_layout, page_render, image_crop | no | A master composition, then variants per placement (4:5 social, 9:16, OOH portrait/landscape, double page) with safe areas and a text-free version |
| 5 | `critique` | maison_critique, quality_gate | editorial_layout, page_render | yes | maison critique (Claude + local models): every rubric criterion 4 or above, with evidence anti-AI-tells gate, face gate, provenance and brand_lint all pass (blocking) No discount or urgency language anywhere (AP-1) |
| 6 | `publish` | publish_log | editorial_layout | yes | Every placement file handed over with its size and safe area |
| 7 | `motion` | decision_log | - | yes | Optional 6-15 s motion version: HyperFrames and Remotion both offered; Runway MCP elected |

Every stage writes its choices to `decision_log.json`. The critique stage is blocking: see `maison/critique/rubric.md`.
