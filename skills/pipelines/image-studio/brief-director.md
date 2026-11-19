# Brief Director — Image Studio Pipeline

## When to Use

First stage. Turn the user's request into a `print_brief` they confirm. No tools are called.

## Ask only what you cannot infer

Infer from the request when it is clear; ask, in one message, for what is missing:

1. **Where will it be seen?** → `formats[]`. Map platforms to presets (`instagram_post`,
   `instagram_story`, `facebook_post`, `linkedin_post`, `x_post`, `youtube_thumbnail`) or print
   trims (`a4`, `poster_18x24`, ...). One image delivered to three platforms = one frame, three
   formats.
2. **What must it achieve?** → `purpose` (one sentence) and `success_criteria` (testable:
   "price readable at phone size", "logo top-left", "Arabic headline").
3. **Exact words** → `mandatory_copy`, verbatim: prices, dates, phone numbers, legal lines.
4. **Language** → `languages[]` with `direction` (`ar` = `rtl`).
5. **Brand** → colours, fonts, logo path, do/don't rules. If the project has a brand file or a
   style playbook, read it — never borrow another project's look.
6. **Pictures** → user's own photos (`user_assets`), or none yet (decided at concept).
7. **How many** → `image_count`, `kind` (`single_image`, `image_set`, `carousel`, `poster`,
   `ad_set`).

## Output

Schema-valid `print_brief` (`schemas/artifacts/print_brief.schema.json`). Present it to the user
as a short plain-language summary, not JSON. Checkpoint `brief` as `awaiting_human`, then
`completed` once confirmed.
