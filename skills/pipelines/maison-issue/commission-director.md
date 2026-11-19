# Commission Director

Treat the image set as one commission: write a short brief per story (light, palette, hand, paper,
lens or medium) all derived from house.yaml, so the issue reads as one body of work.

- Source free first; pair an archive object with a contemporary image wherever the inventory asks.
- Each source image is used once (AP-5): no flips, crops or recolours of the same picture elsewhere.
- Run a consistency check on the whole set (`image_crop` montage) and redo outliers.
- Every image that may show a person passes `run_face_gate` (photo or cartoon mode) before it is placed; a failure moves the file to `components/` with the reason, never deletes it.
- Generation runs **only through the Runway MCP connector**, and only after the human elects it: show the model, the credits per call and the count, then record a `paid_election` decision (`record_election`) carrying the election ID before any call. Prompts describe qualities (light, hand, paper, palette); they never name a living artist, a photographer or a real house. Free sources first: Met, Cleveland, Rijksmuseum, AIC (CC0), Pexels, Pixabay, seeded `generative_art`.
Write `asset_manifest` with provenance for every file.
