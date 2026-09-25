---
name: handdrawn-paperfolk
description: >
  Family A of the hand-drawn explainer system — "paper folk": outlined people on a
  textured paper field, pale circular eyes with small pupils, flat local-colour
  clothing, symbolic props instead of furnished rooms. Trigger `hdx_paperfolk`.
  Use for narrated explainers carried by simple people and everyday objects: how a
  process works, what a policy does to a person, an idea explained by someone holding
  it. Also use it to judge or fix an existing family-A plate, to render one with the
  trained adapter, or to animate a held paper-folk shot. Do NOT use it for myth or
  story silhouettes (that is handdrawn-incise) or for nature, science and diagrams
  (handdrawn-biotext) — the three grammars contradict each other and blending them is
  the one failure this system exists to prevent.
---

# Family A — paper folk

One of **three separate** illustration systems learned from three reference recordings.
Averaging them produces work that is almost right and unmistakably wrong: A's pale
circular eyes cannot coexist with B's black cut-out faces or C's coloured organic
outlines. Pick one family per video, or split the video into sections and give each
section exactly one family. Never one image with two grammars.

Everything below lives on **abood** at `/home/abood/work/openmontage--marketing-projects`.
Run every command with `abrun` from the handle folder
`/Users/ebod/servers-and-projects/abood/projects/openmontage-marketing-projects`. No
source and no compute on the Mac.

## Read these two files before drawing or judging

| Purpose | File |
|---|---|
| Playbook the pipeline loads (palette, typography, motion, prompts, negatives) | `styles/handdrawn-paperfolk.yaml` |
| Construction rules (linework, proportions, face map, layout modes, checklist) | `assets/style/handdrawn/construction/a.yaml` |
| Controlled vocabulary — only phrases whose `use_condition` the picture satisfies | `assets/style/handdrawn/lexicon.json` |
| Fillable templates: character plate, environment, information object | `assets/style/handdrawn/mega-prompts/` |

## The non-negotiables

- **Paper field** `#E7D6BE`, or the pink-grey alternative `#E5DBDB`. Grain is fixed — it
  never animates.
- **Contours** near-black and enclosed, 0.10–0.18% of art width (≈1.9–3.5 px at 1920),
  100% opacity, 0% scatter. Interior marks 0.55–0.9× the contour width.
- **Face map** (normalised inside the face envelope): eye centres x 0.30 / 0.70,
  y 0.35–0.45, eye width 0.20–0.25 of face width, mouth y 0.63–0.75. Pale bounded eye
  enclosure with a **small solid pupil**. No prominent frontal nose. Expression comes
  from pupil placement and mouth angle, not eyelid anatomy.
- **Body** 3.8–4.4 cranial-face units, narrow limbs (0.18–0.30 H), small hands, shoe
  wedges 0.10–0.20 units. Not an eight-head heroic figure.
- **Colour** flat local colour separated by *value*, not by shading. No gradients on
  bodies, no drop shadows, no gloss, no rim light. Pure black in pupils and contours and
  near-white eye whites are allowed.
- **Quiet field** 70–90% for an isolated figure, 35–55% for a lineup. Figure height
  45–60% of art height in the isolated mode.
- **One idea per frame**, and the idea is a physical prop — a podium, a stair, a
  certificate, a pinboard — never a labelled box.

Layout modes, in `construction/a.yaml`: isolated full figure · comparison lineup ·
medium action plate · relationship board · symbolic stairs. Pick the mode *before*
applying an occupancy target.

## The face gate — always on, never optional

Every image that could contain a person passes the face check before it enters a
composition, a render, a thumbnail or a hand-off. There is no flag to switch it off and
no "just this once". A failure is a rejected seed: generate again, change the seed, and
only then adjust the prompt. Never retouch a broken face by hand and call it a pass.

It asks three questions per image, and measures rather than trusts:

1. Is there a person, face or character at all? If not, the image passes.
2. Does every person have two eyes, each with a visible pupil **inside** its eye white?
   `eye_geometry()` locates the whites and rejects a pupil more than 0.55 of the way to
   the rim, or two pupils disagreeing by more than 0.5 horizontally / 0.4 vertically.
3. Is the mouth a simple mark? A filled dark mouth or visible teeth is a rejection —
   `mouth_is_simple()` rejects a largest mouth mark above 0.05 × span².

Implementation: `scripts/style_refs/generate_scene.py` → `face_is_whole()`. Any other
generator — a provider tool, an MCP connector, a hand-written script — carries the same
gate before its output is accepted. To audit frames that already exist, run the same
function over them; `projects/pilot-paperfolk/audit_faces.py` is the worked example.

Where this came from: a pilot shipped with the closing shot showing a character with one
blank eye. Everything else about it had been verified. A vision model will happily answer
"yes, it has a pupil" about a pupil painted on the eye's rim — that is why the gate
measures geometry instead of asking a question.

## Draw a plate

```bash
abrun 'nohup bash .ml/serve_comfyui.sh > /tmp/comfy.log 2>&1 &'   # server on :8188
abrun 'python -m scripts.style_refs.generate_scene a \
  "one person standing on a low podium holding a folded umbrella" \
  --out projects/<proj>/plates/s1.png \
  --must-show "a person on a podium holding an umbrella" \
  --subjects 1 --noun people --seeds 7 101 202 303 404 505'
```

The generator is the checked path and does four things a bare prompt does not:

- **meaning check** — `shows()` asks whether the render actually shows `--must-show`,
  so the picture cannot drift away from the narration line.
- **subject count** — `--subjects` / `--noun` rejects the render when "two people"
  returns three.
- **no lettering** — diffusion cannot spell. Letters are rejected and the real words are
  typeset later in the composition, where they can be spelled and translated. `--allow-text`
  exists only for deliberate abstract marks.
- **face gate** — above, mandatory.

Add `--cutout` for a prop that must animate on its own: the background is flood-filled
away and the result is written as RGBA. Renders land at `*.attempt.png` and are only
moved into place on acceptance, so a rejected image never sits on disk looking approved.

Adapter: `.ml/out-a/hdx_a_sdxl_v1.safetensors`, workflow
`tools/_comfyui/workflows/sdxl-lora-txt2img.json`, 74 training images.
Trained on 74 frames; acceptance run scored **15 of 25 usable, 5 of 5 cases, 0
contamination** (`docs/handdrawn-acceptance-results.md`). Reference images from
`assets/references/handdrawn/dataset-a` may condition a render; Pexels or Pixabay only
for paper or fabric texture — a stock photo in frame breaks the family.

## Move it

`assets/hyperframes/handdrawn-alive/` — copy `alive.js` and `profile-a.js` into the
HyperFrames workspace, load after GSAP:

```html
<section class="clip" data-start="0" data-duration="4">
  <div class="alive-hold">                            <!-- slow camera drift on the shot -->
    <div class="alive-float" data-rise="120">…</div>   <!-- rise and fade, staggered -->
    <div class="alive-pop" data-lead="1.2">…</div>     <!-- pop in, one after another -->
    <div class="alive-scatter">…</div>                 <!-- dissolve away, staggered -->
    <g class="alive-blink">…</g> <g class="alive-breathe">…</g> <g class="alive-sway">…</g>
  </div>
</section>
<div class="alive-grain"></div>                        <!-- fixed paper texture, once -->
```

```js
const tl = gsap.timeline({ paused: true });
HandDrawnAlive.apply(tl, document.getElementById("root"));
window.__timelines["main"] = tl;
```

Measured over 2,497 frame pairs of reference video 1 — this family's own numbers:

| Measured | Value | What you do |
|---|---|---|
| Stepping | changes land every 2nd frame at 24 fps | animate on twos: 12 updates a second |
| Line wobble | 0.0001 median change while holding | never add a boil filter |
| Paper grain | flicker std 0.046 while holding | never animate the texture |
| Shots | 3.46 s median (1.96 p25 / 5.67 p75) | 2–5 s, 8 s maximum |
| Holding | 69% of screen time, 1.38 s median hold | most of the video is a held shot |
| Camera | 32% of shots move, pan 24.4 px/s, **zoom 0** | slow pan, ease-in-out, no push-in by default |
| Secondary events | 93.4 per minute — one every 0.64 s | a prop event on this beat, every held shot |

Rules the layer will not enforce for you: every held shot carries at least one `alive-*`
group; the subject stays still while the props move; never mix smooth 24 fps tweens with
the stepped ones.

## Accept or reject, in this order

1. **Face first** — pale bounded eye enclosures, small purposeful pupils, compact mouth.
2. **Then the body** — about four units tall, narrow limbs, small hands and feet, clear
   prop contact.
3. **Only then** the paper surface and garment texture. *A correct background cannot
   rescue a wrong face.*
4. Compare at the intended final size, inspect the densest region separately, and remove
   accidental interface elements from the acceptance set.

Do not manufacture a cast shadow, rim light or gradient body shading to fill a checklist.
Full criteria and the numeric threshold: `docs/handdrawn-acceptance.md`. Evaluation
prompts: `assets/style/handdrawn/eval-prompts.yaml` (cases A-eval-1…5, fixed seeds
7/101/202/303/404 plus extra seeds).

## When it comes out wrong

| Failure | Cause | Fix |
|---|---|---|
| A black cut-out face appears | family mixing or ambiguous conditioning | keep datasets and triggers apart; retest the isolated adapter |
| Every image contains a certificate | narrow prop coverage in the training content | widen prop and action coverage; caption the certificate explicitly as content |
| Right palette, wrong anatomy | surface terms outweigh construction | raise construction wording in the prompt; improve anatomical coverage |
| Gibberish lettering | diffusion cannot spell | already handled — the generator rejects letters and the composition typesets the words |
| A progress bar appears | training contamination | audit and remove those frames; a negative prompt is not a fix |
| Generic squares standing in for ideas | prop vocabulary too thin | design a meaningful visual token per idea before generating |

These are hypotheses. Change one factor at a time and re-run the same evaluation set.

## Worked example, and rebuilding

A finished narrated explainer built entirely from this family:
`projects/pilot-paperfolk/` — `script.json` (per-scene plate, must-show, subjects, props,
caption, seeds), `make_voice.py` (ElevenLabs → `timing.json`), `make_assets.sh` (health
gate for ComfyUI), `build_composition.py`, `audit_faces.py`, `pilot-final.mp4`.

```bash
abrun 'python -m scripts.style_refs.build_datasets assets/references/handdrawn --per-family 160'
abrun 'python -m scripts.style_refs.caption_frames assets/references/handdrawn'
abrun 'bash .ml/train_family.sh a'
abrun 'python -m scripts.style_refs.motion_analysis assets/references/handdrawn/work/motion-src \
  --fps 24 --out assets/references/handdrawn/motion-profile.json'
```

Measure our own render against the reference:

```bash
abrun 'ffmpeg -i renders/final.mp4 -vf "fps=24,scale=1470:-2" /tmp/f/%05d.png && \
  python -m scripts.style_refs.motion_analysis /tmp/f --flat --fps 24 --out /tmp/ours.json'
```

Compare `pooled` with `videos.video1` in `motion-profile.json`: `drift_pan_px_per_s`,
`drift_zoom_pct_per_s`, `share_of_shots_moving`, `shot_seconds_median`,
`idle_events_per_minute`, and `grain_flicker_std` below 1.2. `line_change_while_holding`
scales with how much linework a scene has — read it as a direction, not a target.

## Evidence and rights

What is measured, observed, inferred or prescribed, and what evidence is missing:
`docs/handdrawn-evidence-boundaries.md`. Colour verification (35/35 samples reproduce):
`docs/handdrawn-palette-verification.md`. Training history:
`docs/handdrawn-training-log.md`.

The reference material is a third party's copyrighted work. Learn the general grammar;
never reproduce their characters, scenes or marks, never put their name in a prompt,
caption, trigger or filename, and never present the output as theirs. **The repository is
public**: no reference frame, dataset image or derived GIF is ever committed — only
measured numbers and reports ship.
