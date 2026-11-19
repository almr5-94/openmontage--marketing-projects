# Concept Director — Magazine Pipeline

## When to Use

After the brief. Produce `studio_proposal` + `decision_log`; get approval. No paid call before
`approval.status` is `approved`.

## Design directions (two or three)

Each direction specifies:

- **Typography** — one Latin display face and one Latin text face, plus one Arabic display and
  one Arabic text face if the issue has Arabic, all from `print-studio/fonts/FONTS.yaml`
  (curated OFL library). At most two families per script. Fallback faces (Noto, DejaVu, Arial,
  Roboto, Inter...) are banned (AP-4). A new font must be OFL or similarly licensed, added as a
  file with its licence and registered in FONTS.yaml.
- **Grid** — columns per page (2 for brochures, 3 for magazines), margins, gutter.
- **Image strategy** — photo-real generated, illustrated, stock photography, the user's photos,
  or typographic; the cover treatment specifically.
- **Palette** — 3–5 colours as hex.

Render a two-page mock of each direction (cover + one feature page) from
`print-studio/templates/magazine/issue.html` with grey picture boxes — `page_render` is free —
and show the PNGs. Directions are judged on pages, not on adjectives.

## Tool election (Rule Zero)

Present the image-source menu: free first (CC0 museum art `met_art`/`cleveland_art`/`rijks_art`/
`aic_art`, stock `pexels_image`/`pixabay_image`, seeded `generative_art`, local models from
`registry.capability_catalog()["image_generation"]` that are local and `available`), then
the Runway MCP connector (quoted in credits with `prepare_runway_call`, run only after the user elects it). No other paid image service is ever offered. Include "user's photos" and "no pictures". Ask separately about `upscale` if print resolution
requires it, and `diagram_gen` if the issue has charts or diagrams. Log every election in
`decision_log` with all options considered.

## Cost

Line items per image (cover counted separately with 2 retries), upscales, and `page_render` at
0. Include the time estimate.
