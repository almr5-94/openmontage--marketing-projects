# Matching Parts Director — Editorial Magazine (optional, paid)

New fragments that extend a real artwork's palette and texture. **Runway MCP only** — there is no
pay-per-call image API in this system (owner order 2026-11-19) and no `RUNWAY_API_KEY`.

## Before any call
1. A micro-brief per part: the one idea, subject, medium, light, palette, texture, composition,
   crop, and the reference fragment it must match (a file from `assets/fragments/`).
2. `brand_lint` on the prompt (no house, trademark or living-artist names).
3. Show the user the model, the prompt and the **credit cost**; on their yes, record a
   `paid_election` decision (`election_id`, `cost`, `user_approved: true`). No election, no call.

## After each result
- Face gate (`run_face_gate`) if a person may appear; a failure means a new seed, not a retouch.
- Save under `assets/generated/`, record provenance `generated-in-session` with the parent fragment.
- Rejected takes are kept in `assets/generated/components/`.

If the user does not elect generation, skip the stage and log why.
