# Critique Director — Maison Drawing Series

Blocking. The luxury bar: every criterion of `maison/critique/rubric.md` must score **4 or higher**
from BOTH critics, with evidence. Anything lower goes back to the stage the rubric names.

1. Render the screen PDF and page PNGs (`editorial_layout`, `pngs`).
2. **Your scores (Claude critic)** — follow `maison/critique/critic_claude.md`: open every page PNG,
   score each criterion 1-5 with one sentence of evidence that points at a page, and save
   `projects/<id>/qa/critic/claude_scores.json` as `{"model": "...", "scores": {criterion: {score, evidence, send_back_to}}}`.
3. **Run the gate** — `maison_critique` (MCP) / `om maison critique <project> --claude-scores ...` (CLI).
   It adds the local critic (`maison/critique/critic_local.md`: the vision model per page and on a
   contact sheet, the reasoning model on the copy and the Arabic), takes the LOWER score per
   criterion and writes `qa/maison_critique.json` + `.md`.
4. **Anti-AI-tells** — `qa_anti_ai_tells` / `om qa` with your page verdicts in
   `qa/critic/claude_verdicts.json`. Must pass (or carry a logged `anti_pattern_override`).
5. **Face gate, provenance, brand_lint** — `python maison/critique/brand_lint.py projects/<id>`
   must exit 0. A real house's name, monogram or trade dress is allowed only when `house.yaml`
   says `brand_owner: self` or `client`.
6. Write `quality_gate` (pass only when every check passed) and show the human the scores table.

Each send-back is logged in the decision log; after `max_send_backs` (3) the human decides.
A `critique_override` is valid only with the human's own reason.
