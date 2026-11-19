# Asset Director — Image Studio Pipeline

## When to Use

Fill every image slot in `layout_plan` with the tools elected at concept. Produce
`asset_manifest` (scene_id = frame id).

## Order of work

1. **Read the provider skill** before the first call: `skills/creative/image-provider-usage.md`,
   `skills/creative/image-gen-usage.md`, and the tool's Layer 3 skills (`agent_skills` in
   `get_info()`, under `.agents/skills/`).
2. **Sample**: generate the single most important slot (the hero), show it to the user, and
   wait. Only then batch the rest.
3. **Batch** the remaining slots with the same tool and settings. Keep prompts consistent
   (shared style suffix, same seed where the tool supports it) so a set looks like a set.
4. **Fit**: check each image's pixel size against the slot's `min_px`; run `upscale` when short;
   `bg_remove` for product cut-outs. Log each enhancement in the manifest.
5. **Never put words in the picture prompt** that must be read (prices, names, dates). Ask the
   model for clean negative space where the headline will sit ("empty sky upper third").

## Files

`projects/<id>/assets/images/<frame>-<slot>.png`. A retake is `<frame>-<slot>.v2.png`; the
rejected take moves to `assets/images/components/`. Never delete one.

## Manifest entries

`{"id", "type": "image", "path", "source_tool", "scene_id": "<frame id>", "prompt", "model",
"cost_usd"}` — schema `asset_manifest`. Record stock licence and author in the entry for stock
images.

Checkpoint `assets` as `awaiting_human` with the contact sheet of all images.
