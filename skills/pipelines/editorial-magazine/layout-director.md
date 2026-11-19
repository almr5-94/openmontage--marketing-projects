# Layout Director — Editorial Magazine

Read `.agents/skills/editorial-design/SKILL.md`. Tool: `editorial_layout`.

1. Write the issue JSON (`projects/<id>/layout/issue.issue.json`): trim, bleed, tokens from the
   approved art system, masthead, section, pages. Page types: `cover`, `contents`, `opening_spread`,
   `feature_spread`, `art_page`, `pull_quote`, `text_page`, `colophon`, `back_cover`.
2. Spreads must start on a left page (LTR: even page; RTL: odd page) — the tool warns otherwise.
3. Run `editorial_layout` with outputs print_pdf, screen_pdf, pngs. Fix every warning and every
   overflow by editing copy or layout, never by shrinking body type below 8.5 pt.
4. Arabic edition: `dir: rtl`, Arabic faces, Latin digits; no drop caps or italics on Arabic.

Write `layout_plan` (one frame per page) and `print_render` (paths and checks).
