# Maison

Maison is the high-art side of the OpenMontage print studio: collectible magazines, numbered drawing
series and luxury campaigns for a **house** — the user's own brand, a client's brand, or an invented one.

Its bar is the four references analysed (text only, no images kept) in [`references/`](references/README.md):
an art guide, a watchmaker's magazine, a fashion house's art paper and a leather house's art magazine.
The shared rules are in [`references/synthesis.md`](references/synthesis.md) and became the ten doctrine
principles in [`doctrine/`](doctrine/README.md) (index skill: `.agents/skills/maison-doctrine/SKILL.md`).

## Folders

| Folder | What it holds |
|---|---|
| `doctrine/` | Ten principles, one skill each: culture first, one theme, the incomplete inventory, the singular cover object, archive and contemporary, the commissioned image set, the fixed hand, the house grid, restraint, the precise voice |
| `references/` | Text analysis of the four reference publications and the synthesis |
| `houses/<id>/house.yaml` | A house: owner type, languages, palette, type, grid, voice, motifs, masthead, production, drawing-series frame |
| `pipelines/` | Plain-language guides to the three pipelines (the manifests are in `pipeline_defs/`) |
| `critique/` | `rubric.md`, the two critic prompts, `critique.py` (the gate) and `brand_lint.py` |

## Pipelines

| Pipeline | Makes | Manifest |
|---|---|---|
| `maison-issue` | an issue of a house magazine | `pipeline_defs/maison-issue.yaml` |
| `maison-drawing-series` | numbered plates in one fixed hand, an index and an archive page | `pipeline_defs/maison-drawing-series.yaml` |
| `maison-campaign` | one-idea campaign: master composition plus placement variants | `pipeline_defs/maison-campaign.yaml` |

## The gates (all blocking)

1. **Maison critique** — nine criteria (restraint, one idea, craft, cohesion, archive dialogue, voice,
   typography, originality, Arabic edition) scored 1–5 by Claude and by the local models; the lower score
   counts and anything below 4 goes back to the stage the rubric names.
2. **Anti-AI-tells** — `qa/anti_ai_tells.py`, AP-1..AP-7.
3. **Face gate** — every image that shows a person.
4. **brand_lint** — no real house's name, monogram or trade dress unless `brand_owner` is `self` or `client`.
5. **Provenance** — every placed image traces to a source and licence.

## Rules that never bend

- Images and video are generated **only through the Runway MCP**, after the human elects the call with
  its credits shown. Free sources (CC0 museums, Pexels, Pixabay, seeded drawing) come first.
- Prompts describe qualities, never a living artist, photographer or real house.
- Fonts are OFL only (see `print-studio/fonts/FONTS.yaml`). Paper is simulated in the proofs.
- Generated media is never deleted; rejected takes move to `components/`.
- Arabic is a native right-to-left edition with Latin digits, not a mirrored English one.

## Start

```bash
om maison house new my-house          # or copy houses/maison-example/house.yaml
om maison issue new my-issue --house my-house --theme Water
om maison critique projects/my-issue --claude-scores projects/my-issue/qa/critic/claude_scores.json
om maison export projects/my-issue
```

The same actions are MCP tools (`maison_new_house`, `maison_new_issue`, `maison_run_stage`,
`maison_critique`, `maison_export`) — both call `lib/studio_api.py`.

`houses/maison-example/` is an invented house used for tests and smoke runs. It is not, and must not
resemble, any real brand.
