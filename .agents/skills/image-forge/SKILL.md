---
name: image-forge
description: Crop, mask and batch-process images for editorial pages with the image_crop tool - smart crops to exact sizes, geometric fragments (circle, ellipse, triangle, hexagon, polygon, arc, stripe), contact sheets. Use after art-sourcing and before collage or layout.
---

# Image forge (Layer 2)

The `image_crop` tool (Pillow, free, local) does the mechanical image work. Upstream guidance:
`vendor/image-forge/skills/design-media/image-forge/SKILL.md` (audited). **Its Gemini route is
removed:** new pixels come only from the Runway MCP, never from a pay-per-call image API.

## Operations
- `smart_crop` — exact `target` ("1200x1500"), `gravity`: attention (default: finds detail and
  contrast), entropy, center, north/south/east/west. `engine: "imagemagick"` uses the vendored
  ImageMagick 7 script. Warns when the source had to be upscaled.
- `mask` — `shape` + `shape_params`, optional `rim` (a thin metal or paper edge). Output is an RGBA
  PNG trimmed to the shape, in `assets/fragments/`.
  - circle / ellipse (`r`, `cx`, `cy`), triangle, hexagon, polygon (`points` as 0..1 pairs),
    arc (`ri`, `start`, `end` degrees — a ring segment), stripe (`count`, `band`, `angle`).
  - `feather` softens the edge; `trim: false` keeps the original canvas.
- `batch` — resize, thumbnail, crop, format, strip metadata, auto-orient over many files.
- `montage` — a labelled contact sheet for review (keeps fragment transparency).

## Doing it well
- Geometry is the editorial voice: a circle cut from an astrolabe, an arch cut from a facade,
  stripes of a textile. Cut **along the object's own geometry** when it has one.
- One shape family per spread. Mixing circles, hexagons and stripes on one page reads as clip-art.
- Keep the subject's edges: crop with margin, then mask; never mask through a face or a hand.
- Every output is recorded as `licence: derived` with its parent and the crop parameters —
  never hand-copy a file into `assets/` (it would fail the provenance gate).
