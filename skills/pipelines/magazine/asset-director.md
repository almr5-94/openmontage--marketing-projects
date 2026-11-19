# Asset Director — Magazine Pipeline

## When to Use

The wireframe fits. Fill every image slot with the elected tools. Produce `asset_manifest`
(scene_id = page id).

## Order

1. Read `skills/creative/image-provider-usage.md`, `skills/creative/image-gen-usage.md` and the
   elected tool's Layer 3 skills before the first call.
2. **Cover first.** Generate 2–3 cover candidates at the cover slot's aspect, with clean
   negative space where the masthead and cover lines sit (state it in the prompt: "upper fifth
   empty dark sky"). The user picks one. Unpicked candidates go to `assets/images/components/`.
3. **Sample one interior image**, show it, then batch the rest with a shared style suffix so
   the issue looks like one publication.
4. **Size**: check every image against its slot's `min_px`; `upscale` when short (log it).
5. Charts and diagrams: `diagram_gen` or hand-authored SVG in the HTML — not image models.
6. Stock images: record author, source URL and licence in the manifest entry.

No readable text inside generated pictures — headlines, captions and numbers are set in HTML.

## Files

`projects/<id>/assets/images/p03-hero.png`, retakes `p03-hero.v2.png`; never delete a take.

Checkpoint `assets` as `awaiting_human` with a contact sheet.
