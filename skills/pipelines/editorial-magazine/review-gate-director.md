# Review Gate Director — Editorial Magazine

Blocking. Run, in order, and write a `quality_gate`:

1. **Anti-AI-tells** — `qa_anti_ai_tells` (MCP) / `om qa` (CLI) on the screen PDF with the source
   HTML: automated AP-1..AP-7 checks, the local vision critic, and **your own page critique**:
   open every page PNG in `qa/pages/`, compare with `qa/anti-patterns/` and record verdicts in
   `qa/critic/claude_verdicts.<pdf stem>.json` (codes, publish yes/no, a note). Re-run the gate.
2. **Face gate** — `run_face_gate` on every image that may show a person (photo or cartoon mode).
3. **Provenance** — `lib.provenance.check_complete` on every image placed in the issue.
4. **brand_lint** — `python maison/critique/brand_lint.py projects/<id>`.
5. Contrast and legibility — every text/ground pair from the art system meets WCAG AA.

Any failure → the page goes back to its stage with the reasons. An override is valid only as an
`anti_pattern_override` decision carrying the user's own reason and the page numbers.
Write `print_review` from what you saw, page by page.
