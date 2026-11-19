# Layout Director — Image Studio Pipeline

## When to Use

After concept approval. Produce `layout_plan` (`units: "frames"`): one frame per distinct
image, each listing its text and image slots.

## Per frame

- `id`: `f01`, `f02` ... (carousel slides in reading order).
- `format`: the primary format; the render stage also exports the brief's other formats from
  the same HTML when the design reflows (the stills template sizes type in `--u`, a unit that follows the shorter side, so one file serves 1:1, 4:5, 9:16 and 16:9).
- `elements[]`: every text element with its exact `content` (from mandatory copy and the
  concept), and every image slot with `image_prompt`, `image_source`, `aspect`, and `min_px`
  (the frame's pixel size × 1, or × 2 when the picture is cropped/zoomed).

## Legibility floors (phone screens)

| Format | Headline min | Body min | Max headline words |
|--------|--------------|----------|--------------------|
| instagram_post / square | 64 px | 30 px | 8 |
| instagram_story | 72 px | 34 px | 8 |
| youtube_thumbnail | 90 px | — | 5 |
| facebook / linkedin / x | 48 px | 24 px | 10 |

Below the floor is a layout failure: shorten the copy or change the layout, never shrink type.

## Safe zones

Story: keep text out of the top 250 px and bottom 300 px (platform UI). Thumbnail: nothing
important in the bottom-right 200×80 px (timestamp). Carousel: the first slide must work alone.

## Prove it fits

Author the frame HTML now with grey placeholders (`background:#bbb`) in the image slots, render
with `page_render` (`mode: "still"`), and confirm `checks.pass` and a visual look. This costs
nothing and catches overflow before any picture is paid for.
