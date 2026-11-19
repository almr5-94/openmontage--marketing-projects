# Idea Director — KLI Daily Reel Pipeline

## When to Use

The `idea` stage of `kli-daily-reel`. This pipeline is driven unattended by
`projects/kli/kli_daily.py`, not by an agent conversation. Read this file when you, as an agent,
inspect, resume, debug or hand-run a KLI reel, so you know which choices are already made and
where they are recorded.

## What the stage does

Picks one topic from the KLI idea bank that is not in the script ledger or the rejection
register, attaches its primary-source URL and a demonstration object, and writes a schema-valid
`brief` (target platform instagram, 15-40 s) plus the run's `decision_log`.

## Standing elections — no menu at run time

The owner approved one standing tool plan for every KLI reel on 2026-09-27 (decision D4 of the
restart). It is the only "stop asking" authority this pipeline has, and its scope is exactly
the list in `ELECTIONS` in `projects/kli/kli_daily.py`:

| Capability | Elected | Also considered (logged as rejected) |
|---|---|---|
| Narration | `elevenlabs_tts` (signed male Kuwaiti voice) | `google_tts`, `piper_tts` |
| Per-shot stills | `qwen_image_edit_local` | `google_imagen`, `pexels_image` |
| Motion | `veo_video` | `pexels_video`, Runway MCP |
| Music | `google_music` | `music_library`, `pixabay_music` |
| Composition runtime | **HyperFrames** | Remotion, FFmpeg |

Each run writes these as `decision_log` entries, with every option in `options_considered`.

## Composition runtime (`render_runtime`)

`render_runtime` is locked to `hyperframes` for this pipeline. The two runtimes were presented
when the standing plan was approved, and every run records the choice again as a
`render_runtime_selection` decision listing **hyperframes** (selected: RTL Arabic captions
already proven in the Sard reels), **remotion** (rejected: no RTL caption component), and
**ffmpeg** (rejected: ASS subtitles dropped lam-alef ligatures in KLI tests).

Do not present both runtimes again at run time. The standing election covers it. Re-open the
question with the owner only if HyperFrames is unavailable on the machine, or if a change would
alter the reel's caption system. In either case, ask before switching. A silent swap is a
CRITICAL governance violation (`AGENT_GUIDE.md` → "Present Both Composition Runtimes").
