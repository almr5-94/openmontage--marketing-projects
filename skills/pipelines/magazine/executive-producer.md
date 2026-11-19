# Executive Producer — Magazine Pipeline

## When to Use

You run the `magazine` pipeline: a multi-page publication read in order — magazine, zine,
brochure, catalog, annual or illustrated report — delivered as a PDF (screen and/or print) with
a PNG of every page. Read `skills/meta/print-production.md` first; every rule there applies.

## The run

```
brief -> concept -> editorial -> layout -> assets -> render -> review -> publish
```

| Stage | Director | Artifact | Human gate |
|-------|----------|----------|-----------|
| brief | brief-director | `print_brief` | yes |
| concept | concept-director | `studio_proposal`, `decision_log` | yes — design direction, tools, cost |
| editorial | editorial-director | `editorial_copy` | yes — the user reads the words |
| layout | layout-director | `layout_plan` (flatplan) | no — wireframe render must pass |
| assets | asset-director | `asset_manifest` | yes — cover + sample first |
| render | render-director | `print_render` | no — checks must pass |
| review | review-director | `print_review` | yes — the user reads the proof |
| publish | publish-director | `publish_log` | yes |

Start: `init_project('<id>', title='<Title>', pipeline_type='magazine')`, then
`python -m backlot open <id>` (best effort).

## Why words come before pictures

Copy is cheap to change and pictures are not. The editorial stage fixes the words, the layout
stage proves they fit with grey boxes, and only then are pictures generated at the exact sizes
the pages need. Generating pictures first and writing to fit them wastes credits on images that
end up cropped or cut.

## Scale and time

A 16-page issue with ~10 generated images is a 60–90 minute run. Above 24 pages, propose
splitting the work: build and approve one section (cover + one feature) end to end, then
produce the rest in the same design. Budget default USD 5.00.

## Send-backs

- Copy overflows at render → edit the copy to length (editorial), not shrink the type below
  8.5 pt body.
- A page count that is not a multiple of 4 for a saddle-stitched print job → back to brief with
  the options (add an ad page, a contents page, or a notes page).
- User rejects the cover → regenerate the cover only; keep the old one in components/.
