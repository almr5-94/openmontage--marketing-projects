---
name: handdrawn-biotext
description: >
  Family C of the hand-drawn explainer system — "bio texture": filled organic shapes with
  local-colour outlines, drawn veins, growth rings and dots, cream-disc diagrams,
  callouts, and close-up faces with big radial irises and nostril marks. Trigger
  `hdx_biotext`. Use for nature and science explainers, biology, ecosystems, networks and
  labelled diagrams — anything where the subject is an organism, a system or a
  relationship rather than a person telling a story. Also use it to judge or fix an
  existing family-C plate, to render one with the trained adapter, or to animate a held
  botanical or diagram shot. Do NOT use it for outlined paper people (that is
  handdrawn-paperfolk) or black silhouette myth scenes (handdrawn-incise), and never put
  a uniform heavy black outline around a C subject. Diagrams are built in HyperFrames,
  not generated — see "Build diagrams, do not generate them".
---

# Family C — bio texture

One of **three separate** illustration systems learned from three reference recordings.
They contradict each other: C's outlines take the *object's own colour*, which is exactly
what A's near-black contour and B's black mass forbid. Pick one family per video, or
split the video into sections and give each section exactly one family.

Everything below lives on **abood** at `/home/abood/work/openmontage--marketing-projects`.
Run every command with `abrun` from the handle folder
`/Users/ebod/servers-and-projects/abood/projects/openmontage-marketing-projects`. No
source and no compute on the Mac.

## Read these two files before drawing or judging

| Purpose | File |
|---|---|
| Playbook the pipeline loads (palette, typography, motion, prompts, negatives) | `styles/handdrawn-biotext.yaml` |
| Construction rules (linework, object morphology, face rule, modes, checklist) | `assets/style/handdrawn/construction/c.yaml` |
| Controlled vocabulary — only phrases whose `use_condition` the picture satisfies | `assets/style/handdrawn/lexicon.json` |
| Fillable templates: character plate, environment, information object | `assets/style/handdrawn/mega-prompts/` |

## Choose the mode first — everything else depends on it

Four modes with four different subsystems. Naming the mode is step one of both drawing
and judging; "organic paper illustration" is too weak a verdict to distinguish them.

| Mode | Organisation | Target |
|---|---|---|
| **Botanical setting** | foreground vegetation framing an open middle distance | keep a readable environmental opening; coherent branching |
| **Comparison callouts** | two large discs tied to their source organisms | one unambiguous pointer each; modules legible |
| **Scientific network** | unequal nodes and connecting edges | node hierarchy and *actual* connection meaning; 20–40% connective breathing room |
| **Extreme close-up** | face or cutaway fills the frame | deliberate crop, dominant eyes, no invented body |
| **Internal form** | strong diagonal biological structure | preserve taper direction and surrounding context |

## The non-negotiables

- **Outlines take the object's own colour** — darker green on a leaf, red on a salmon
  form. A uniform heavy black contour around everything is the signature failure of this
  family. Structural marks 0.12–0.30% of art width, 0–15% size variation, 1–6% spacing;
  use a separate dispersed-tip brush for dots rather than breaking a contour into dashes.
- **Drawn pattern follows the object**: veins split a leaf, rings follow a cut trunk,
  dots run along a trunk, radial lines fill an iris. Surface irregularity stays
  subordinate — it must never turn a diagram into noisy wallpaper or a leaf into a
  botanical engraving.
- **Palette**: field `#94C0B9`, primaries `#1E4146` / `#5D5E1E`, cream `#DADFC9`, deep
  green `#34624D`; warm accents `#E9783C` / `#EDA094` mark biological emphasis and stay
  spatially concentrated. Diagram mode keeps its own restricted palette: cream discs on a
  quiet field, dark-green pictograms, pale connectors drawn *behind* the containers, a
  visible rim inside every disc.
- **Close-up faces**: an iris filling most of the eye opening, a pupil ½–⅔ of the iris
  diameter, sparse radial lines that stay separately legible, a warmer tapered nose plane
  with small dark nostril strokes, small dots and short curved lines on the cheeks. Do
  not import family A's flat-face grammar. Skull top and chin are cropped in the
  evidence — never extrapolate a whole head from it.
- **Morphology instead of a person template**: trees branch and carry rounded, lobed or
  disc-like canopies; a mushroom is a broad cap over a narrow stem with smaller ones
  repeating the shape at reduced scale (family resemblance, not clones); a diagram icon
  condenses identity into masses that stay legible inside a disc. **Full-body human
  proportions are not established for this family — do not invent them.**
- Black, orange, red and saturated accents are allowed here. Only uniform heavy black
  outlines are not.
- Scene content is not anatomy: yellow particles floating over a face in the reference
  are content, and must not become permanent freckles on every generated face.

## The face gate — always on, never optional

Close-up mode puts a face across the whole frame, which is the worst possible place for a
missing pupil. Every image that could contain a person or a creature's face passes the
check before it enters a composition, a render, a thumbnail or a hand-off. No flag turns
it off. A failure is a rejected seed: generate again, change the seed, and only then
adjust the prompt. Never retouch a broken face by hand and call it a pass.

1. Is there a person, face or character at all? If not, the image passes.
2. Does every face have two eyes, each with a visible pupil inside its eye opening?
   `eye_geometry()` measures the pupil's position instead of asking — a pupil on the rim
   fails, and two pupils disagreeing by more than 0.5 horizontally / 0.4 vertically fail.
3. Is the mouth a simple mark, without teeth or a filled dark hole? `mouth_is_simple()`
   rejects a largest mouth mark above 0.05 × span².

Implementation: `scripts/style_refs/generate_scene.py` → `face_is_whole()`. Any other
generator carries the same gate. Audit existing frames with the same function —
`projects/pilot-paperfolk/audit_faces.py` is the worked example.

Where this came from: a pilot shipped with a closing shot showing a character with one
blank eye; everything else about it had been verified. A vision model answers "yes, it
has a pupil" about a pupil painted on the rim — so the gate measures geometry. In this
family the check runs **with** the mode rule: a C iris is large and radial by design, and
that is not a defect to be "corrected" toward A's small pupil.

## Draw a plate

```bash
abrun 'nohup bash .ml/serve_comfyui.sh > /tmp/comfy.log 2>&1 &'   # server on :8188
abrun 'python -m scripts.style_refs.generate_scene c \
  "a cluster of three mushrooms on a mossy log, open middle distance behind" \
  --out projects/<proj>/plates/s1.png \
  --must-show "three mushrooms on a log" \
  --subjects 3 --noun mushrooms --seeds 7 101 202 303 404 505'
```

`--noun` takes whatever the scene is counting — mushrooms, containers, nodes — not just
people. The generator verifies the render shows `--must-show`, counts subjects, rejects
lettering (diffusion cannot spell; the real words are typeset later in the composition
where they can be spelled and translated), and runs the face gate. `--cutout` keys the
background away for a prop that must animate on its own. Renders land at `*.attempt.png`
and only move into place on acceptance.

Adapter: `.ml/out-c/hdx_c_sdxl_v1.safetensors`, workflow
`tools/_comfyui/workflows/sdxl-lora-txt2img.json`, 128 training images — the largest of
the three. Acceptance scored **17 of 25 usable, 5 of 5 cases, 0 contamination**
(`docs/handdrawn-acceptance-results.md`). Reference frames from
`assets/references/handdrawn/dataset-c`; stock photos only for paper texture.

## Build diagrams, do not generate them

Diagram mode holds in only 3 of 5 seeds, because few diagram frames exist in the source —
and a generated graph cannot be trusted to have the right edges anyway. **Topology before
styling** is already the rule. So build discs, connectors and icons as HTML in
HyperFrames, styled from `styles/handdrawn-biotext.yaml`: cream discs with a visible
inner rim, dark-green pictograms, pale connectors behind the discs, 20–40% breathing
room. Supply the edge list yourself and verify it by hand. Generate the organisms; build
the graph.

## Move it

`assets/hyperframes/handdrawn-alive/` — copy `alive.js` and `profile-c.js` into the
HyperFrames workspace, load after GSAP, then `alive-hold` on the shot, `alive-pop` /
`alive-float` / `alive-scatter` on props, `alive-grain` once.

```js
const tl = gsap.timeline({ paused: true });
HandDrawnAlive.apply(tl, document.getElementById("root"));
window.__timelines["main"] = tl;
```

Measured over 4,075 frame pairs of reference video 3 — this family's own numbers, and
they are **not** family A's:

| Measured | Value | What you do |
|---|---|---|
| Stepping | changes land every 2nd frame at 24 fps | animate on twos: 12 updates a second |
| Line wobble | 0.0001 median change while holding | never add a boil filter |
| Shots | 3.02 s median (1.63 p25 / 5.60 p75) | 2–5 s, 8 s maximum |
| Holding | 42% of screen time | this family moves the camera far more than A does |
| Camera | **58% of shots move**, pan 51.2 px/s, zoom 0.34%/s | push-in and pull-out are both normal here (7 and 6 of 15) |
| Easing | ease-out most common, then ease-in-out | not a single house ease |
| Secondary events | 33.6 per minute — one every 1.8 s | fewer, larger prop events than A |
| Surface | grain flicker std 0.34 while holding (p90 5.1) | the liveliest surface of the three, but still not an animated texture |

The camera doing the work is the difference you will feel most: A holds still and moves
props; C drifts and scales across a layered scene. Never mix smooth 24 fps tweens with
the stepped ones, and every held shot still carries at least one `alive-*` group.

## Accept or reject

1. **Name the mode**, then judge against that subsystem — botanical, callout, network,
   close-up or internal form.
2. **Botanical**: coherent branching — leaf to stem, cap to stalk, root to body.
3. **Network**: a graph is wrong if its connections are wrong, however attractive the
   discs look. Never bury a connector under texture.
4. **Callout**: one unambiguous pointer to its source organism.
5. **Close-up**: detailed irises and visible nostrils present; no imported flat-face
   grammar; no invented body below the crop.
6. Compare at the intended final size, inspect the densest region separately, preserve
   exact scientific meaning, and remove accidental interface elements from the acceptance
   set.

Full criteria: `docs/handdrawn-acceptance.md`. Evaluation prompts:
`assets/style/handdrawn/eval-prompts.yaml` (cases C-eval-1…5, fixed seeds
7/101/202/303/404 plus extra seeds).

## When it comes out wrong

| Failure | Cause | Fix |
|---|---|---|
| Heavy black outlines on every plant | over-generalised contour wording | use mode-specific captions and diagram references |
| Diagram mode collapses | few diagram frames in the source | build the diagram in HyperFrames (above) |
| Right icons, wrong graph edges | unconstrained topology | supply the edge list and verify it by hand |
| Faces always carry yellow particles | scene content absorbed as style | caption particles as content; add clean face evidence |
| Texture swallows small icons | surface irregularity not subordinated | reduce pattern density; keep pattern object-specific |
| A progress bar appears | training contamination | audit and remove those frames; a negative prompt is not a fix |
| A whole human body appears in a close-up scene | invented proportions | reject it; this family has no established body template |

These are hypotheses. Change one factor at a time and re-run the same evaluation set.

## Rebuilding

```bash
abrun 'python -m scripts.style_refs.build_datasets assets/references/handdrawn --per-family 160'
abrun 'python -m scripts.style_refs.caption_frames assets/references/handdrawn'
abrun 'bash .ml/train_family.sh c'
abrun 'python -m scripts.style_refs.motion_analysis assets/references/handdrawn/work/motion-src \
  --fps 24 --out assets/references/handdrawn/motion-profile.json'
```

Measure our own render against the reference:

```bash
abrun 'ffmpeg -i renders/final.mp4 -vf "fps=24,scale=1470:-2" /tmp/f/%05d.png && \
  python -m scripts.style_refs.motion_analysis /tmp/f --flat --fps 24 --out /tmp/ours.json'
```

Compare `pooled` with `videos.video3` in `motion-profile.json`: `drift_pan_px_per_s`,
`drift_zoom_pct_per_s`, `share_of_shots_moving`, `shot_seconds_median`,
`idle_events_per_minute`, `grain_flicker_std` below 1.2.

## Evidence and rights

Boundaries between measured, observed, inferred and prescribed — including the
proportions this family deliberately does not claim:
`docs/handdrawn-evidence-boundaries.md`. Colour verification:
`docs/handdrawn-palette-verification.md`. Training history:
`docs/handdrawn-training-log.md`.

The reference material is a third party's copyrighted work. Learn the general grammar;
never reproduce their characters, scenes or marks, never put their name in a prompt,
caption, trigger or filename, and never present the output as theirs. **The repository is
public**: no reference frame, dataset image or derived GIF is ever committed.
