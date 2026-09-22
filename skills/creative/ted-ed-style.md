# Hand-drawn Explainer Style (Layer 2)

How OpenMontage makes a narrated explainer in the hand-drawn style learned from
the three reference videos in `assets/references/ted-ed/`. Everything here is
measured, not taste: the numbers come from `assets/references/ted-ed/motion-profile.json`
and the colours from `assets/references/ted-ed/clean/`.

## When to use

Use when the brief asks for a narrated explainer that teaches one idea, and the
user asks for the hand-drawn / TED-Ed-like look, names `ted-ed-handdrawn`, or
points at `assets/references/ted-ed/board/`.

Do not use it for product UI walkthroughs, data-heavy dashboards, talking-head
recuts or cinematic trailers — the style has no visual grammar for them.

## What the style actually is

Measured across 6,572 frame pairs of the references (videos 1 and 3; video 2 was
recorded with the player controls on screen 69% of the time and is excluded from
the motion numbers):

| Property | Measured | What to do |
|---|---|---|
| Frame stepping | changes land every 2nd frame at 24 fps | animate **on twos** (12 updates a second) |
| Line wobble | 0.09% of linework changes while holding | **none** — lines stay still |
| Paper grain | 0.21 grey levels of flicker (codec noise) | **fixed** texture, never animated |
| Shot length | median 3.2 s | 2–5 s per shot, 8 s absolute maximum |
| Camera | 46% of shots move: ~39 px/s pan, ~0.2%/s zoom, ease-in-out | slow drift on about half the shots |
| Secondary motion | one local event every ~1.0 s | a prop event every second in every held shot |
| Transitions | cuts outnumber dissolves ~3:1; dissolves ~1.9 s | cut by default, long dissolve for a section change |

The scene itself holds still. What keeps it alive is the **secondary props**:
icons popping in one after another around a figure, bubbles rising out of a
head, pieces of a pattern dissolving away one by one, blocks sliding into a
staircase. That is the single most important thing to get right.

## Pipeline

1. **Script** — hook, then the question, then the explanation carried by one
   physical metaphor, then the payoff. Around 150 words a minute of video.
   Never a labelled box diagram: the idea is shown as an object doing something.
2. **Playbook** — set `style_playbook: ted-ed-handdrawn` (`styles/ted-ed-handdrawn.yaml`).
   Its `image_prompt_prefix` already carries the LoRA trigger.
3. **Scene stills** — in this order:
   - `comfyui_image` with `.ml/ComfyUI/models/loras/tededstyle_sdxl_v1.safetensors`
     (trigger `tededstyle`, plus one sub-style: `flat character scene`,
     `black silhouette myth scene`, `textured nature scene`). Free, local, closest match.
   - Higgsfield or another `image_selector` provider with 3–5 frames from
     `assets/references/ted-ed/board/` attached as visual references, when the
     LoRA is unavailable or a scene needs a capability it does not have.
   - Pexels/Pixabay only for paper or fabric textures. Never a stock photo in frame:
     photographic material breaks the drawn look instantly.
   Cut every subject out onto transparency (`bg_remove`) so it can be animated
   separately from the background.
4. **Motion** — `render_runtime: hyperframes`, with the `ted-ed-alive` layer
   (below) applied to every composition.
5. **Voice** — `tts_selector` (ElevenLabs), calm and curious, unhurried; slower
   and half a step lower on the payoff.
6. **Music** — light acoustic bed at 0.1, ducked 6 dB under the voice. Sound
   effects only on reveals.

## The ted-ed-alive layer

`assets/hyperframes/ted-ed-alive/` — `alive.js` plus `profile.js`, which is
generated from the measurements:

```bash
python -m scripts.style_refs.build_alive_profile \
    assets/references/ted-ed/motion-profile.json \
    assets/hyperframes/ted-ed-alive/profile.js
```

Copy both files into the HyperFrames workspace, load them after GSAP, and mark
up each scene:

```html
<section class="clip" data-start="0" data-duration="4">
  <div class="alive-hold">                 <!-- slow camera drift on the shot -->
    <div class="alive-float" data-rise="120">…</div>   <!-- rise and fade, staggered -->
    <div class="alive-pop" data-lead="1.2">…</div>     <!-- pop in, one after another -->
    <div class="alive-scatter">…</div>                 <!-- dissolve away, staggered -->
    <g class="alive-blink">…</g> <g class="alive-breathe">…</g> <g class="alive-sway">…</g>
  </div>
</section>
<div class="alive-grain"></div>            <!-- fixed paper texture, once -->
```

```js
const tl = gsap.timeline({ paused: true });
// …your own scene tweens…
TedEdAlive.apply(tl, document.getElementById("root"));
window.__timelines["main"] = tl;
```

`data-drift="on"` / `"off"` overrides the dice on a shot. `TedEdAlive.onTwos(ease,
duration, 12)` wraps any ease of your own so it steps like the rest.

Rules the layer does not enforce for you:

- Every held shot needs at least one `alive-*` group. A shot with none is a frozen
  picture, which the reference never has.
- Keep the subject still. Animate what is *around* it.
- Do not add smooth 24 fps tweens next to the stepped ones; the mismatch is visible.

Working example: `assets/hyperframes/ted-ed-alive/demo/index.html` (10 s, renders
in about 9 s).

## Checking a render against the references

```bash
ffmpeg -i renders/final.mp4 -vf "fps=24,scale=1470:-2" /tmp/f/%05d.png
python -m scripts.style_refs.motion_analysis /tmp/f --flat --fps 24 --out /tmp/ours.json
```

Compare `pooled` with `assets/references/ted-ed/motion-profile.json`. Targets,
within about 20%: `drift_pan_px_per_s`, `drift_zoom_pct_per_s`,
`share_of_shots_moving`, `shot_seconds_median`, `idle_events_per_minute`, and
`grain_flicker_std` below 1.2 (a fixed texture). `line_change_while_holding_median`
depends on how much linework a scene has, so read it as a direction, not a target.

## Rights

The style was learned from copyrighted TED-Ed videos. A general look is fine to
learn from; the specifics are not. Never reproduce their characters, scenes or
marks, never use "TED" or "TED-Ed" in a prompt or a caption, and never present
the output as theirs. **This repository is public**, so no reference frame is
ever committed: the raw frames, the cleaned set, the board, the training data
and the reference GIFs all stay on abood and are gitignored. Only the measured
numbers (`motion-profile.json`, the reports) are in git. Rebuild the frames from
the recordings in `assets/references/ted-ed/raw-video/` with
`scripts/style_refs/prepare_frames.py` and `select_board.py`.

## Where the parts live

| Path | What |
|---|---|
| `styles/ted-ed-handdrawn.yaml` | the playbook: palette, type, pacing, prompts |
| `assets/references/ted-ed/board/` | 41 reference frames for image models and human review (local only, never committed) |
| `assets/references/ted-ed/motion-profile.json` | the measured motion numbers |
| `assets/references/ted-ed/motion/` | timeline charts and close-up GIFs of the references (local only) |
| `assets/hyperframes/ted-ed-alive/` | the motion layer, its profile and the demo |
| `scripts/style_refs/` | prepare_frames, motion_analysis, build_alive_profile, select_board, caption_frames |
| `.ml/` | ComfyUI, the trainer, the SDXL base model and the trained LoRA (never committed) |
