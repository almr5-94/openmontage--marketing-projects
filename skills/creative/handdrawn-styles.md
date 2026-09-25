# Hand-drawn Explainer Styles (Layer 2)

Three separate illustration systems learned from three reference recordings, plus the motion
that keeps a held scene alive. **They are not one style.** Averaging them is the failure this
whole system exists to prevent: A's pale circular eyes, B's black incised silhouettes and C's
local-colour organic drawing contradict each other, and a model that blends them produces work
that is almost right and unmistakably wrong.

| Family | Trigger | Playbook | Construction | Motion profile | Looks like |
|---|---|---|---|---|---|
| **A — paper folk** | `hdx_paperfolk` | `styles/handdrawn-paperfolk.yaml` | `assets/style/handdrawn/construction/a.yaml` | `profile-a.js` | outlined people on textured paper, pale round eyes, flat clothing colour, symbolic props |
| **B — incised silhouette** | `hdx_incise` | `styles/handdrawn-incise.yaml` | `construction/b.yaml` | `profile-b.js` (borrowed) | solid black figures with white cut-in marks, saturated staged scenery, haze and gradients |
| **C — bio texture** | `hdx_biotext` | `styles/handdrawn-biotext.yaml` | `construction/c.yaml` | `profile-c.js` | organic filled shapes, coloured outlines, drawn veins and rings, diagrams, big radial irises |

## One skill per family - load the family, not this router

This file is the router. The per-family detail is a skill of its own, and each one is
self-contained: construction numbers, the face gate, the generate command, that family's
own measured motion, its acceptance order and its failure map.

| Family | Skill | Versioned copy in this repo |
|---|---|---|
| A paper folk | `handdrawn-paperfolk` | `skills/creative/handdrawn-paperfolk.md` |
| B incised silhouette | `handdrawn-incise` | `skills/creative/handdrawn-incise.md` |
| C bio texture | `handdrawn-biotext` | `skills/creative/handdrawn-biotext.md` |

Installed for Claude Code at `~/.claude/skills/handdrawn-{paperfolk,incise,biotext}/SKILL.md`,
byte-identical to the copies above - edit the repo copy and reinstall, never only one side.

Loading one family's skill instead of this file is the point: an agent that only carries the
family it is drawing cannot average three contradictory grammars by accident.

## Step 0 — pick the family, and say so

Ask what the video is: people and ideas (A), story and myth (B), nature and science (C). If the
brief spans two, split the video into sections and give each section one family — never one
image with two grammars. Record the choice in the proposal; a silent family swap mid-project is
a contract violation in the same way a silent runtime swap is.

## Step 1 — script

Hook, question, explanation carried by one physical metaphor, payoff. About 150 words a minute.
The idea is shown as an object doing something, never as a labelled box.

## Step 2 — the picture

1. **Playbook** — set `style_playbook` to the family's playbook. Its prompt prefix carries the
   trigger, and its negative prompt carries only that family's exclusions.
2. **Read the construction file** before drawing or judging: proportions, face map, brush
   widths, colorist steps, layout modes, negative-space targets, acceptance checklist.
3. **Vocabulary** comes from `assets/style/handdrawn/lexicon.json`, and only phrases whose
   `use_condition` the picture actually satisfies. A phrase that describes something not in the
   image is contradictory supervision, not stylistic emphasis.
4. **Generation order**: the family LoRA through `comfyui_image`
   (`.ml/out-{a,b,c}/hdx_{a,b,c}_sdxl_v1.safetensors`, workflow
   `tools/_comfyui/workflows/sdxl-lora-txt2img.json`, server `.ml/serve_comfyui.sh` on :8188),
   then a reference-image provider with frames from that family's dataset, then nothing else.
   Pexels/Pixabay only for paper or fabric texture — a stock photo in frame breaks all three.
5. **Mega-prompts** for the three asset kinds live in `assets/style/handdrawn/mega-prompts/`:
   character plate, establishing environment, information object. Keep one family block, delete
   the rest, fill every bracket.

## Step 3 — the motion

`assets/hyperframes/handdrawn-alive/` — `alive.js` plus the family's `profile-*.js`. Copy both
into the HyperFrames workspace, load after GSAP, then:

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

What the measurements say, and what they mean for you:

| Measured over 6,572 frame pairs | A | C | Do |
|---|---|---|---|
| Stepping | every 2nd frame at 24 fps | same | animate on twos, 12 updates a second |
| Line wobble | none (0.01% of linework) | none | never add a boil filter |
| Paper grain | fixed | fixed | never animate the texture |
| Shots | 3.46 s median | 3.02 s | 2-5 s, 8 s maximum |
| Camera | 32% move, 24 px/s | 58% move, 51 px/s, 0.34%/s zoom | slow drift, ease-in-out |
| Secondary events | one per 0.64 s | one per 1.8 s | a prop event on this beat, every held shot |

B's timing is borrowed from A and says so in its profile: its own recording is 69% covered by
the player's controls. Re-measure it if a clean recording appears.

Rules the layer will not enforce for you: every held shot needs at least one `alive-*` group;
the subject stays still and the props move; do not mix smooth 24 fps tweens with the stepped
ones.

## Step 4 — voice and sound

`tts_selector` (ElevenLabs) with the family's `audio.voice_style`. Music at the playbook's
volume, ducked 6 dB. Sound effects only on reveals.

## Step 5 — accept or reject

Per family, in this order (from the study's director checklist):

- **A** — face first: pale bounded eye enclosures, small purposeful pupils, compact mouth. Then
  proportions, small hands and feet, prop contact. Only then paper and garment texture. A
  correct background cannot rescue a wrong face.
- **B** — fill the figure mentally as one black shape: does the role and gesture still read?
  Then the profile, the negative-space openings, the direction of the long prop. Then the
  incised marks. Last, whether the setting gives atmosphere without contaminating the figure.
- **C** — identify the mode first (botanical, diagram, cutaway, close-up) and judge against that
  subsystem. Branching must be coherent, pointers unambiguous, connections correct, irises and
  nostrils present in a close-up.

Full criteria and the numeric threshold: `docs/handdrawn-acceptance.md`. Evaluation prompts:
`assets/style/handdrawn/eval-prompts.yaml`.

## Known weaknesses, and what to do about each

Measured in the acceptance pass (`docs/handdrawn-acceptance-results.md`). Three of the
four are handled in the pipeline; the fourth needs new source material.

| Weakness | Cause | Handling |
|---|---|---|
| Wrong subject count ("two people" returns three) | base-model behaviour, not style | **fixed in the pipeline** — `generate_scene.py` counts the subjects in the render with the local vision model and moves to the next seed until the count matches |
| Gibberish lettering on cards, signs and labels | diffusion models cannot spell | **fixed in the pipeline** — the generator adds a no-text negative, asks for a blank label area, rejects any render containing letters, and the real words are typeset in the composition where they can be spelled and translated |
| C's diagram mode holds in only 3 seeds of 5 | few diagram frames exist in the source | **build diagrams in HyperFrames instead of generating them** — discs, connectors and icons as HTML, styled from `handdrawn-biotext.yaml`. The study's rule already says topology before styling; a generated graph cannot be trusted to have the right edges anyway |
| B's landscapes fall back to generic flat vector | 43 training frames, mostly detail crops, almost no clean environments | **not fixed** — use family B for figures and props, and carry its scenes with A- or C-style environments, or supply a clean recording (below) |

### The one thing that needs you

Family B is thin because its recording has the player's controls on screen 69% of the
time, which also makes its timing unmeasurable. A clean capture would fix both at once.

```bash
# play the video full screen, let the controls fade, then record the screen only
# (no browser window, no cursor), and drop the file next to the others:
#   assets/references/handdrawn/raw-video/video2.mov
```

With a clean capture: rerun `build_datasets.py`, `caption_frames.py`,
`.ml/train_family.sh b`, and `motion_analysis.py` — B then gets real environment
examples and its own measured timing instead of A's borrowed numbers.

## When something comes out wrong

| Output failure | Where to look | What to change |
|---|---|---|
| A gets a black facial mass | family mixing or ambiguous conditioning | keep the datasets and triggers apart; retest the isolated adapter |
| B figures are grainy throughout | texture wording, or contaminated figure examples | drop global-grain phrases; check the figure masks in the dataset |
| C diagrams grow heavy black outlines | over-generalised contour wording | use mode-specific captions and diagram references |
| Every A image contains a certificate | content entanglement from narrow examples | widen prop and action coverage; caption the certificate explicitly |
| Every B setting repeats one landscape | scene redundancy or memorisation | reduce repeated frames of that scene; add scene groups |
| C faces always carry yellow particles | scene content absorbed as style | caption particles as content, add clean face evidence |
| Outputs reproduce a progress bar | training contamination | audit and remove the frames; a negative prompt is not a fix |
| Right palette, wrong anatomy | surface terms outweigh construction | raise family structure in the prompt; improve anatomical coverage |
| Right icons, wrong graph edges | unconstrained topology | supply the edge list and verify it by hand |
| Great on training images, poor on new scenes | overfitting or weak base | judge on held-out content; adjust diversity and duration |

These are hypotheses. Change one factor at a time and re-run the same evaluation set.

## Rebuilding the whole thing

```bash
python -m scripts.style_refs.build_datasets assets/references/handdrawn --per-family 160
python -m scripts.style_refs.caption_frames assets/references/handdrawn
bash .ml/train_all.sh                      # A, then C, then B
python -m scripts.style_refs.motion_analysis assets/references/handdrawn/work/motion-src \
    --fps 24 --out assets/references/handdrawn/motion-profile.json
python -m scripts.style_refs.build_alive_profile assets/references/handdrawn/motion-profile.json \
    assets/hyperframes/handdrawn-alive/profile-a.js --video video1
```

Measuring our own render against the references:

```bash
ffmpeg -i renders/final.mp4 -vf "fps=24,scale=1470:-2" /tmp/f/%05d.png
python -m scripts.style_refs.motion_analysis /tmp/f --flat --fps 24 --out /tmp/ours.json
```

Compare `pooled` with that family's block in `motion-profile.json`: `drift_pan_px_per_s`,
`drift_zoom_pct_per_s`, `share_of_shots_moving`, `shot_seconds_median`,
`idle_events_per_minute`, and `grain_flicker_std` below 1.2. `line_change_while_holding_median`
scales with how much linework a scene has, so read it as a direction, not a target.

## Evidence and rights

What is measured, observed, inferred, prescribed or simply unknown:
`docs/handdrawn-evidence-boundaries.md`. Colour verification:
`docs/handdrawn-palette-verification.md`. Training history:
`docs/handdrawn-training-log.md`.

The reference material is a third party's copyrighted work. Learn the general grammar; never
reproduce their characters, scenes or marks, never put their name in a prompt, caption, trigger
or filename, and never present the output as theirs. **This repository is public**: no reference
frame, dataset image or derived GIF is ever committed. Only measured numbers and reports ship.

## The face gate — always on, never optional

Every generated or edited frame that could contain a person passes a face check
before it is used in a composition, a render, a thumbnail or a hand-off. There is
no flag to switch it off and no "just this once".

What it checks, per image:

1. Is there a person, face or character at all? If no, the image passes.
2. Does every person have two eyes, each with a visible pupil?
3. Is any face distorted — a missing eye, a missing pupil, a doubled or smeared
   mouth, a melted jaw?

A failure is a rejected seed, not a note: generate again, change the seed, and only
then adjust the prompt. Never retouch a broken face by hand and call it a pass, and
never ship the frame because "the rest of the shot is good" — a half-drawn stare is
the first thing a viewer sees, and no other check catches it. The count check, the
lettering check and the does-it-show-the-line check all pass happily on a face with
one pupil.

Reference implementation: `scripts/style_refs/generate_scene.py` → `face_is_whole()`
in the OpenMontage repo, which asks a local vision model the three questions above
and rejects the render when the answers are wrong. Any other generator — a provider
tool, an MCP connector, a hand-written script — carries the same gate before its
output is accepted. To audit frames that already exist, run the same function over
them (`projects/pilot-paperfolk/audit_faces.py` is the worked example) and
regenerate whatever it names.

Where this came from: a pilot shipped with the closing shot showing a character with
one blank eye. Everything else had been verified.
