# Concept Director — Image Studio Pipeline

## When to Use

After the brief. Produce `studio_proposal` + `decision_log` and get approval. **This is the
spending gate**: no paid image call happens before `approval.status` is `approved`.

## 1. Read what is really available

```python
from tools.tool_registry import registry; registry.discover()
registry.capability_catalog()["image_generation"]   # status per tool; offer only the LOCAL ones
# Paid generation is never a registry tool here: it goes through the Runway MCP connector.
```

A tool is a real option only if its status is `available`. A green status means a key exists,
not that the call will succeed.

## 2. Two or three concepts

Each concept differs in **visual approach** (photo-real scene / illustrated / typographic-only /
product cut-out on colour / collage), **typography**, and **palette** — not just colour swaps.
For each: `why_this_works` tied to the brief's purpose, and the risk. Typographic-only is often
the best answer for announcements, quotes and price offers, and it costs nothing.

To show a concept cheaply, you may render a grey-box mock with `page_render` (free): the real
template, placeholder rectangles for pictures, real copy.

## 3. Tool election (Rule Zero)

Present the image-source menu: free first — CC0 museum art (`met_art`, `cleveland_art`, `rijks_art`,
`aic_art`), stock (`pexels_image`, `pixabay_image`), the user's own photos, seeded drawing
(`generative_art`), local models (`local_diffusion`, `qwen_image_local`, `comfyui_image` if available,
`qwen_image_edit_local` to edit the user's photo); then **generation through the Runway MCP connector**,
quoted in credits with `prepare_runway_call` and run only after the user elects it (`record_election`).
No other paid image service is ever offered (owner rule: images and video go through Runway only).
Offer enhancement only if needed (`upscale`, `bg_remove`, both local). Wait for the user's pick.

Log one `decision_log` entry per capability with every offered option in `options_considered`
(`category: provider_selection`, `subject: "Image source"`), plus `concept_selection`.

## 4. Cost

`cost_estimate.line_items`: images × unit price, plus one retry per image as contingency,
upscales, and `page_render` at 0. `budget_verdict` against `print_brief.budget_usd`.

Checkpoint `concept` as `awaiting_human`; complete only on explicit approval.
