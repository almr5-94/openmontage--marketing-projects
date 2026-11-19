---
name: fashion-direction
description: Direct fashion and campaign imagery - shot lists, looks, light, casting notes and Runway prompts - for editorial and campaign pipelines. Generation runs only through the Runway MCP, every person image passes the face gate, and brand_lint blocks house names, trademarks and living artists in prompts.
---

# Fashion direction (Layer 7)

Upstream guidance (audited, SKILL.md only; supporting scripts were unavailable upstream):
`vendor/fashion-campaign/SKILL.md`. Use its craft — shot grammar, light, styling vocabulary — with
these overrides:

1. **Runway MCP only.** No Nano Banana / Gemini, Stability, FLUX, OpenAI image, fal or any other
   pay-per-call image tool (owner order 2026-11-19). If the Runway MCP is not connected, stop and say so.
2. **Every paid call needs an election ID** (`record_election`): show the model, the credit cost and
   the prompt, get a yes, then call.
3. **No names in prompts**: no real fashion or luxury houses, no trademarks, no living
   photographers, designers or artists. `maison/critique/brand_lint.py` rejects them. Describe the
   light, the cloth and the gesture instead.
4. **Face gate on every image of a person** (`run_face_gate`, photo mode): eyes, hands, teeth,
   warping. A failed take is moved to `components/`, never deleted.

## Output of this skill
`shots-<slug>.json` (one entry per shot: purpose, framing, lens feel, light, wardrobe, set, pose,
aspect ratio, Runway model) plus one `<shot>.prompt.txt` per shot, ready for the Runway MCP.
