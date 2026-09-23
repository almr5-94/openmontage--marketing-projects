# Acceptance results — the three family adapters

Judged against `docs/handdrawn-acceptance.md`, which was written before training.
Renders: 5 evaluation cases × 5 seeds × (with adapter, without adapter) per family —
150 images, in `assets/references/handdrawn/work/acceptance/` (local only).

"Usable" means an image that needs no retouching: the family's construction is right
**and** the requested content is right. Style-right-but-content-wrong is not counted.

| Family | Usable of 25 | Cases with a usable output | Contamination | Verdict |
|---|---|---|---|---|
| A paper folk | 15 | 5 of 5 | 0 | **pass** (exactly at the threshold) |
| C bio texture | 17 | 5 of 5 | 0 | **pass** |
| B incised silhouette | 17 | 5 of 5 | 0 | **pass**, with a weak environment mode |

Threshold was: at least 15 usable, at least 3 cases with a usable output, zero
contamination, no structural failure recurring more than 5 times, and a visible
difference against the base model.

## What each adapter learned

- **A** — flat enclosed figures on a paper field, pale round eyes, small pupils, no
  volumetric shading. The base model answers the same prompts with pencil-sketch
  realism, so the difference is unambiguous.
- **C** — layered organic masses, muted earth and blue-green, cut-paper feel, callout
  and network modes recognisable. Base output is engraving or cluttered infographic.
- **B** — opaque black figures with white incised interior marks over staged colour.
  Stronger than expected from 43 mostly-cropped training frames.

## Where each one is weak

- **A, content counting.** "Two people" often returns three. The caption vocabulary
  carries counts, but SDXL is unreliable at them; specify the count in the prompt and
  check the render.
- **A and C, lettering.** Every card, label and callout renders gibberish text. Expected:
  the playbooks say to reserve label areas and typeset text afterwards.
- **B, environments.** The landscape and monument cases lose the granular near-ground and
  haze and come back as generic flat vector. Its environment evidence is the thinnest in
  the whole project.
- **C, diagram mode.** The cream-disc-on-blue network appears in 3 of 5 seeds; the other
  two dissolve into blobs. More diagram frames would fix it, and there are only a handful
  in the source.

## About the automatic contamination check

The player-overlay detector flagged 1 A, 5 B and 3 C renders. All nine were inspected by
eye and all nine are false positives: the detector looks for a red bar low in the frame, a
bright title band and a bright rectangle over the picture, and generated art trips those
shapes honestly. No render contains a player control, cursor or platform mark.

## Not tested here

Whether a generated diagram is factually correct. Style matching cannot make a wrong
connection list right; the edges are supplied and checked by a human.
