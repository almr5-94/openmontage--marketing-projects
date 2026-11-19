# Render Director — Image Studio Pipeline

## When to Use

Typeset every frame with its images and export every format the brief asked for. Produce
`print_render`.

## Steps

1. Copy `print-studio/css/print-base.css` to `projects/<id>/layout/print-base.css`; set the
   brand tokens (`--accent`, `--paper`, `--ink`, fonts) in each frame's `<style>` or a shared
   `brand.css`.
2. One HTML per frame: `layout/f01.html` ... starting from
   `print-studio/templates/stills/social-post.html`. Replace placeholders with
   `../assets/images/...` and the exact copy from the layout plan.
3. Render each frame × format:
   ```python
   PageRender().execute({"html_path": "projects/<id>/layout/f01.html", "mode": "still",
       "size_preset": "instagram_post", "output_path": "projects/<id>/renders/f01_instagram_post.png"})
   ```
   Use `.jpg` for photographic social posts (smaller upload), `.png` when there is transparency
   or flat colour.
4. Any output with `checks.pass == false` is fixed and re-rendered before you move on.
5. Record every output in `print_render.outputs[]` with `frame_id`, `size_name`, `pixel_size`,
   `checks_pass`, `problems`.

## Multi-format from one frame

If a frame must ship in shapes with very different aspect ratios (1:1 and 9:16), check the
reflow visually; if the design breaks, author a per-format variant (`f01.story.html`) rather
than accepting a cramped layout.
