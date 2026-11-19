# Executive Producer — Maison Drawing Series

A named, numbered series (`house.yaml` → `drawing_series.frame`, e.g. "Drawing Water No. 3") in one
fixed hand. Read `.agents/skills/maison-doctrine/SKILL.md` and the house file first.

Stages: series_brief → hand → assets → style_lock → layout → critique → publish.
- The hand is fixed once elected: medium look, line weight, palette, paper. Plate No. 30 must look
  like the same artist as No. 1; the style-lock stage enforces it.
- Engine order: seeded `generative_art` (free, reproducible — log every seed), the repo's
  hand-drawn style families (`scripts/style_refs`), then an elected Runway generation. Generation runs **only through the Runway MCP connector**, and only after the human elects it: show the model, the credits per call and the count, then record a `paid_election` decision (`record_election`) carrying the election ID before any call. Prompts describe qualities (light, hand, paper, palette); they never name a living artist, a photographer or a real house. Free sources first: Met, Cleveland, Rijksmuseum, AIC (CC0), Pexels, Pixabay, seeded `generative_art`.
- Every image that may show a person passes `run_face_gate` (photo or cartoon mode) before it is placed; a failure moves the file to `components/` with the reason, never deletes it.
