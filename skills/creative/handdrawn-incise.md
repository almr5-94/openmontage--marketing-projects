---
name: handdrawn-incise
description: >
  Family B of the hand-drawn explainer system — "incised silhouette": opaque black
  figures carrying white cut-in interior marks, staged against saturated scenery with
  gradients, haze and separated depth planes. Trigger `hdx_incise`. Use for story, myth
  and history explainers where figures read as graphic silhouettes — a hero, a ritual, a
  monument, a moment with weight. Also use it to judge or fix an existing family-B plate,
  to render one with the trained adapter, or to animate a held silhouette shot. Do NOT
  use it for outlined paper people (that is handdrawn-paperfolk) or for nature, science
  and diagrams (handdrawn-biotext); and do not carry this family's gradients and haze
  into either of them. Its environment mode is weak — read "The two things that are
  thin" before promising landscapes.
---

# Family B — incised silhouette

One of **three separate** illustration systems learned from three reference recordings.
They are not one style: B's gradients and haze are *required* here and banned in A;
A's pale circular sclera is banned here. Pick one family per video, or split the video
into sections and give each section exactly one family.

Everything below lives on **abood** at `/home/abood/work/openmontage--marketing-projects`.
Run every command with `abrun` from the handle folder
`/Users/ebod/servers-and-projects/abood/projects/openmontage-marketing-projects`. No
source and no compute on the Mac.

## Read these two files before drawing or judging

| Purpose | File |
|---|---|
| Playbook the pipeline loads (palette, typography, motion, prompts, negatives) | `styles/handdrawn-incise.yaml` |
| Construction rules (linework, archetypes, face rule, layout modes, checklist) | `assets/style/handdrawn/construction/b.yaml` |
| Controlled vocabulary — only phrases whose `use_condition` the picture satisfies | `assets/style/handdrawn/lexicon.json` |
| Fillable templates: character plate, environment, information object | `assets/style/handdrawn/mega-prompts/` |

## The non-negotiables

- **The figure is an opaque black mass** `#000000`, built as a filled silhouette, not as
  an outline with fill. It stays clean of environmental speckle and grain.
- **Interior structure is white cut-in marks** at 0.18–0.35% of art width, 100% opacity,
  0% jitter, 0–3% spacing — deliberate spacing and taper, never random scratches, and
  never a pale filled sclera. Working white `#F7F7F0` (prescribed, not an extracted swatch).
- **The profile is a facial feature.** Forehead → nose → chin → hem → feet is designed as
  one silhouette system. Moving a pupil while leaving the head generic does not reproduce
  the family. An eye is nested white rings around a dark centre, or a curved white mark
  for a lowered gaze.
- **Proportions follow an archetype**, not one template: compact broad 2.8–3.6 units,
  elongated narrow 4.0–5.0. A helmet crest is an accessory that makes the silhouette tall
  without lengthening the body — judge the face unit separately from the crest.
- **Gradients, haze and saturated colour are part of this style.** Do not ban them. Scene
  colour is chosen per scene: warm props against cool fields, or the reverse. Background
  `#3B7673`; accents `#E48529`, `#7B0000`, `#57905A`, `#CBECCF`.
- **Depth is three separated planes**: near planes crisp and granular, distant planes
  losing contrast toward the haze colour. Landscape keeps a 25–45% low-detail opening.
- **Clearance**: keep a readable gap around head, action hand and prop so two black
  masses never merge. The deepest figure black stays unlifted while environmental darks
  may be lifted or tinted.

Layout modes, in `construction/b.yaml`: action silhouette · landscape · central monument ·
theatrical trio. Pick the mode before applying any occupancy target — "70% empty" would
misdescribe a landscape, where depth-plane legibility is the real target.

## The face gate — always on, never optional

A silhouette face is still a face, and an eye built from white rings fails just as
visibly as a missing pupil. Every image that could contain a person passes the check
before it enters a composition, a render, a thumbnail or a hand-off. No flag turns it
off. A failure is a rejected seed: generate again, change the seed, and only then adjust
the prompt. Never retouch a broken face by hand and call it a pass.

1. Is there a person, face or character at all? If not, the image passes.
2. Does every person have two eyes, each with a visible pupil inside its eye opening?
   `eye_geometry()` measures position rather than asking — a mark painted on the rim
   fails, and two eyes disagreeing by more than 0.5 horizontally / 0.4 vertically fail.
3. Is the mouth a simple mark, without teeth or a filled dark hole? `mouth_is_simple()`
   rejects a largest mouth mark above 0.05 × span².

Implementation: `scripts/style_refs/generate_scene.py` → `face_is_whole()`. Any other
generator carries the same gate. Audit existing frames with the same function —
`projects/pilot-paperfolk/audit_faces.py` is the worked example.

Where this came from: a pilot shipped with a closing shot showing a character with one
blank eye; everything else about it had been verified. A vision model will answer "yes,
it has a pupil" about a pupil painted on the rim — so the gate measures geometry.

## Draw a plate

```bash
abrun 'nohup bash .ml/serve_comfyui.sh > /tmp/comfy.log 2>&1 &'   # server on :8188
abrun 'python -m scripts.style_refs.generate_scene b \
  "a lone figure raising a long staff against a wide evening sky" \
  --out projects/<proj>/plates/s1.png \
  --must-show "a black silhouette figure holding a raised staff" \
  --subjects 1 --noun people --seeds 7 101 202 303 404 505'
```

The generator is the checked path: it verifies the render actually shows `--must-show`,
counts subjects, rejects lettering (diffusion cannot spell — the real words are typeset
later in the composition), and runs the face gate. `--cutout` keys the background away
for a prop that must animate on its own. Renders land at `*.attempt.png` and only move
into place on acceptance.

Adapter: `.ml/out-b/hdx_b_sdxl_v1.safetensors`, workflow
`tools/_comfyui/workflows/sdxl-lora-txt2img.json`, **43 training images** — the smallest
of the three, mostly detail crops. Acceptance scored **17 of 25 usable, 5 of 5 cases, 0
contamination**, which is stronger than 43 frames deserve, *with a weak environment mode*
(`docs/handdrawn-acceptance-results.md`). Reference frames from
`assets/references/handdrawn/dataset-b`; stock photos only for paper or fabric texture.

A new dashboard or interface object in this family is an extrapolation beyond the
evidence and needs separate approval before it ships.

## Move it

`assets/hyperframes/handdrawn-alive/` — copy `alive.js` and `profile-b.js` into the
HyperFrames workspace, load after GSAP, then the same markup as the other families:
`alive-hold` on the shot, `alive-pop` / `alive-float` / `alive-scatter` on props,
`alive-grain` once.

```js
const tl = gsap.timeline({ paused: true });
HandDrawnAlive.apply(tl, document.getElementById("root"));
window.__timelines["main"] = tl;
```

**This family's timing is borrowed from family A, and the profile says so.** Reference
video 2 was recorded with the player's controls on screen for 69% of its frame pairs, so
its own numbers are contaminated: the "1.4 s median shot" is the seek-preview thumbnail
appearing and disappearing, and the "19.9%/s zoom" is the controls sliding, not the
picture. Do not quote either. Until a clean recording exists, use A's measured beat:

| Borrowed from family A | Value | What you do |
|---|---|---|
| Stepping | every 2nd frame at 24 fps | animate on twos: 12 updates a second |
| Line wobble | none | no boil filter; the silhouette holds its shape |
| Grain | fixed | no grain flicker inside the figure |
| Shots | 3.46 s median | 2–5 s, 8 s maximum |
| Camera | 32% of shots move, 24.4 px/s pan | slow drift and atmospheric movement, ease-in-out |
| Secondary events | ~one per 0.64 s | one dominant gesture plus staged props on that beat |

Entrances rise or slide *along the action direction* and exit the same way — that
direction is the composition's spine.

## Accept or reject, in this order

1. **Fill the figure mentally as one black shape** — does the role and gesture still read?
2. **Then the profile**, the negative-space openings, and the direction of the long prop
   or arm.
3. **Then the incised marks** — deliberate spacing and taper, not random scratches.
4. **Last, the setting** — atmosphere without contaminating the figure with indiscriminate
   texture or naturalistic shading.
5. Compare at the intended final size, inspect the densest region separately, and remove
   accidental interface elements from the acceptance set.

Full criteria: `docs/handdrawn-acceptance.md`. Evaluation prompts:
`assets/style/handdrawn/eval-prompts.yaml` (cases B-eval-1…5, fixed seeds
7/101/202/303/404 plus extra seeds).

## The two things that are thin

**Environments.** With 43 mostly-cropped training frames and almost no clean
environments, B's landscapes fall back to generic flat vector. **Not fixed.** Use family
B for figures and props, and either carry its scenes with A- or C-style environments —
declared as such, never blended inside one image — or get a clean recording.

**Timing.** Unmeasurable for the same reason, as above.

Both are fixed by one thing you can supply:

```bash
# play the video full screen, let the controls fade, then record the screen only
# (no browser window, no cursor), and drop the file next to the others:
#   assets/references/handdrawn/raw-video/video2.mov
```

Then rerun `build_datasets.py`, `caption_frames.py`, `.ml/train_family.sh b`, and
`motion_analysis.py`: B gets real environment examples and its own measured timing
instead of A's borrowed numbers.

## When it comes out wrong

| Failure | Cause | Fix |
|---|---|---|
| Figures are grainy throughout | texture wording, or contaminated figure examples | drop global-grain phrases; check the figure masks in the dataset |
| Pale circular sclera appears | family A leaking in | keep datasets and triggers apart; retest the isolated adapter |
| Every setting repeats one landscape | scene redundancy or memorisation | reduce repeated frames of that scene; add scene groups |
| Black masses merge into a blob | no clearance planned | re-stage with gaps around head, action hand and prop |
| A progress bar appears | training contamination | audit and remove those frames; a negative prompt is not a fix |
| Great on training images, poor on new scenes | overfitting or weak base | judge on held-out content; adjust diversity and duration |

These are hypotheses. Change one factor at a time and re-run the same evaluation set.

## Rebuilding

```bash
abrun 'python -m scripts.style_refs.build_datasets assets/references/handdrawn --per-family 160'
abrun 'python -m scripts.style_refs.caption_frames assets/references/handdrawn'
abrun 'bash .ml/train_family.sh b'
```

Measure our own render:

```bash
abrun 'ffmpeg -i renders/final.mp4 -vf "fps=24,scale=1470:-2" /tmp/f/%05d.png && \
  python -m scripts.style_refs.motion_analysis /tmp/f --flat --fps 24 --out /tmp/ours.json'
```

Compare `pooled` with `videos.video1` (A's borrowed block), **not** `video2`, until a
clean capture exists.

## Evidence and rights

Boundaries between measured, observed, inferred and prescribed — and what is missing for
this family in particular: `docs/handdrawn-evidence-boundaries.md`. Colour verification:
`docs/handdrawn-palette-verification.md`. Training history: `docs/handdrawn-training-log.md`.

The reference material is a third party's copyrighted work. Learn the general grammar;
never reproduce their characters, scenes or marks, never put their name in a prompt,
caption, trigger or filename, and never present the output as theirs. **The repository is
public**: no reference frame, dataset image or derived GIF is ever committed.
