# Brief Director — Magazine Pipeline

## When to Use

First stage. Produce a confirmed `print_brief` with `kind` in (`magazine`, `brochure`,
`catalog`, `report`, `zine`). No tools are called.

## Settle these, asking only what you cannot infer

1. **Kind and purpose** — what the publication is for, in one sentence; the reader it serves.
2. **Trim size** → `formats[0]`: `magazine_standard` (230×300 mm), `magazine_us`, `a4`, `a5`,
   `us_letter`. Record `bleed_mm: 3` and `dpi: 300` when it goes to a print shop.
3. **Page count** → `page_count`, including covers. Saddle-stitched print needs a multiple of 4;
   a screen-only PDF can be any number.
4. **Languages** → `languages[]`. Bilingual issues: decide whether pages are mirrored (one
   language per page) or parallel (both on the page). Arabic-first publications bind on the
   right — record it in `success_criteria`.
5. **Sections** → `key_messages`: the stories or sections the user already has in mind.
6. **Material the user supplies** → `user_assets` (photos, logos, existing articles), and
   `mandatory_copy` (masthead name, issue number, date, price, legal lines) verbatim.
7. **Delivery** → `delivery`: `pdf_screen`, `pdf_print`, `png` covers for social.
8. **Brand** — read the project's own brand material or a style playbook; never borrow
   another project's look.

Present a short plain-language summary, then checkpoint `brief`.
