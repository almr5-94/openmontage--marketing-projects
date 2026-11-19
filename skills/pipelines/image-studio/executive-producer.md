# Executive Producer — Image Studio Pipeline

## When to Use

You run the `image-studio` pipeline: one or more finished still images — a social post, a
carousel, a poster, a set of ad variants, a thumbnail. You own the run from brief to hand-off.
Read `skills/meta/print-production.md` first; every rule there applies.

## The run

```
brief -> concept -> layout -> assets -> render -> review -> publish
```

| Stage | Director | Artifact | Human gate |
|-------|----------|----------|-----------|
| brief | brief-director | `print_brief` | yes |
| concept | concept-director | `studio_proposal`, `decision_log` | yes — tool election + cost |
| layout | layout-director | `layout_plan` | no (self-review) |
| assets | asset-director | `asset_manifest` | yes — sample first |
| render | render-director | `print_render` | no (checks must pass) |
| review | review-director | `print_review` | yes — the user sees the images |
| publish | publish-director | `publish_log` | yes |

Start: `init_project('<id>', title='<Title>', pipeline_type='image-studio')`, then
`python -m backlot open <id>` (best effort). Resume with `checkpoint.get_next_stage()`.

## Choosing this pipeline

- Still images of any kind → **image-studio**.
- More than ~4 pages that are read in order (magazine, brochure, catalog, report) → **magazine**.
- Motion of any kind → a video pipeline, not this one.
- A single picture with **no text at all** still goes through image-studio, but the layout stage
  is one full-bleed frame and render is a straight export at the exact size.

## Budget and sampling

Default budget USD 1.00. Generate **one** sample image with the elected tool, show it, and only
then batch the rest. Variants of one frame (A/B ad tests) count as separate images in the
cost estimate. Track spend with `tools/cost_tracker.py`.

## Send-backs

- Copy does not fit at render → back to layout (shorter copy or bigger box), not "smaller font
  until it fits" below the legibility floor (see layout-director).
- Image fails the minimum size → back to assets (upscale or regenerate), logged.
- User rejects the concept at review → back to concept; the old images move to
  `assets/images/components/`.
