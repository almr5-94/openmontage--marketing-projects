# Fragment Director — Editorial Magazine

Read `.agents/skills/image-forge/SKILL.md`. Tool: `image_crop`.

- Cut fragments in the approved motif family: `mask` with circle / hexagon / arc / stripe /
  polygon, along the object's own geometry; `smart_crop` (gravity `attention`) for exact slot sizes.
- Keep the subject's edges; never cut through a face or a hand.
- Review a `montage` contact sheet before moving on; discard nothing — unwanted fragments stay
  on disk (move them to `assets/fragments/components/`).
- Every fragment is recorded as `derived` with its parent and crop parameters.
