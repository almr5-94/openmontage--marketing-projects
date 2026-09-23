# Evidence boundaries for the hand-drawn style system

Every rule in `styles/handdrawn-*.yaml` and `assets/style/handdrawn/construction/*.yaml` carries
one of four labels, used exactly as the forensic study defines them.

| Label | Means | Example here |
|---|---|---|
| measured | calculated from specified pixels or file properties | paper field `#E7D6BE`, re-verified in `handdrawn-palette-verification.md` |
| observed | visible in the frames without assuming a hidden history | black figure interiors, white interior marks, pale eye whites |
| inferred | a plausible explanation of the image | vector-friendly construction, separate texture layers |
| prescribed | a reconstruction rule proposed to make reproduction testable | brush widths, head-unit templates, quiet-field targets, caption format |

## Verified independently

- All 35 colour samples of the study reproduce on the original pixels within 3 levels per
  channel (`docs/handdrawn-palette-verification.md`).
- The art field inside the screen recording sits between y 162 and 1,815 of a 2,940 × 1,912
  capture — found independently here by edge detection, and matching the study.
- Frame counts and dimensions match: 6,942 captures, all 2,940 × 1,912.

## Added here, outside the study's scope

The study examines static illustration only. Timing was measured separately over 6,572
consecutive frame pairs (`assets/references/handdrawn/motion-profile.json`): stepping on twos,
no line boil, fixed paper grain, per-family shot length, camera drift and secondary-event rate.
These are measurements of the same recordings, not claims the study makes.

## Not established — do not fill these gaps by guessing

- **Family B's timing.** Its recording shows the player controls 69% of the time. Its motion
  profile is borrowed from family A and labelled as borrowed.
- **Family C's full-body human proportions**, and its human hand construction. The only human
  evidence is a cropped close-up face.
- **Family B's stabilisation setting and internal-to-outer stroke ratio**, and the pixel
  equivalents of B's and C's brush widths: the study gives those numbers for family A only.
- **The source software, brush engines and layer stacks** of all three families. Several
  workflows produce the same flattened pixels.
- **A clean orange for family C's mushroom**: the study's patch crosses other structure, so no
  paint recipe is claimed.
- **Any exact diagram topology.** The network's edge list was never transcribed; a new diagram's
  edges are specified by a human.

## What would materially strengthen a second pass

1. The original artwork files — they would settle brushes, layers and true swatches.
2. Clean recordings without the player overlay, especially for family B, which would replace 43
   mostly-cropped frames with real ones and make its timing measurable.
3. Additional complete family C human figures, to define that family's full-body anatomy.
4. Manual silhouette masks and perpendicular stroke-width measurements, to replace the
   bounding-box occupancy figures with real coverage.

## Rights

The reference material is a third party's copyrighted work. A general style is fine to learn
from; the specifics are not. No reference frame, dataset image or reference GIF is committed to
this public repository — only measured numbers and reports. No source-channel name appears in a
trigger, caption, prompt or filename.
