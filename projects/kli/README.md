# Kuwait Legal Insider — the factory

One Arabic 9:16 reel a day for **@kwlegalinsider**, produced, judged, published and measured
here. The editorial brain (promise, sourcing rules, voice, recurring world, judging contract,
idea bank, learning) is the separate repository `/home/abood/work/kuwait-legal-insider`; this
folder reads it before every reel and writes back only to `09_LEARNING/observations/`,
`09_LEARNING/REJECTION_REGISTER.md` and `07_OUTPUTS/SCRIPT_LEDGER.md`.

Pipeline manifest: `pipeline_defs/kli-daily-reel.yaml`. One OpenMontage project per reel:
`projects/kli-YYYYMMDD/` (checkpoints, artifacts, decision_log.json, events.jsonl, renders).

| Script | Does | When |
|---|---|---|
| `kli_world.py build / accept` | builds the recurring-world reference stills, owner accepts each | once |
| `kli_cast.py run / sign` | casts the male Kuwaiti narrator, owner signs the pick | once |
| `kli_daily.py run` | idea → script → scene_plan → assets → edit → compose → judge (+1 revision) | 09:00 daily (timer) |
| `kli_publish.py` | posts the judged reel when `live_enabled.json` is signed, 16:00–20:00 | 16:30 daily (timer) |
| `kli_metrics.py` | 48 h insights → `metrics/` and the brain's observations | hourly (timer) |

Owner switches: `live_enabled.json` (posting on/off), `PAUSE` (stop production), `budget.json`
(USD 15 per reel, USD 400 per month). Everything paid is metered in the reel's `events.jsonl`
and the guard refuses a call that would breach either cap.

Run everything from the repo root with the repo venv: `.venv/bin/python projects/kli/<script>`.
