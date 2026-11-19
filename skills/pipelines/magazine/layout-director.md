# Layout Director — Magazine Pipeline

## When to Use

After the copy is approved. Produce the flatplan as `layout_plan` (`units: "pages"`) and prove
it fits with a wireframe render — before any picture is generated.

## The flatplan

One frame per page, `id` `p01` ... `pNN`, in order. Page 1 is the front cover (right-hand);
even pages are left-hand, odd pages right-hand (`side`) — reversed for right-bound Arabic
issues. Spreads (left + right) are designed together: a feature opener usually takes a spread.

Each page lists:

- `role`: cover, inside_cover, contents, editor_letter, feature_open, feature_body, news, ad,
  back_cover ...
- `copy_ref`: the `editorial_copy` piece id.
- `elements`: text roles (kicker, headline, dek, body, pull_quote, caption, folio) and image
  slots with `image_prompt`, `image_source`, `aspect`, and `min_px` computed from the slot size:
  `width_mm / 25.4 × 300` for print (× 150 for screen-only).

## Wireframe proof (mandatory)

Build `projects/<id>/layout/issue.html` from the template now: every page, real copy, grey
boxes (`background:#c9c9c9`) for pictures at their real sizes. Render with `page_render`
(`mode: "pdf"`, `expected_pages` = page count, size preset = trim). Required: `checks.pass`.
Fix overflow by editing copy length (send back to editorial for big cuts) or by moving the
break to the next page — never by dropping body type below 8.5 pt or leading below 1.3.

## Page furniture

Folio (page number + section) on every page except covers and full-bleed openers; contents
page numbers must match the real page numbers; continued-on lines where a story jumps.
