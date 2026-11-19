# Compose Director — KLI Daily Reel Pipeline

## When to Use

The `compose` stage of `kli-daily-reel`, run by `projects/kli/kli_daily.py`. Read it when you
inspect or hand-run a KLI render.

## Runtime routing

Compose routes on `edit_decisions.render_runtime`. For this pipeline it must be `hyperframes`:
see the standing `render_runtime_selection` decision in the run's `decision_log` and
`skills/pipelines/kli-daily-reel/idea-director.md`. If `render_runtime` is anything else, stop
and report it. Never fall back to Remotion or FFmpeg silently.

## Steps

1. The composition is built from `projects/kli/composition/index.tpl.html` (RTL Arabic
   captions, Tajawal / IBM Plex Sans Arabic, grain overlay, GSAP). Read `skills/core/hyperframes.md`.
2. `hyperframes lint` and `hyperframes validate` must pass before render.
3. Mix narration and music with `audio_mixer` (the narration master is normalized first, the
   final is loudness-normalized).
4. The output must be 1080x1920, 30 fps, h264/aac, 15-40 s. Write a schema-valid
   `render_report`.
