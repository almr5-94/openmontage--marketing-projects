# Render Director — Magazine Pipeline

## When to Use

Replace the wireframe's grey boxes with the real pictures and render the final PDF. Produce
`print_render`.

## Steps

1. In `projects/<id>/layout/issue.html`, swap each grey box for its image
   (`<img class="bleed" src="../assets/images/p01-cover.png">` or a placed `<img>` with
   `object-fit: cover` and a deliberate `object-position` so faces are not cut).
2. Screen PDF:
   ```python
   PageRender().execute({"html_path": "projects/<id>/layout/issue.html", "mode": "pdf",
       "output_path": "projects/<id>/renders/<id>_screen.pdf", "size_preset": "<trim>",
       "expected_pages": <page_count>, "preview_dpi": 110})
   ```
3. Print PDF (only if `pdf_print` is in the brief): a second HTML entry point
   `issue.print.html` that sets `@page` to trim + 2 × bleed and adds bleed to full-bleed
   images; render with `width_mm`/`height_mm` = trim + 6 mm.
4. Cover PNG for social: `mode: "still"` on a cover-only HTML, or take `page-01.png` from the
   previews at higher DPI (`preview_dpi: 200`).
5. `checks.pass` must be true for every PDF. Fix and re-render otherwise.
6. Record everything in `print_render.outputs[]` (pages, page_size_mm, page_previews,
   checks_pass, problems).
